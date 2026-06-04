import logging
from collections import defaultdict
from datetime import datetime, timezone
from collections import Counter


from dynawrap.backends.base import DBBackend

from reheat.registry import command, Payload
from reheat.state.execution import (
    Enrichment,
    ClusterModel,
    ClusterAssignments,
    ModelClusterMetric,
    ModelRunMetric,
    RunModels,
    ModelRuns,
)
from reheat.state import ENRICHMENTS_TABLE, MODELS_TABLE, SOURCES_TABLE, get_user, get_user_id
from reheat.commands.runs import _resolve_run
from reheat.pipeline.tag import tag_all
from reheat.sources.serp import SerpAPIProvider
from reheat.state.execution import SourceConfig
from reheat.pipeline.embed import embed_queries
from reheat.providers.embeddings import get_embedding_provider
from reheat.pipeline.cluster import EmbeddedQuery, fit_cluster_model, apply_cluster_model


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _get_enrichment(backend: DBBackend, run_id: str, enrichment_type: str):
    return backend.get(
        ENRICHMENTS_TABLE, Enrichment,
        user_id=get_user_id(backend), run_id=run_id, enrichment_type=enrichment_type,
    )


def _save_enrichment(backend: DBBackend, enrichment: Enrichment) -> None:
    backend.save(ENRICHMENTS_TABLE, enrichment)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _now().strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def _compute_cluster_metrics(
    assignments: list,
    queries: list,
    adjacent_data: dict,
    k: int,
) -> list:
    """
    Compute the four demand metrics per cluster from a joint set of seed
    and adjacent assignments.

    intent_demand     seed impressions + adjacent impression weights
    coverage_health   seed impressions / intent_demand
    click_quality     clicks / seed impressions  (0 if no seed impressions)
    demand_capture    clicks / intent_demand      (0 if no intent demand)
                      = coverage_health * click_quality

    Adjacent impression weight for a query is the sum of impressions of
    all seed queries that surfaced it via PAA or related search. This
    information is read from the adjacent enrichment data.

    Returns a list of dicts, one per cluster index 0..k-1.
    """
    impressions = {q.query: q.impressions for q in queries}
    clicks_map = {q.query: q.clicks for q in queries}

    # build adjacent_query -> [seed, ...] mapping from enrichment data
    adjacent_to_seeds: dict = defaultdict(list)
    for seed, data in adjacent_data.get("queries", {}).items():
        for q in data.get("paa", []) + data.get("related", []):
            if q:
                adjacent_to_seeds[q.lower()].append(seed)

    cluster_data: dict = defaultdict(lambda: {
        "seed_impressions": 0.0,
        "clicks": 0.0,
        "adjacent_weight": 0.0,
        "seed_count": 0,
        "adjacent_count": 0,
    })

    for a in assignments:
        cd = cluster_data[a["cluster_id"]]
        if not a["is_adjacent"]:
            cd["seed_impressions"] += impressions.get(a["query"], 0)
            cd["clicks"] += clicks_map.get(a["query"], 0)
            cd["seed_count"] += 1
        else:
            seeds = adjacent_to_seeds.get(a["query"].lower(), [])
            cd["adjacent_weight"] += sum(impressions.get(s, 0) for s in seeds)
            cd["adjacent_count"] += 1

    results = []
    for cluster_id in range(k):
        cd = cluster_data[cluster_id]
        seed_imp = cd["seed_impressions"]
        adj_weight = cd["adjacent_weight"]
        intent_demand = seed_imp + adj_weight
        coverage_health = seed_imp / intent_demand if intent_demand > 0 else 0.0
        click_quality = cd["clicks"] / seed_imp if seed_imp > 0 else 0.0
        demand_capture = cd["clicks"] / intent_demand if intent_demand > 0 else 0.0

        results.append({
            "cluster_id":   str(cluster_id).zfill(4),
            "intent_demand":      round(intent_demand, 4),
            "coverage_health":    round(coverage_health, 4),
            "click_quality":      round(click_quality, 4),
            "demand_capture":     round(demand_capture, 4),
            "seed_query_count":   cd["seed_count"],
            "adjacent_query_count": cd["adjacent_count"],
        })

    return results


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@command(help="Tag queries with auto-generated labels")
def cmd_enrich_tags(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
) -> dict:
    run = _resolve_run(backend, run_id or None)
    adjacent = _get_enrichment(backend, run.run_id, "adjacent")
    tags = tag_all(run.queries, adjacent_data=adjacent.data if adjacent else {})

    _save_enrichment(backend, Enrichment(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        enrichment_type="tags",
        layer="silver",
        data={"tags": tags},
        derived_from=["adjacent"],
        created_at=_now(),
    ))

    all_tags = [t for ts in tags.values() for t in ts]
    return {
        "run_id":     run.run_id,
        "tagged":     len(tags),
        "tag_counts": dict(sorted(Counter(all_tags).items())),
    }


