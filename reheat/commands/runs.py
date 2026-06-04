import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.registry import command, Resource, Payload
from reheat.state.execution import RunRecord, SourceConfig
from reheat.state import RUNS_TABLE, SOURCES_TABLE, get_user, get_user_id

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
