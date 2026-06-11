import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone

from dynawrap.backends.base import DBBackend

from reheat.commands.runs import _resolve_run
from reheat.pipeline.cluster import (EmbeddedQuery, apply_cluster_model,
                                     fit_cluster_model)
from reheat.pipeline.embed import embed_queries
from reheat.pipeline.tag import tag_all
from reheat.providers.embeddings import get_embedding_provider
from reheat.registry import Payload, command
from reheat.sources.serp import SerpAPIProvider
from reheat.state import (ENRICHMENTS_TABLE, MODELS_TABLE, SOURCES_TABLE,
                          ClusterAssignments, ClusterModel, Enrichment,
                          ModelClusterMetric, ModelRunMetric, ModelRuns,
                          RunModels, SourceConfig, get_user, get_user_id)

from .analyse import _get_latest_enrichment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_adjacent_data(backend: DBBackend, run_id: str) -> dict:
    """
    Load all adjacent enrichment records for this run and merge their
    query maps into a single dict keyed by query string.

    Each adjacent enrichment is stored as enrichment_type='adjacent#{source_id}'.
    PAA and related lists from all sources are concatenated.

    Returns an empty dict if no adjacent enrichments exist.
    """
    uid = get_user_id(backend)
    merged = {}
    for enrichment in backend.query(
        ENRICHMENTS_TABLE,
        Enrichment,
        user_id=uid,
        run_id=run_id,
        enrichment_type="adjacent",
    ):
        for query, data in enrichment.data.get("queries", {}).items():
            if query not in merged:
                merged[query] = {"related": []}
            merged[query]["related"].extend(data.get("related", []))

    return merged


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
    all seed queries that surfaced it via PAA or related search.

    Returns a list of dicts, one per cluster index 0..k-1.
    """
    impressions = {q.query: q.impressions for q in queries}
    clicks_map = {q.query: q.clicks for q in queries}

    adjacent_to_seeds: dict = defaultdict(list)
    for seed, data in adjacent_data.items():
        for q in data.get("paa", []) + data.get("related", []):
            if q:
                adjacent_to_seeds[q.lower()].append(seed)

    cluster_data: dict = defaultdict(
        lambda: {
            "seed_impressions": 0.0,
            "clicks": 0.0,
            "adjacent_weight": 0.0,
            "seed_count": 0,
            "adjacent_count": 0,
        }
    )

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

        results.append(
            {
                "cluster_id": str(cluster_id).zfill(4),
                "intent_demand": round(intent_demand, 4),
                "coverage_health": round(coverage_health, 4),
                "click_quality": round(click_quality, 4),
                "demand_capture": round(demand_capture, 4),
                "seed_query_count": cd["seed_count"],
                "adjacent_query_count": cd["adjacent_count"],
            }
        )

    return results


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@command(help="Tag queries with auto-generated labels")
def cmd_enrich_tags(
    backend: DBBackend, *, run_id: Payload[str] = "", headless: bool = False
) -> dict:
    run = _resolve_run(backend, run_id or None)
    adjacent_data = _get_adjacent_data(backend, run.run_id)
    tags = tag_all(run.queries, adjacent_data=adjacent_data)

    enrichment = Enrichment(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        enrichment_type="tags",
        source_id="regex",
        layer="silver",
        data={"tags": tags},
        derived_from=["adjacent"],
        created_at=_now(),
    )

    backend.save(ENRICHMENTS_TABLE, enrichment)

    all_tags = [t for ts in tags.values() for t in ts]
    return {
        "run_id": run.run_id,
        "tagged": len(tags),
        "tag_counts": dict(sorted(Counter(all_tags).items())),
    }


@command(help="Fetch adjacent queries via SerpAPI (PAA and related searches)")
def cmd_enrich_adjacent(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    source_id: Payload[str] = "",
    headless: Payload[bool] = False,
) -> dict:
    """
    Calls SerpAPI for the top queries in the run and stores PAA and
    related-search data. One Enrichment record is written per serp source,
    stored as enrichment_type='adjacent#{source_id}'.

    With no --source-id, all configured serp sources are run in sequence.
    With --source-id, only that source is used.

    Requires at least one source of type 'serp':
        reheat sources create --source-type serp --domain google
    """
    run = _resolve_run(backend, run_id or None)
    uid = get_user_id(backend)

    all_serp = [
        s
        for s in backend.query(SOURCES_TABLE, SourceConfig, user_id=uid)
        if s.source_type == "serp"
    ]
    if not all_serp:
        raise ValueError(
            "no serp source configured. "
            "Run: reheat sources create --source-type serp --domain google"
        )

    if source_id:
        sources = [s for s in all_serp if s.source_id == source_id]
        if not sources:
            raise ValueError(
                f"serp source {source_id!r} not found. "
                f"Available: {', '.join(s.source_id for s in all_serp)}"
            )
    else:
        sources = all_serp

    total_enriched = 0
    total_adjacent = 0
    records_written = []

    for source in sources:
        source.settings["headless"] = headless
        logger.info(
            "running adjacent enrichment via %s (engine: %s)",
            source.source_id,
            source.domain or "google",
        )

        enriched_map = SerpAPIProvider(source).enrich(run.queries)

        enrichment = Enrichment(
            user_id=uid,
            run_id=run.run_id,
            enrichment_type="adjacent",
            source_id=source.source_id,
            layer="silver",
            data={"queries": enriched_map},
            derived_from=[],
            created_at=_now(),
        )

        backend.save(ENRICHMENTS_TABLE, enrichment)

        enriched_count = sum(
            1 for v in enriched_map.values() if v.get("paa") or v.get("related")
        )
        adjacent_count = sum(
            len(v.get("paa", [])) + len(v.get("related", []))
            for v in enriched_map.values()
        )
        total_enriched += enriched_count
        total_adjacent += adjacent_count
        records_written.append(
            {
                "source_id": source.source_id,
                "seeds_enriched": enriched_count,
                "adjacent_queries": adjacent_count,
            }
        )
        logger.info(
            "adjacent enrichment complete for %s: %d seeds, %d adjacent",
            source.source_id,
            enriched_count,
            adjacent_count,
        )

    return {
        "run_id": run.run_id,
        "sources": records_written,
        "seeds_total": len(run.queries),
        "total_enriched": total_enriched,
        "total_adjacent": total_adjacent,
    }


@command(help="Generate embeddings for seed and adjacent queries")
def cmd_enrich_embed(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    provider: Payload[str] = "",
    headless: bool = False,
) -> dict:
    """
    Stage 3a: embed seed queries and adjacent queries into the same
    vector space. Adjacent data is read from all configured serp sources
    and merged. If no adjacent enrichment exists, only seed queries are
    embedded.

    The embeddings enrichment produced here is the input to cmd_enrich_cluster.
    Both seed and adjacent vectors are stored together under the keys
    'embeddings' and 'adjacent_embeddings' respectively.
    """
    run = _resolve_run(backend, run_id or None)
    user = get_user(backend)

    if provider:
        user = user.model_copy(update={"embedding_provider": provider})

    adjacent_data = _get_adjacent_data(backend, run.run_id)
    tags = _get_latest_enrichment(backend, run.run_id, "tags")

    result = embed_queries(
        queries=run.queries,
        provider=get_embedding_provider(user),
        adjacent_data=adjacent_data,
        tags_data=tags.data.get("tags", {}) if tags else {},
    )

    source_id = result.model_name or user.embedding_model

    enrichment = Enrichment(
        user_id=get_user_id(backend),
        run_id=run.run_id,
        enrichment_type="embeddings",
        source_id=source_id,
        layer="silver",
        data={
            "embeddings": result.embeddings,
            "adjacent_embeddings": result.adjacent_embeddings,
        },
        derived_from=["adjacent", "tags"],
        created_at=_now(),
    )

    backend.save(ENRICHMENTS_TABLE, enrichment)

    return {
        "run_id": run.run_id,
        "embedded": len(result.embeddings),
        "adjacent": len(result.adjacent_embeddings),
        "excluded": len(run.queries) - len(result.embeddings),
        "provider": source_id,
    }


@command(help="Cluster embeddings into intent groups using a cluster model")
def cmd_enrich_cluster(
    backend: DBBackend,
    *,
    run_id: Payload[str] = "",
    model_id: Payload[str] = "",
    k: Payload[int] = 0,
    description: Payload[str] = "",
    headless: bool = False,
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

    embed_enrichment = _get_latest_enrichment(backend, run.run_id, "embeddings")
    if embed_enrichment is None:
        raise ValueError("no embeddings found -- run: reheat enrich embed")

    adjacent_data = _get_adjacent_data(backend, run.run_id)

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

    recommended_k = max(2, min(user.cluster_k, len(all_embeddings) // 3))
    logger.info(
        "recommend k set to %i for %i total embeddings",
        recommended_k,
        len(all_embeddings),
    )

    now = _now()
    metric_id = now.strftime("%Y%m%dT%H%M%SZ")
    fitted = False

    if model_id:
        model = backend.get(
            MODELS_TABLE,
            ClusterModel,
            user_id=get_user_id(backend),
            model_id=model_id,
        )
        if model is None:
            raise ValueError(f"cluster model {model_id!r} not found")
        logger.info("applying existing model %s to run %s", model_id, run.run_id)
    else:
        effective_k = recommended_k or user.cluster_k
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

    backend.save(
        MODELS_TABLE,
        ClusterAssignments(
            user_id=get_user_id(backend),
            model_id=model_id,
            run_id=run.run_id,
            assignments=assignment_dicts,
            created_at=now,
        ),
    )

    backend.save(
        MODELS_TABLE,
        RunModels(
            user_id=get_user_id(backend),
            run_id=run.run_id,
            model_id=model_id,
            applied_at=now,
        ),
    )
    backend.save(
        MODELS_TABLE,
        ModelRuns(
            user_id=get_user_id(backend),
            model_id=model_id,
            run_id=run.run_id,
            applied_at=now,
        ),
    )

    metrics = _compute_cluster_metrics(
        assignment_dicts,
        run.queries,
        adjacent_data,
        model.k,
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
        backend.save(MODELS_TABLE, ModelClusterMetric(run_id=run.run_id, **shared))
        backend.save(MODELS_TABLE, ModelRunMetric(run_id=run.run_id, **shared))

    return {
        "run_id": run.run_id,
        "model_id": model_id,
        "fitted": fitted,
        "k": model.k,
        "queries": len(seed_records),
        "adjacent": len(adjacent_records),
        "metric_id": metric_id,
    }
