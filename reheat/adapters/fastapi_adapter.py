import inspect
import logging
from importlib.resources import files
from typing import Optional, get_type_hints

from dynawrap.backends.base import DBBackend
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import create_model

from reheat.registry import Payload, Resource, registry
from reheat.state import init_backend

logger = logging.getLogger(__name__)

APP_METADATA = dict(
    title="reheat",
    description="Intent harvesting and market research API.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


def _static_dir() -> str:
    return str(files("reheat").joinpath("static"))


STATIC_MOUNTS = [
    ("/static", _static_dir(), "static"),
]

VERB_SEGMENTS = {"list", "show", "read", "create", "update", "delete"}


def get_backend() -> DBBackend:
    return init_backend()


def _inner_type(annotation) -> type:
    args = getattr(annotation, "__args__", None)
    return args[0] if args else str


def _classify_params(fn) -> tuple:
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    resources, payloads, queries = [], [], []

    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            continue
        annotation = hints.get(name)
        origin = getattr(annotation, "__origin__", None)
        default = param.default
        if origin is Resource:
            resources.append((name, _inner_type(annotation), default))
        elif origin is Payload:
            payloads.append((name, _inner_type(annotation), default))
        else:
            queries.append((name, annotation, default))

    return resources, payloads, queries


def _path_to_route(path: str, fn) -> str:
    parts = path.split(".")
    segments = [p for p in parts if p not in VERB_SEGMENTS]
    route = "/" + "/".join(segments)
    resources, _, _ = _classify_params(fn)
    for name, _, _ in resources:
        route += f"/{{{name}}}"
    return route


def _path_to_method(path: str) -> str:
    last = path.split(".")[-1]
    if last in ("read", "list", "show"):
        return "GET"
    if last in ("create", "set", "update"):
        return "POST"
    if last == "delete":
        return "DELETE"
    return "POST"


def _make_get_handler(fn):
    resources, _, queries = _classify_params(fn)

    params = []
    for name, typ, default in resources:
        params.append(
            inspect.Parameter(
                name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=typ,
            )
        )
    for name, typ, default in queries:
        params.append(
            inspect.Parameter(
                name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Optional[typ],
                default=default if default is not inspect.Parameter.empty else None,
            )
        )
    params.append(
        inspect.Parameter(
            "backend",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=DBBackend,
            default=Depends(get_backend),
        )
    )

    async def handler(backend: DBBackend = Depends(get_backend), **kwargs):
        try:
            return fn(backend, **kwargs)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.exception("error in %s", fn.__name__)
            raise HTTPException(status_code=500, detail=str(e))

    handler.__signature__ = inspect.Signature(params)
    handler.__name__ = fn.__name__
    handler.__doc__ = inspect.getdoc(fn) or fn._cli_help
    return handler


def _make_post_handler(fn):
    _, payloads, _ = _classify_params(fn)

    if not payloads:
        raise ValueError(
            f"{fn.__name__} is registered as POST but has no Payload parameters."
        )

    fields = {
        name: (
            Optional[typ],
            default if default is not inspect.Parameter.empty else None,
        )
        for name, typ, default in payloads
    }

    body_model = create_model(f"{fn.__name__}_body", **fields)

    async def handler(
        backend: DBBackend = Depends(get_backend),
        body: body_model = None,
    ):
        try:
            return fn(backend, **body.model_dump())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("error in %s", fn.__name__)
            raise HTTPException(status_code=500, detail=str(e))

    handler.__name__ = fn.__name__
    handler.__doc__ = inspect.getdoc(fn) or fn._cli_help
    return handler


def build_app() -> FastAPI:
    app = FastAPI(**APP_METADATA)

    for mount_path, directory, name in STATIC_MOUNTS:
        app.mount(
            mount_path,
            StaticFiles(directory=str(directory)),
            name=name,
        )

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/static/index.html")

    for path, fn in sorted(registry.items()):
        if getattr(fn, "_interactive_only", False):
            continue

        route = _path_to_route(path, fn)
        method = _path_to_method(path)
        tag = [path.split(".")[0]]

        try:
            if method == "GET":
                handler = _make_get_handler(fn)
                app.get(route, summary=fn._cli_help, tags=tag)(handler)
            elif method == "DELETE":
                handler = _make_get_handler(fn)
                app.delete(route, summary=fn._cli_help, tags=tag)(handler)
            elif method == "POST":
                handler = _make_post_handler(fn)
                app.post(route, summary=fn._cli_help, tags=tag)(handler)
            else:
                logger.warning("unknown method %s for %s", method, path)
        except Exception as e:
            logger.warning("failed to register %s %s: %s", method, route, e)

    return app