@command(help="Fetch adjacent queries via SerpAPI (PAA and related searches)")
def cmd_enrich_adjacent(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    headless: Payload[bool] = False,
) -> dict:
    """
    Stage 2: third-party enrichment.

    Calls SerpAPI for the top queries in the run and stores PAA and
    related-search results as the 'adjacent' enrichment. This enrichment
    is consumed by cmd_enrich_embed (for joint clustering) and
    cmd_analyse_opportunities (for gap analysis).

    Requires a source of type 'serp' to be configured.
    """
    run = _resolve_run(backend, run_id or None)

    serp_sources = [
        s for s in backend.query(SOURCES_TABLE, SourceConfig, user_id=get_user_id(backend))
        if s.source_type == "serp"
    ]
    if not serp_sources:
        raise ValueError(
            "no serp source configured. "
            "Run: reheat sources create --source-type serp"
        )

    serp_source = serp_sources[0]
    serp_source.settings["headless"] = headless

    enriched_map = SerpAPIProvider(serp_source).enrich(run.queries)

    _save_enrichment(backend, Enrichment(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        enrichment_type="adjacent",
        layer="silver",
        data={"queries": enriched_map},
        derived_from=[],
        created_at=_now(),
    ))

    enriched_count = sum(
        1 for v in enriched_map.values()
        if v.get("paa") or v.get("related")
    )
    adjacent_count = sum(
        len(v.get("paa", [])) + len(v.get("related", []))
        for v in enriched_map.values()
    )
    return {
        "run_id":          run.run_id,
        "seeds_enriched":  enriched_count,
        "seeds_total":     len(enriched_map),
        "adjacent_queries": adjacent_count,
    }


@command(help="Generate embeddings for seed and adjacent queries")
def cmd_enrich_embed(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    provider: Payload[str] = "",
) -> dict:
    """
    Stage 3a: embed seed queries and adjacent queries into the same
    vector space. The adjacent enrichment is read if present; if absent,
    only seed queries are embedded.

    The embeddings enrichment produced here is the input to cmd_enrich_cluster.
    Both seed and adjacent vectors are stored together under the keys
    'embeddings' and 'adjacent_embeddings' respectively.
    """
    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)

    if provider:
        user = user.model_copy(update={"embedding_provider": provider})

    adjacent = _get_enrichment(backend, run.run_id, "adjacent")
    tags = _get_enrichment(backend, run.run_id, "tags")

    enrichment = embed_queries(
        queries=run.queries,
        provider=get_embedding_provider(user),
        adjacent_data=adjacent.data if adjacent else {},
        tags_data=tags.data.get("tags", {}) if tags else {},
        user_id=get_user_id(backend),
        run_id=run.run_id,
    )
    _save_enrichment(backend, enrichment)

    seed_count = len(enrichment.data.get("embeddings", []))
    adj_count = len(enrichment.data.get("adjacent_embeddings", []))
    return {
        "run_id":    run.run_id,
        "embedded":  seed_count,
        "adjacent":  adj_count,
        "excluded":  len(run.queries) - seed_count,
        "provider":  user.embedding_provider,
    }


