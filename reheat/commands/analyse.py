import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.registry import command, Payload
from reheat.state.execution import (
    Enrichment,
    ClusterModel,
    ClusterAssignments,
    RunModels,
)
from reheat.state import ENRICHMENTS_TABLE, MODELS_TABLE, get_user, get_user_id
from reheat.commands.runs import _resolve_run

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers -- public so report.py can import them
# ---------------------------------------------------------------------------


def get_enrichment(backend: DBBackend, run_id: str, enrichment_type: str):
    return backend.get(
        ENRICHMENTS_TABLE, Enrichment,
        user_id=get_user_id(backend), run_id=run_id, enrichment_type=enrichment_type,
    )


def resolve_model_id(backend: DBBackend, run_id: str) -> str:
    """
    Return the model_id of the most recently applied ClusterModel for
    this run, using the RunModels adjacency index.

    Raises ValueError if no model has been applied to this run.
    """
    links = sorted(
        backend.query(MODELS_TABLE, RunModels, user_id=get_user_id(backend), run_id=run_id),
        key=lambda link: link.model_id,
    )
    if not links:
        raise ValueError(
            f"no cluster model applied to run {run_id!r} -- "
            "run: reheat enrich cluster"
        )
    return links[-1].model_id


def load_assignments(backend: DBBackend, run_id: str, model_id: str) -> list:
    """
    Load ClusterAssignments for a (run, model) pair and return the raw
    assignment dict list. Raises if the record is not found.
    """
    record = backend.get(
        MODELS_TABLE, ClusterAssignments,
        user_id=get_user_id(backend), model_id=model_id, run_id=run_id,
    )
    if record is None:
        raise ValueError(
            f"no cluster assignments for run {run_id!r} "
            f"under model {model_id!r}"
        )
    return record.assignments


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@command(help="Label clusters with natural language summaries")
def cmd_analyse_summarise(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    model_id: Payload[str] = "",
    cluster_id: Payload[int] = 0,
    top_n: Payload[int] = 0,
) -> dict:
    """
    Generate natural language labels for each cluster using the configured
    LLM provider. Labels are stored in the 'summaries' Enrichment record
    and written back to ClusterModel.labels via read-modify-write so that
    reports and the UI can reference them without loading the full enrichment.

    If --model is omitted the most recently applied model for the run is used.
    """
    from reheat.pipeline.summarise import summarise_all
    from reheat.pipeline.cluster import ClusterAssignment

    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)

    mid = model_id or resolve_model_id(backend, run.run_id)
    assignment_dicts = load_assignments(backend, run.run_id, mid)

    if top_n:
        user = user.model_copy(update={"summarise_top_n": top_n})

    assignments = [ClusterAssignment(**a) for a in assignment_dicts]

    summaries = summarise_all(
        assignments=assignments,
        records=run.queries,
        user=user,
        cluster_id=cluster_id or None,
    )

    backend.save(ENRICHMENTS_TABLE, Enrichment(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        enrichment_type="summaries",
        layer="gold",
        data={"summaries": [s.model_dump() for s in summaries]},
        derived_from=["adjacent", "cluster_assignments"],
        created_at=datetime.now(timezone.utc),
    ))

    model = backend.get(
        MODELS_TABLE, ClusterModel, user_id=get_user_id(backend), model_id=mid,
    )
    if model is not None:
        updated_labels = {
            **model.labels,
            **{str(s.cluster_id): s.label for s in summaries if s.label},
        }
        backend.save(MODELS_TABLE, model.model_copy(update={"labels": updated_labels}))

    return {
        "run_id":    run.run_id,
        "model_id":  mid,
        "labelled":  len(summaries),
        "summaries": [
            {
                "cluster_id":  s.cluster_id,
                "label":       s.label,
                "description": s.description,
                "query_count": s.query_count,
            }
            for s in summaries
        ],
    }


@command(help="Rank content opportunities from adjacent query analysis")
def cmd_analyse_opportunities(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    model_id: Payload[str] = "",
) -> dict:
    from reheat.pipeline.gap import (
        owned_set,
        adjacent_map,
        opportunity_scores,
        overlapping_gaps,
        gaps_per_seed,
    )
    SCORE_THRESHOLD = 5

    run = _resolve_run(backend, run_id or None)

    adjacent_enrichment = get_enrichment(backend, run.run_id, "adjacent")
    if adjacent_enrichment is None:
        raise ValueError(
            "no adjacent enrichment found -- run: reheat enrich adjacent"
        )

    mid = model_id or resolve_model_id(backend, run.run_id)
    assignment_dicts = load_assignments(backend, run.run_id, mid)

    query_to_cluster = {
        a["query"].lower(): a["cluster_id"]
        for a in assignment_dicts
        if not a.get("is_adjacent", False)
    }

    owned = owned_set(run.queries)
    adjacent = adjacent_map(adjacent_enrichment.data)
    impressions = {q.query: q.impressions for q in run.queries}

    opportunities = opportunity_scores(owned, adjacent, impressions)
    overlaps = overlapping_gaps(owned, adjacent)
    gaps = gaps_per_seed(owned, adjacent)

    ranked = []
    for query, score, seeds in opportunities:
        if score < SCORE_THRESHOLD:
            continue
        cluster_ids = list({
            query_to_cluster[s.lower()]
            for s in seeds
            if s.lower() in query_to_cluster
        })
        recommendation = "expand existing content" if cluster_ids else "new content"
        top_seed = max(seeds, key=lambda s: impressions.get(s, 0))
        ranked.append({
            "query":          query,
            "score":          score,
            "seeds":          seeds,
            "top_seed":       top_seed,
            "cluster_ids":    cluster_ids,
            "recommendation": recommendation,
        })

    backend.save(ENRICHMENTS_TABLE, Enrichment(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        enrichment_type="opportunities",
        layer="gold",
        data={
            "opportunities":    ranked,
            "overlapping_gaps": [
                {"query": q, "seed_count": c, "seeds": s}
                for q, c, s in overlaps
            ],
            "gaps_per_seed":    gaps,
        },
        derived_from=["adjacent", "cluster_assignments"],
        created_at=datetime.now(timezone.utc),
    ))

    logger.info(
        "opportunities: %d ranked above threshold (score >= %d)",
        len(ranked), SCORE_THRESHOLD,
    )

    return {
        "run_id":        run.run_id,
        "model_id":      mid,
        "opportunities": len(ranked),
        "top":           ranked[:10],
    }
