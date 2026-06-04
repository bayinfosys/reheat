import logging
from datetime import datetime, timezone
from typing import List

from reheat.state.execution import Enrichment, QueryRecord
from reheat.pipeline.transform import to_embedding_text
from reheat.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


def embed_queries(
    queries: List[QueryRecord],
    provider: EmbeddingProvider,
    adjacent_data: dict,
    tags_data: dict,
    user_id: str = "default",
    run_id: str = "",
) -> Enrichment:
    exclude = {"auto:ai-generated", "auto:zero-impression"}

    to_embed = [
        q for q in queries if not exclude.intersection(tags_data.get(q.query, []))
    ]

    logger.info(
        "embedding %d queries (%d excluded by tag)",
        len(to_embed),
        len(queries) - len(to_embed),
    )

    # seed embeddings
    seed_texts = [to_embedding_text(q.query, "main") for q in to_embed]
    seed_vectors = provider.embed(seed_texts)
    embeddings = [
        {"query": q.query, "vector": v} for q, v in zip(to_embed, seed_vectors)
    ]

    # adjacent embeddings from serp enrichment
    seen = {q.query for q in to_embed}
    adjacent = []
    for query_data in adjacent_data.get("queries", {}).values():
        for paa in query_data.get("paa", []):
            if paa and paa not in seen:
                adjacent.append(("paa", paa))
                seen.add(paa)
        for related in query_data.get("related", []):
            if related and related not in seen:
                adjacent.append(("related", related))
                seen.add(related)

    adjacent_embeddings = []
    if adjacent:
        adj_texts = [to_embedding_text(q, t) for t, q in adjacent]
        adj_vectors = provider.embed(adj_texts)
        adjacent_embeddings = [
            {"query": q, "type": t, "vector": v}
            for (t, q), v in zip(adjacent, adj_vectors)
        ]
        logger.info("embedded %d adjacent queries", len(adjacent_embeddings))

    logger.info("embedded %d seed queries", len(embeddings))

    return Enrichment(
        user_id=user_id,
        run_id=run_id,
        enrichment_type="embeddings",
        layer="silver",
        data={
            "embeddings": embeddings,
            "adjacent_embeddings": adjacent_embeddings,
        },
        derived_from=["serp", "tags"],
        created_at=datetime.now(timezone.utc),
    )
