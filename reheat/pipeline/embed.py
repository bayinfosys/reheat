import logging
from dataclasses import dataclass, field
from typing import List

from reheat.pipeline.transform import to_embedding_text
from reheat.providers.embeddings import EmbeddingProvider
from reheat.state import QueryRecord

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    embeddings: List[dict] = field(default_factory=list)
    adjacent_embeddings: List[dict] = field(default_factory=list)
    model_name: str = ""


def embed_queries(
    queries: List[QueryRecord],
    provider: EmbeddingProvider,
    adjacent_data: dict,
    tags_data: dict,
) -> EmbeddingResult:
    """
    Embed seed queries and adjacent queries into the same vector space.

    adjacent_data is the merged dict from _get_adjacent_data:
        {seed_query: {"related": [...]}}

    Returns an EmbeddingResult with seed and adjacent embedding lists
    and the model name used.
    """
    exclude = {"auto:ai-generated", "auto:zero-impression"}

    to_embed = [
        q for q in queries if not exclude.intersection(tags_data.get(q.query, []))
    ]

    logger.info(
        "embedding %d queries (%d excluded by tag)",
        len(to_embed),
        len(queries) - len(to_embed),
    )

    seed_texts = [to_embedding_text(q.query, "main") for q in to_embed]
    seed_vectors = provider.embed(seed_texts)
    embeddings = [
        {"query": q.query, "vector": v} for q, v in zip(to_embed, seed_vectors)
    ]

    seen = {q.query for q in to_embed}
    adjacent = []
    for data in adjacent_data.values():
        for related in data.get("related", []):
            if related and related not in seen:
                adjacent.append(related)
                seen.add(related)

    adjacent_embeddings = []
    if adjacent:
        adj_texts = [to_embedding_text(q, "related") for q in adjacent]
        adj_vectors = provider.embed(adj_texts)
        adjacent_embeddings = [
            {"query": q, "type": "related", "vector": v}
            for q, v in zip(adjacent, adj_vectors)
        ]
        logger.info("embedded %d adjacent queries", len(adjacent_embeddings))

    logger.info("embedded %d seed queries", len(embeddings))

    return EmbeddingResult(
        embeddings=embeddings,
        adjacent_embeddings=adjacent_embeddings,
        model_name=provider.model_name,
    )