@command(help="Cluster embeddings into intent groups using a cluster model")
def cmd_enrich_cluster(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    model_id: Payload[str] = "",
    k: Payload[int] = 0,
    description: Payload[str] = "",
) -> dict:
    """
    Stage 3b: fit or apply a cluster model over the joint pool of seed
    and adjacent embeddings.

    If --model is supplied, the named ClusterModel is loaded and applied
    to the current run without re-fitting. This produces comparable metrics
    across runs and is the correct mode for trend analysis.

    If --model is omitted, a new ClusterModel is fitted and persisted.

    Writes:
        ClusterModel          (reheat_models, only when fitting)
        ClusterAssignments    (reheat_models)
        ModelClusterMetric    (reheat_models, one per cluster)
        ModelRunMetric        (reheat_models, one per cluster, dual-write)
        RunModels             (reheat_models, adjacency index)
        ModelRuns             (reheat_models, adjacency index)
    """
    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)

    embed_enrichment = _get_enrichment(backend, run.run_id, "embeddings")
    if embed_enrichment is None:
        raise ValueError("no embeddings found -- run: reheat enrich embed")

    adjacent_enrichment = _get_enrichment(backend, run.run_id, "adjacent")
    adjacent_data = adjacent_enrichment.data if adjacent_enrichment else {}

    # build joint embedding pool
    seed_records = embed_enrichment.data.get("embeddings", [])
    adjacent_records = embed_enrichment.data.get("adjacent_embeddings", [])

    all_embeddings = [
        EmbeddedQuery(query=e["query"], vector=e["vector"], is_adjacent=False)
        for e in seed_records
    ] + [
        EmbeddedQuery(query=e["query"], vector=e["vector"], is_adjacent=True)
        for e in adjacent_records
    ]

    if not all_embeddings:
        raise ValueError("embedding pool is empty -- run: reheat enrich embed")

    now = _now()
    metric_id = now.strftime("%Y%m%dT%H%M%SZ")
    fitted = False

    if model_id:
        model = backend.get(
            MODELS_TABLE, ClusterModel, user_id=get_user_id(backend), model_id=model_id,
        )
        if model is None:
            raise ValueError(f"cluster model {model_id!r} not found")
        logger.info("applying existing model %s to run %s", model_id, run.run_id)
    else:
        effective_k = k or user.cluster_k
        new_model_id = now.strftime("%Y%m%dT%H%M%SZ")
        centroids = fit_cluster_model(all_embeddings, effective_k)
        model = ClusterModel(
            user_id=get_user_id(backend),
            model_id=new_model_id,
            source_id=run.source_id or "",
            description=description or None,
            algorithm="agglomerative+kmeans",
            embedding_model=user.embedding_provider,
            k=effective_k,
            centroids=centroids,
            created_at=now,
        )
        backend.save(MODELS_TABLE, model)
        model_id = new_model_id
        fitted = True
        logger.info("fitted new cluster model %s (k=%d)", model_id, effective_k)

    assignments = apply_cluster_model(model.centroids, all_embeddings)
    assignment_dicts = [a.model_dump() for a in assignments]

    # persist assignments
    backend.save(MODELS_TABLE, ClusterAssignments(
        user_id=get_user_id(backend),
        model_id=model_id,
        run_id=run.run_id,
        assignments=assignment_dicts,
        created_at=now,
    ))

    # persist adjacency index (both directions)
    backend.save(MODELS_TABLE, RunModels(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        model_id=model_id,
        applied_at=now,
    ))
    backend.save(MODELS_TABLE, ModelRuns(
        user_id=get_user_id(backend),
        model_id=model_id,
        run_id=run.run_id,
        applied_at=now,
    ))

    # compute and dual-write metrics
    metrics = _compute_cluster_metrics(
        assignment_dicts, run.queries, adjacent_data, model.k,
    )
    for m in metrics:
        cluster_id = m["cluster_id"]
        shared = dict(
            user_id=get_user_id(backend),
            model_id=model_id,
            cluster_id=cluster_id,
            metric_id=metric_id,
            intent_demand=m["intent_demand"],
            coverage_health=m["coverage_health"],
            click_quality=m["click_quality"],
            demand_capture=m["demand_capture"],
            seed_query_count=m["seed_query_count"],
            adjacent_query_count=m["adjacent_query_count"],
            computed_at=now,
        )
        backend.save(MODELS_TABLE, ModelClusterMetric(
            run_id=run.run_id,
            **shared,
        ))
        backend.save(MODELS_TABLE, ModelRunMetric(
            run_id=run.run_id,
            **shared,
        ))

    return {
        "run_id":    run.run_id,
        "model_id":  model_id,
        "fitted":    fitted,
        "k":         model.k,
        "queries":   len(seed_records),
        "adjacent":  len(adjacent_records),
        "metric_id": metric_id,
    }
