import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.commands.analyse import _get_latest_enrichment
from reheat.commands.runs import _resolve_run
from reheat.registry import Payload, Resource, command
from reheat.state import (ENRICHMENTS_TABLE, PROJECTIONS_TABLE, Enrichment,
                          ProjectionData, get_user, get_user_id)

logger = logging.getLogger(__name__)


@command(help="Compute and cache embedding projection")
def cmd_project_create(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    method: Payload[str] = "",
) -> dict:
    from reheat.pipeline.transform import reduce_embeddings

    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)
    method = method or user.projection_method

    embed_enrichment = _get_latest_enrichment(backend, run.run_id, "embeddings")
    if embed_enrichment is None:
        raise ValueError("no embeddings -- run: reheat enrich embed")

    embeddings = embed_enrichment.data.get("embeddings", [])
    adjacent_embeddings = embed_enrichment.data.get("adjacent_embeddings", [])

    seed_coords, adjacent_coords = reduce_embeddings(
        embeddings=embeddings,
        adjacent_embeddings=adjacent_embeddings,
        method=method,
    )

    backend.save(PROJECTIONS_TABLE, ProjectionData(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        method=method,
        embedding_model=user.embedding_model,
        seed_coords=seed_coords,
        adjacent_coords=adjacent_coords,
        created_at=datetime.now(timezone.utc),
    ))

    return {
        "run_id":   run.run_id,
        "method":   method,
        "seeds":    len(seed_coords),
        "adjacent": len(adjacent_coords),
    }


@command(help="Read cached projection metadata")
def cmd_project_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
    method: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)
    method = method or user.projection_method

    projection = backend.get(
        PROJECTIONS_TABLE, ProjectionData,
        user_id=get_user_id(backend), run_id=run.run_id, method=method,
    )
    if projection is None:
        raise ValueError(
            f"no {method} projection for run {run.run_id} -- "
            "run: reheat project create"
        )
    return {
        "run_id":          projection.run_id,
        "method":          projection.method,
        "embedding_model": projection.embedding_model,
        "seed_count":      len(projection.seed_coords),
        "adjacent_count":  len(projection.adjacent_coords),
        "created_at":      projection.created_at.isoformat() if projection.created_at else None,
    }
