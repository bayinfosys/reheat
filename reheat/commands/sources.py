import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.registry import Payload, Resource, command
from reheat.state import (SOURCES_TABLE, USER_TABLE, SourceConfig, get_user,
                          get_user_id)

logger = logging.getLogger(__name__)


def _source_id(source_type: str, domain: str) -> str:
    return f"{source_type}:{domain}".replace("/", "-").replace(".", "-")


@command(help="Configure a new data source")
def cmd_sources_create(
    backend: DBBackend,
    *,
    source_type: Payload[str] = "",
    domain: Payload[str] = "",
    days: Payload[int] = 90,
    limit: Payload[int] = 200,
    delay: Payload[float] = 0.5,
) -> dict:
    if not source_type:
        raise ValueError("source_type is required")

    user = get_user(backend)

    if source_type == "google_search_console":
        domain = domain or user.default_source_id
        settings = {"days": days, "limit": limit}

    elif source_type == "serp":
        domain = domain or "google"
        settings = {"delay": delay, "limit": limit}

    else:
        raise ValueError(
            f"unknown source type {source_type!r}. "
            "Available: google_search_console, serp"
        )

    source_id = _source_id(source_type, domain)

    source = SourceConfig(
        user_id=get_user_id(backend),
        source_id=source_id,
        source_type=source_type,
        domain=domain,
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
