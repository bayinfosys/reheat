import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.commands.analyse import (_get_latest_enrichment, get_user,
                                     load_assignments, resolve_model_id)
from reheat.commands.enrich import _get_adjacent_data
from reheat.commands.runs import _resolve_run
from reheat.registry import Payload, Resource, command
from reheat.state import (PROJECTIONS_TABLE, REPORTS_TABLE, CoverageData,
                          ProjectionData, ScatterData, SummaryData,
                          get_user_id)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@command(help="Build and cache scatter plot data")
def cmd_report_scatter_create(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    method: Payload[str] = "",
) -> dict:
    from reheat.pipeline.report import build_scatter_data

    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)
    method = method or user.projection_method

    projection = backend.get(
        PROJECTIONS_TABLE, ProjectionData,
        user_id=get_user_id(backend), run_id=run.run_id, method=method,
    )
    if projection is None:
        raise ValueError("no projection found -- run: reheat project create")

    embed_enrichment = _get_latest_enrichment(backend, run.run_id, "embeddings")
    if embed_enrichment is None:
        raise ValueError("no embeddings found -- run: reheat enrich embed")

    mid = resolve_model_id(backend, run.run_id)
    all_assignments = load_assignments(backend, run.run_id, mid)

    seed_assignments     = [a for a in all_assignments if not a.get("is_adjacent", False)]
    adjacent_assignments = [a for a in all_assignments if a.get("is_adjacent", False)]

    summaries_enrichment = _get_latest_enrichment(backend, run.run_id, "summaries")
    summaries = summaries_enrichment.data.get("summaries", []) if summaries_enrichment else []

    datasets = build_scatter_data(
        embeddings=embed_enrichment.data.get("embeddings", []),
        seed_coords=projection.seed_coords,
        assignments=seed_assignments,
        adjacent_embeddings=embed_enrichment.data.get("adjacent_embeddings", []),
        adjacent_coords=projection.adjacent_coords,
        adjacent_assignments=adjacent_assignments,
        summaries=summaries,
    )

    backend.save(REPORTS_TABLE, ScatterData(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        datasets=datasets,
        created_at=datetime.now(timezone.utc),
    ))
    return {"run_id": run.run_id, "datasets": len(datasets)}


@command(help="Read cached scatter plot data")
def cmd_report_scatter_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    scatter = backend.get(REPORTS_TABLE, ScatterData, user_id=get_user_id(backend), run_id=run.run_id)
    if scatter is None:
        raise ValueError("no scatter data -- run: reheat report scatter create")
    return {"datasets": scatter.datasets}


@command(help="Build and cache summary panel data")
def cmd_report_summary_create(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
) -> dict:
    from reheat.pipeline.report import build_summary_data

    run = _resolve_run(backend, run_id or None)

    adjacent_data = _get_adjacent_data(backend, run.run_id)
    opps = _get_latest_enrichment(backend, run.run_id, "opportunities")

    mid = resolve_model_id(backend, run.run_id)
    all_assignments = load_assignments(backend, run.run_id, mid)
    seed_assignments = [a for a in all_assignments if not a.get("is_adjacent", False)]

    data = build_summary_data(
        run=run,
        adjacent_data=adjacent_data,
        assignments=seed_assignments,
        opportunities=opps.data.get("opportunities", []) if opps else [],
    )

    backend.save(REPORTS_TABLE, SummaryData(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        created_at=datetime.now(timezone.utc),
        **data,
    ))
    return {"run_id": run.run_id, "created": True}


@command(help="Read cached summary panel data")
def cmd_report_summary_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    summary = backend.get(REPORTS_TABLE, SummaryData, user_id=get_user_id(backend), run_id=run.run_id)
    if summary is None:
        raise ValueError("no summary data -- run: reheat report summary create")
    return {
        "top_performing":       summary.top_performing,
        "top_clusters":         summary.top_clusters,
        "missed_opportunities": summary.missed_opportunities,
        "new_opportunities":    summary.new_opportunities,
    }


@command(help="Build and cache coverage table data")
def cmd_report_coverage_create(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    queries = sorted(run.queries, key=lambda q: q.impressions, reverse=True)[:100]
    backend.save(REPORTS_TABLE, CoverageData(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        queries=[q.model_dump() for q in queries],
        created_at=datetime.now(timezone.utc),
    ))
    return {"run_id": run.run_id, "queries": len(queries)}


@command(help="Read cached coverage table data")
def cmd_report_coverage_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    coverage = backend.get(REPORTS_TABLE, CoverageData, user_id=get_user_id(backend), run_id=run.run_id)
    if coverage is None:
        raise ValueError("no coverage data -- run: reheat report coverage create")
    return {"queries": coverage.queries}


@command(help="Read ranked opportunities")
def cmd_report_opportunities_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    enrichment = _get_latest_enrichment(backend, run.run_id, "opportunities")
    if enrichment is None:
        raise ValueError("no opportunities -- run: reheat analyse opportunities")
    return {"opportunities": enrichment.data.get("opportunities", [])}


@command(help="Read overlapping gaps")
def cmd_report_overlaps_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    enrichment = _get_latest_enrichment(backend, run.run_id, "opportunities")
    if enrichment is None:
        raise ValueError("no opportunities enrichment -- run: reheat analyse opportunities")
    return {"overlapping_gaps": enrichment.data.get("overlapping_gaps", [])}


@command(help="Read content schedule and narrative overview")
def cmd_report_schedule_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    enrichment = _get_latest_enrichment(backend, run.run_id, "schedule")
    if enrichment is None:
        raise ValueError("no schedule -- run: reheat analyse schedule")
    return {
        "overview": enrichment.data.get("overview", {}),
        "schedule": enrichment.data.get("schedule", []),
    }


@command(help="Read narrative overview")
def cmd_report_overview_read(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    enrichment = _get_latest_enrichment(backend, run.run_id, "overview")
    if enrichment is None:
        raise ValueError("no overview -- run: reheat analyse overview")
    return {"paragraphs": enrichment.data.get("paragraphs", [])}
