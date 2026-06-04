from dynawrap.backends.base import DBBackend

from reheat.registry import command, Resource
from reheat.state.execution import Enrichment
from reheat.commands.runs import _resolve_run
from reheat.state import ENRICHMENTS_TABLE, get_user_id


@command(help="List enrichments for a run")
def cmd_enrichments_list(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> list:
    run = _resolve_run(backend, run_id or None)
    enrichments = list(backend.query(
        ENRICHMENTS_TABLE, Enrichment, user_id=get_user_id(backend), run_id=run.run_id
    ))
    return [{
        "enrichment_type": e.enrichment_type,
        "layer":           e.layer,
        "derived_from":    e.derived_from,
        "created_at":      e.created_at.isoformat() if e.created_at else None,
    } for e in sorted(enrichments, key=lambda e: e.created_at or "")]


@command(help="Show enrichment data")
def cmd_enrichments_show(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
    enrichment_type: Resource[str] = "",
) -> dict:
    if not enrichment_type:
        raise ValueError("enrichment_type is required")
    run = _resolve_run(backend, run_id or None)
    enrichment = backend.get(
        ENRICHMENTS_TABLE, Enrichment,
        user_id=get_user_id(backend), run_id=run.run_id, enrichment_type=enrichment_type,
    )
    if enrichment is None:
        raise ValueError(
            f"enrichment {enrichment_type!r} not found for run {run.run_id}"
        )
    return {
        "run_id":          run.run_id,
        "enrichment_type": enrichment.enrichment_type,
        "layer":           enrichment.layer,
        "derived_from":    enrichment.derived_from,
        "created_at":      enrichment.created_at.isoformat() if enrichment.created_at else None,
        "data":            enrichment.data,
    }


@command(help="Delete an enrichment")
def cmd_enrichments_delete(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
    enrichment_type: Resource[str] = "",
) -> dict:
    if not enrichment_type:
        raise ValueError("enrichment_type is required")
    run = _resolve_run(backend, run_id or None)
    enrichment = backend.get(
        ENRICHMENTS_TABLE, Enrichment,
        user_id=get_user_id(backend), run_id=run.run_id, enrichment_type=enrichment_type,
    )
    if enrichment is None:
        raise ValueError(f"enrichment {enrichment_type!r} not found")
    backend.delete(ENRICHMENTS_TABLE, enrichment)
    return {
        "deleted":         True,
        "run_id":          run.run_id,
        "enrichment_type": enrichment_type,
    }
