import logging
from typing import Optional

from dynawrap.backends.base import DBBackend

from reheat.registry import command, Payload
from reheat.state import (
    get_user,
    ENRICHMENTS_TABLE,
    MODELS_TABLE,
    PROJECTIONS_TABLE,
    REPORTS_TABLE,
)
from reheat.state.execution import (
    Enrichment,
    RunModels,
    ModelRuns,
    ModelClusterMetric,
    ClusterModel,
    ProjectionData,
    ScatterData,
    SummaryData,
    CoverageData,
)
from reheat.commands.runs import _resolve_run
from reheat.state import get_user_id

logger = logging.getLogger(__name__)

_PIPELINE_STAGES = ["adjacent", "tags", "embeddings", "summaries", "opportunities"]
_REQUIRED_STAGES = ["adjacent", "embeddings"]


def _enrichment_summary(e: Enrichment) -> dict:
    """Extract a compact summary from an Enrichment record."""
    data = e.data
    detail = {}

    if e.enrichment_type == "adjacent":
        queries = data.get("queries", {})
        enriched = sum(1 for v in queries.values() if v.get("paa") or v.get("related"))
        detail = {"seeds_queried": len(queries), "seeds_enriched": enriched}

    elif e.enrichment_type == "tags":
        tags = data.get("tags", {})
        detail = {"tagged": len(tags)}

    elif e.enrichment_type == "embeddings":
        detail = {
            "seed_count": len(data.get("embeddings", [])),
            "adjacent_count": len(data.get("adjacent_embeddings", [])),
        }

    elif e.enrichment_type == "summaries":
        detail = {"labelled": len(data.get("summaries", []))}

    elif e.enrichment_type == "opportunities":
        detail = {"opportunities": len(data.get("opportunities", []))}

    return {
        "present": True,
        "layer": e.layer,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        **detail,
    }


def _absent() -> dict:
    return {"present": False}


@command(help="Show pipeline status and data health for a run")
def cmd_runs_status(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
) -> dict:
    """
    Report the current pipeline state for a run.

    Queries enrichments, cluster models, projections, and report datasets
    and returns a single structured summary. The next_step field names the
    first required pipeline stage that has not yet been completed.

    Defaults to the most recent run if run_id is omitted.
    """
    run = _resolve_run(backend, run_id or None)

    # --- enrichments ---
    enrichment_records = {
        e.enrichment_type: e
        for e in backend.query(
            ENRICHMENTS_TABLE, Enrichment,
            user_id=get_user_id(), run_id=run.run_id,
        )
    }
    pipeline = {
        stage: (
            _enrichment_summary(enrichment_records[stage])
            if stage in enrichment_records
            else _absent()
        )
        for stage in _PIPELINE_STAGES
    }

    # --- models ---
    run_model_links = list(backend.query(
        MODELS_TABLE, RunModels,
        user_id=get_user_id(), run_id=run.run_id,
    ))

    models = []
    for link in sorted(run_model_links, key=lambda l: l.model_id):
        model = backend.get(
            MODELS_TABLE, ClusterModel,
            user_id=get_user_id(), model_id=link.model_id,
        )
        if model is None:
            continue
        metrics = list(backend.query(
            MODELS_TABLE, ModelClusterMetric,
            user_id=get_user_id(), model_id=link.model_id,
        ))
        models.append({
            "model_id":     model.model_id,
            "k":            model.k,
            "algorithm":    model.algorithm,
            "labels_count": len(model.labels),
            "applied_at":   link.applied_at.isoformat() if link.applied_at else None,
            "metric_count": len(metrics),
        })

    # --- projections ---
    projections = [
        {
            "method":         p.method,
            "seed_count":     len(p.seed_coords),
            "adjacent_count": len(p.adjacent_coords),
            "created_at":     p.created_at.isoformat() if p.created_at else None,
        }
        for p in backend.query(
            PROJECTIONS_TABLE, ProjectionData,
            user_id=get_user_id(), run_id=run.run_id,
        )
    ]

    # --- report datasets ---
    def _present(record) -> dict:
        return {"present": record is not None}

    scatter  = backend.get(REPORTS_TABLE, ScatterData,  user_id=get_user_id(), run_id=run.run_id)
    summary  = backend.get(REPORTS_TABLE, SummaryData,  user_id=get_user_id(), run_id=run.run_id)
    coverage = backend.get(REPORTS_TABLE, CoverageData, user_id=get_user_id(), run_id=run.run_id)

    report = {
        "scatter":  _present(scatter),
        "summary":  _present(summary),
        "coverage": _present(coverage),
    }

    # --- next step ---
    next_step = None
    if not pipeline["adjacent"]["present"]:
        next_step = "reheat enrich adjacent"
    elif not pipeline["embeddings"]["present"]:
        next_step = "reheat enrich embed"
    elif not models:
        next_step = "reheat enrich cluster"
    elif not projections:
        next_step = "reheat project create"
    elif not report["scatter"]["present"]:
        next_step = "reheat report scatter create"

    return {
        "run_id":     run.run_id,
        "domain":     run.domain,
        "source_id":  run.source_id or "",
        "fetched_at": run.fetched_at.isoformat() if run.fetched_at else None,
        "query_count": len(run.queries),
        "pipeline":   pipeline,
        "models":     models,
        "projections": projections,
        "report":     report,
        "next_step":  next_step,
    }
