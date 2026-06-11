import argparse
import inspect
import json
import logging
import sys
from typing import get_type_hints

from dynawrap.backends.base import DBBackend

from reheat.registry import Payload, Resource, registry


def _default_output(data, as_json: bool) -> None:
    if as_json or data is None:
        print(json.dumps(data, indent=2, default=str))
        return
    else:
        raise ValueError("only json output is supported")


def _unwrap_annotation(annotation) -> type:
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is None:
        return annotation
    if type(None) in args:
        return next(a for a in args if a is not type(None))
    if origin in (Resource, Payload):
        return args[0] if args else str
    return annotation


def _add_kwargs(p: argparse.ArgumentParser, fn) -> None:
    sig = inspect.signature(fn)
    hints = get_type_hints(fn)
    for name, param in sig.parameters.items():
        if param.kind != inspect.Parameter.KEYWORD_ONLY:
            continue
        annotation = hints.get(name, str)
        default = (
            param.default if param.default is not inspect.Parameter.empty else None
        )
        flag = "--json" if name == "as_json" else f"--{name.replace('_', '-')}"
        p.add_argument(flag, dest=name, **_param_to_argparse(annotation, default))


def _param_to_argparse(annotation, default) -> dict:
    annotation = _unwrap_annotation(annotation)
    if annotation is bool or isinstance(default, bool):
        return {"action": "store_true", "default": bool(default)}
    if annotation is int:
        return {"type": int, "default": default}
    if annotation is float:
        return {"type": float, "default": default}
    return {"type": str, "default": default}


def _build_groups() -> dict:
    """
    Build a nested group structure from the registry.
    Supports up to three levels: top.mid.leaf
    """
    groups = {}
    for path, fn in registry.items():
        parts = path.split(".")
        top = parts[0]
        mid = parts[1] if len(parts) > 1 else None
        leaf = parts[2] if len(parts) > 2 else None

        groups.setdefault(top, {"fn": None, "children": {}})

        if mid and leaf:
            groups[top]["children"].setdefault(mid, {"fn": None, "children": {}})
            if not isinstance(groups[top]["children"][mid], dict):
                groups[top]["children"][mid] = {"fn": None, "children": {}}
            groups[top]["children"][mid]["children"][leaf] = fn
        elif mid:
            if isinstance(groups[top]["children"].get(mid), dict):
                groups[top]["children"][mid]["fn"] = fn
            else:
                groups[top]["children"][mid] = {"fn": fn, "children": {}}
        else:
            groups[top]["fn"] = fn

    return groups


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reheat",
        description="Intent harvesting and market research tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", metavar="PATH_OR_URI")
    parser.add_argument("--domain", metavar="DOMAIN")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        default=True,
        help="Output as JSON (machine-readable)",
    )

    top_sub = parser.add_subparsers(dest="command", metavar="command")
    top_sub.required = True

    groups = _build_groups()

    for top, group in sorted(groups.items()):
        top_fn = group["fn"]
        children = group["children"]

        if not children:
            top_p = top_sub.add_parser(top, help=top_fn._cli_help if top_fn else "")
            if top_fn:
                _add_kwargs(top_p, top_fn)
            continue

        top_p = top_sub.add_parser(top, help=top_fn._cli_help if top_fn else "")
        if top_fn:
            _add_kwargs(top_p, top_fn)
        mid_sub = top_p.add_subparsers(dest=f"{top}_command", metavar="subcommand")
        mid_sub.required = top_fn is None

        for mid, mid_group in sorted(children.items()):
            if not isinstance(mid_group, dict):
                continue

            mid_fn = mid_group.get("fn")
            mid_children = mid_group.get("children", {})

            if not mid_children:
                mid_p = mid_sub.add_parser(mid, help=mid_fn._cli_help if mid_fn else "")
                if mid_fn:
                    _add_kwargs(mid_p, mid_fn)
                continue

            mid_p = mid_sub.add_parser(mid, help=mid_fn._cli_help if mid_fn else "")
            leaf_sub = mid_p.add_subparsers(
                dest=f"{top}_{mid}_command", metavar="subcommand"
            )
            leaf_sub.required = True

            for leaf, leaf_fn in sorted(mid_children.items()):
                leaf_p = leaf_sub.add_parser(leaf, help=leaf_fn._cli_help)
                _add_kwargs(leaf_p, leaf_fn)

    return parser


def dispatch(args: argparse.Namespace, backend: DBBackend) -> None:
    command = args.command
    mid = getattr(args, f"{command}_command", None)
    leaf = getattr(args, f"{command}_{mid}_command", None) if mid else None

    if leaf:
        path = f"{command}.{mid}.{leaf}"
    elif mid:
        path = f"{command}.{mid}"
    else:
        path = command

    fn = registry.get(path)
    if fn is None:
        logging.getLogger(__name__).error("unknown command %r", path)
        sys.exit(1)

    sig = inspect.signature(fn)
    kwargs = {
        name: getattr(args, name)
        for name, param in sig.parameters.items()
        if param.kind == inspect.Parameter.KEYWORD_ONLY and hasattr(args, name)
    }

    result = fn(backend, **kwargs)

    _default_output(result, args.as_json)
