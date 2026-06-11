import logging
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.commands.runs import _resolve_run
from reheat.registry import Payload, command
from reheat.state import (ENRICHMENTS_TABLE, MODELS_TABLE, ClusterAssignments,
                          ClusterModel, Enrichment, RunModels, get_user,
                          get_user_id)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers -- public so report.py can import them
# ---------------------------------------------------------------------------

def _get_latest_enrichment(backend: DBBackend, run_id: str, enrichment_type: str):
    """Return the most recently created enrichment of the given type, any source."""
    results = list(backend.query(
        ENRICHMENTS_TABLE, Enrichment,
        user_id=get_user_id(backend),
        run_id=run_id,
        enrichment_type=enrichment_type,
    ))
    if not results:
        return None
    return max(results, key=lambda e: e.created_at or "")



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
    from reheat.pipeline.cluster import ClusterAssignment
    from reheat.pipeline.summarise import summarise_all

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
    from reheat.commands.enrich import _get_adjacent_data
    from reheat.pipeline.gap import (adjacent_map, gaps_per_seed,
                                     opportunity_scores, overlapping_gaps,
                                     owned_set)

    SCORE_THRESHOLD = 5

    run = _resolve_run(backend, run_id or None)

    adjacent_data = _get_adjacent_data(backend, run.run_id)
    if not adjacent_data:
        logger.warning(
            "no adjacent enrichment found -- opportunities will be based on "
            "seed queries only. Run reheat enrich adjacent to include PAA "
            "and related search data."
        )

    mid = model_id or resolve_model_id(backend, run.run_id)
    assignment_dicts = load_assignments(backend, run.run_id, mid)

    query_to_cluster = {
        a["query"].lower(): a["cluster_id"]
        for a in assignment_dicts
        if not a.get("is_adjacent", False)
    }

    owned = owned_set(run.queries)
    adjacent = adjacent_map(adjacent_data)
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


@command(help="Generate content schedule from cluster and opportunity data")
def cmd_analyse_schedule(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    model_id: Payload[str] = "",
) -> dict:
    from collections import defaultdict

    from reheat.pipeline.schedule import ScheduleError, build_schedule

    run  = _resolve_run(backend, run_id or None)
    user = get_user(backend)
    uid  = get_user_id(backend)

    summaries_enrichment = _get_latest_enrichment(backend, run.run_id, "summaries")
    if summaries_enrichment is None:
        raise ValueError("no summaries -- run: reheat analyse summarise")

    opps_enrichment = _get_latest_enrichment(backend, run.run_id, "opportunities")
    if opps_enrichment is None:
        raise ValueError("no opportunities -- run: reheat analyse opportunities")

    summaries     = summaries_enrichment.data.get("summaries", [])
    opportunities = opps_enrichment.data.get("opportunities", [])
    high_value    = opps_enrichment.data.get("overlapping_gaps", [])

    mid             = model_id or resolve_model_id(backend, run.run_id)
    all_assignments = load_assignments(backend, run.run_id, mid)
    adjacent_counts: dict = defaultdict(int)
    for a in all_assignments:
        if a.get("is_adjacent", False):
            adjacent_counts[a["cluster_id"]] += 1

    for s in summaries:
        s["adjacent_count"] = adjacent_counts.get(s["cluster_id"], 0)

    impressions = sum(q.impressions for q in run.queries)

    try:
        result = build_schedule(
            domain=run.domain,
            query_count=len(run.queries),
            impressions=impressions,
            summaries=summaries,
            opportunities=opportunities,
            high_value_topics=high_value,
            user=user,
        )
    except ScheduleError as e:
        raise ValueError(str(e)) from e

    label_stats = {
        s["label"]: {
            "adjacent_count":    s.get("adjacent_count", 0),
            "total_impressions": s.get("total_impressions", 0),
        }
        for s in summaries
    }
    for item in result.get("schedule", []):
        stats = label_stats.get(item.get("cluster_label"), {})
        item["adjacent_count"] = stats.get("adjacent_count", 0)
        item["impressions"]    = stats.get("total_impressions", 0)

    backend.save(ENRICHMENTS_TABLE, Enrichment(
        user_id=uid,
        run_id=run.run_id,
        enrichment_type="schedule",
        layer="gold",
        data=result,
        derived_from=["summaries", "opportunities"],
        created_at=datetime.now(timezone.utc),
    ))

    return {
        "run_id":    run.run_id,
        "scheduled": len(result.get("schedule", [])),
    }


@command(help="Generate narrative overview from cluster and schedule data")
def cmd_analyse_overview(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
) -> dict:
    from reheat.pipeline.schedule import ScheduleError, build_overview

    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)

    summaries_enrichment = _get_latest_enrichment(backend, run.run_id, "summaries")
    if summaries_enrichment is None:
        raise ValueError("no summaries -- run: reheat analyse summarise")

    schedule_enrichment = _get_latest_enrichment(backend, run.run_id, "schedule")
    if schedule_enrichment is None:
        raise ValueError("no schedule -- run: reheat analyse schedule")

    summaries   = summaries_enrichment.data.get("summaries", [])
    schedule    = schedule_enrichment.data.get("schedule", [])
    impressions = sum(q.impressions for q in run.queries)

    try:
        result = build_overview(
            domain=run.domain,
            query_count=len(run.queries),
            impressions=impressions,
            summaries=summaries,
            schedule=schedule,
            user=user,
        )
    except ScheduleError as e:
        raise ValueError(str(e)) from e

    backend.save(ENRICHMENTS_TABLE, Enrichment(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        enrichment_type="overview",
        layer="gold",
        data=result,
        derived_from=["summaries", "schedule"],
        created_at=datetime.now(timezone.utc),
    ))

    return {
        "run_id":     run.run_id,
        "paragraphs": len(result),
    }
