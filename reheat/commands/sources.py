import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.registry import command, Resource, Payload
from reheat.state.execution import SourceConfig
from reheat.state import get_user, get_user_id, SOURCES_TABLE, USER_TABLE

logger = logging.getLogger(__name__)


def _source_id(source_type: str, domain: str) -> str:
    return f"{source_type}:{domain}".replace("/", "-").replace(".", "-")


@command(help="Configure a new data source")
def cmd_sources_create(
    backend: DBBackend,
    *,
    source_type: Payload[str] = "",
    domain: Payload[str] = "",
    client_secrets_path: Payload[str] = "",
    token_path: Payload[str] = "",
    api_key: Payload[str] = "",
    days: Payload[int] = 90,
    limit: Payload[int] = 200,
    delay: Payload[float] = 0.5,
) -> dict:
    if not source_type:
        raise ValueError("source_type is required")

    user = get_user(backend)
    domain = domain or user.default_source_id
    source_id = _source_id(source_type, domain)

    credentials = {}
    settings = {}

    if source_type == "google_search_console":
        if not client_secrets_path:
            raise ValueError("client_secrets_path is required for google_search_console")
        credentials = {
            "client_secrets_path": client_secrets_path,
            "token_path": token_path or str(
                __import__("pathlib").Path.home() / ".reheat" / "gsc_token.json"
            ),
        }
        settings = {"days": days, "limit": limit}

    elif source_type == "serp":
        if not api_key:
            raise ValueError("api_key is required for serp")
        credentials = {"api_key": api_key}
        settings = {"delay": delay, "limit": limit}

    else:
        raise ValueError(
            f"unknown source type {source_type!r}. "
            "Available: google_search_console, serp"
        )

    source = SourceConfig(
        user_id=get_user_id(backend),
        source_id=source_id,
        source_type=source_type,
        domain=domain,
        credentials=credentials,
        settings=settings,
        created_at=datetime.now(timezone.utc),
    )
    backend.save(SOURCES_TABLE, source)

    if not user.default_source_id and source_type == "google_search_console":
        user.default_source_id = source_id
        backend.save(USER_TABLE, user)

    return {
        "source_id":   source_id,
        "source_type": source_type,
        "domain":      domain,
    }


@command(help="List configured sources")
def cmd_sources_list(backend: DBBackend) -> list:
    return [{
        "source_id":   s.source_id,
        "source_type": s.source_type,
        "domain":      s.domain,
        "created_at":  s.created_at.isoformat() if s.created_at else None,
    } for s in backend.query(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend))]


@command(help="Show source configuration")
def cmd_sources_show(
    backend: DBBackend,
    *,
    source_id: Resource[str] = "",
) -> dict:
    if not source_id:
        raise ValueError("source_id is required")
    source = backend.get(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend), source_id=source_id)
    if source is None:
        raise ValueError(f"source {source_id!r} not found")
    return {
        "source_id":   source.source_id,
        "source_type": source.source_type,
        "domain":      source.domain,
        "credentials": {k: "[set]" if v else "" for k, v in source.credentials.items()},
        "settings":    source.settings,
        "created_at":  source.created_at.isoformat() if source.created_at else None,
    }


@command(help="Update source settings")
def cmd_sources_update(
    backend: DBBackend,
    *,
    source_id: Payload[str] = "",
    domain: Payload[str] = "",
    days: Payload[int] = 0,
    limit: Payload[int] = 0,
    delay: Payload[float] = 0.0,
) -> dict:
    if not source_id:
        raise ValueError("source_id is required")
    source = backend.get(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend), source_id=source_id)
    if source is None:
        raise ValueError(f"source {source_id!r} not found")

    if domain:
        source.domain = domain
    if days:
        source.settings["days"] = days
    if limit:
        source.settings["limit"] = limit
    if delay:
        source.settings["delay"] = delay

    backend.save(SOURCES_TABLE, source)
    return {"source_id": source_id, "updated": True}


@command(help="Delete a source configuration")
def cmd_sources_delete(
    backend: DBBackend,
    *,
    source_id: Resource[str] = "",
) -> dict:
    if not source_id:
        raise ValueError("source_id is required")
    source = backend.get(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend), source_id=source_id)
    if source is None:
        raise ValueError(f"source {source_id!r} not found")
    backend.delete(SOURCES_TABLE, source)
    return {"source_id": source_id, "deleted": True}


@command(help="Authenticate a Google Search Console source", interactive_only=True)
def cmd_sources_auth(
    backend: DBBackend,
    *,
    source_id: Payload[str] = "",
) -> dict:
    if not source_id:
        sources = list(backend.query(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend)))
        gsc = [s for s in sources if s.source_type == "google_search_console"]
        if not gsc:
            raise ValueError(
                "no google_search_console source configured. "
                "Run: reheat sources create --source-type google_search_console"
            )
        source_id = gsc[0].source_id

    source = backend.get(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend), source_id=source_id)
    if source is None:
        raise ValueError(f"source {source_id!r} not found")

    from reheat.sources.google_search_console import _build_service
    _build_service(
        client_secrets_path=source.credentials["client_secrets_path"],
        token_path=source.credentials["token_path"],
    )
    return {"source_id": source_id, "authenticated": True}
