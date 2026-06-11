import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.registry import Payload, Resource, command
from reheat.state import (ENRICHMENTS_TABLE, MODELS_TABLE, PROJECTIONS_TABLE,
                          REPORTS_TABLE, RUNS_TABLE, SOURCES_TABLE,
                          ClusterAssignments, CoverageData, Enrichment,
                          ProjectionData, RunModels, RunRecord, ScatterData,
                          SourceConfig, SummaryData, get_user, get_user_id)

logger = logging.getLogger(__name__)


def _resolve_run(backend: DBBackend, run_id: str = None) -> RunRecord:
    if run_id:
        run = backend.get(RUNS_TABLE, RunRecord, user_id=get_user_id(backend), run_id=run_id)
        if run is None:
            raise ValueError(f"run {run_id!r} not found")
        return run
    runs = sorted(
        backend.query(RUNS_TABLE, RunRecord, user_id=get_user_id(backend)),
        key=lambda r: r.run_id,
    )
    if not runs:
        raise ValueError("no runs found -- run: reheat runs create")
    return runs[-1]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@command(help="Fetch queries from configured source and create a new run")
def cmd_runs_create(
    backend: DBBackend,
    *,
    source_id: Payload[str] = "",
    headless: Payload[bool] = False,
) -> dict:
    """
    Stage 1: raw download.

    Fetches queries from the configured source (Google Search Console or
    other providers) and persists a RunRecord. No third-party enrichment
    is performed here.

    Run `reheat enrich adjacent` after this step to fetch PAA and
    related-search data from SerpAPI.
    """
    from reheat.sources import get_source_provider

    user = get_user(backend)
    sid = source_id or user.default_source_id
    if not sid:
        raise ValueError(
            "no source configured. "
            "Run: reheat sources create --source-type google_search_console"
        )

    source = backend.get(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend), source_id=sid)
    if source is None:
        raise ValueError(f"source {sid!r} not found")

    provider = get_source_provider(source)
    queries = provider.fetch()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = RunRecord(
        user_id=get_user_id(backend),
        run_id=run_id,
        domain=source.domain,
        source_id=sid,
        queries=queries,
        fetched_at=datetime.now(timezone.utc),
    )
    backend.save(RUNS_TABLE, run)
    logger.info("created run %s with %d queries", run_id, len(queries))

    return {
        "run_id":      run_id,
        "domain":      source.domain,
        "query_count": len(queries),
    }


@command(help="List all runs")
def cmd_runs_list(
    backend: DBBackend,
    *,
    limit: int = 10,
) -> list:
    runs = sorted(
        backend.query(RUNS_TABLE, RunRecord, user_id=get_user_id(backend)),
        key=lambda r: r.run_id,
        reverse=True,
    )[:limit]
    return [
        {
            "run_id":       r.run_id,
            "domain":       r.domain,
            "source_id":    r.source_id or "",
            "query_count":  len(r.queries),
            "fetched_at":   r.fetched_at.isoformat() if r.fetched_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@command(help="Show run detail and query list")
def cmd_runs_show(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    return {
        "run_id":      run.run_id,
        "domain":      run.domain,
        "source_id":   run.source_id or "",
        "fetched_at":  run.fetched_at.isoformat() if run.fetched_at else None,
        "query_count": len(run.queries),
        "queries":     [q.model_dump() for q in run.queries],
    }


@command(help="Delete a run and all associated enrichments and reports")
def cmd_runs_delete(
    backend: DBBackend,
    *,
    run_id: Resource[str] = "",
) -> dict:
    """
    Deletes the RunRecord and all records derived from it:
    enrichments, cluster assignments, run-model links,
    projections, and report data.

    ClusterModel records are not deleted as they may be
    referenced by other runs.
    """
    run = _resolve_run(backend, run_id or None)
    rid = run.run_id
    uid = get_user_id(backend)
    deleted = {
        "enrichments":        0,
        "run_model_links":    0,
        "cluster_assignments": 0,
        "projections":        0,
    }

    # enrichments
    for e in backend.query(ENRICHMENTS_TABLE, Enrichment, user_id=uid, run_id=rid):
        backend.delete(ENRICHMENTS_TABLE, e)
        deleted["enrichments"] += 1

    # run-model adjacency links -- extract model_ids before deleting
    run_models = list(backend.query(MODELS_TABLE, RunModels, user_id=uid, run_id=rid))
    model_ids = [rm.model_id for rm in run_models]

    # cluster assignments must be queried by model_id, not run_id
    for model_id in model_ids:
        for a in backend.query(MODELS_TABLE, ClusterAssignments, user_id=uid, model_id=model_id):
            backend.delete(MODELS_TABLE, a)
            deleted["cluster_assignments"] += 1

    for rm in run_models:
        backend.delete(MODELS_TABLE, rm)
    deleted["run_model_links"] = len(run_models)

    # projections
    for p in backend.query(PROJECTIONS_TABLE, ProjectionData, user_id=uid, run_id=rid):
        backend.delete(PROJECTIONS_TABLE, p)
        deleted["projections"] += 1

    # reports
    for model_cls, label in (
        (ScatterData,  "scatter"),
        (SummaryData,  "summary"),
        (CoverageData, "coverage"),
    ):
        record = backend.get(REPORTS_TABLE, model_cls, user_id=uid, run_id=rid)
        if record is not None:
            backend.delete(REPORTS_TABLE, record)
            deleted[label] = True

    # run record last
    backend.delete(RUNS_TABLE, run)

    logger.info("deleted run %s: %s", rid, deleted)
    return {"deleted": True, "run_id": rid, **deleted}
