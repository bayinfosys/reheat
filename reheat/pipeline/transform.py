import json
from typing import List, Literal, Tuple

import numpy as np

ProjectionMethod = Literal["umap", "tsne", "pca"]


def to_embedding_text(query: str, query_type: str = "main") -> str:
    """
    Serialise a query string to JSON for embedding.
    Same schema for main queries and adjacent queries.
    """
    return json.dumps(
        {
            "query": query,
            "type": query_type,
            "length": len(query),
        },
        ensure_ascii=False,
    )


def project_embeddings(
    vectors: np.ndarray,
    method: ProjectionMethod = "umap",
    n_components: int = 2,
    random_state: int = 42,
) -> np.ndarray:
    """
    Project high-dimensional embedding vectors to n_components dimensions.
    Returns array of shape (n_samples, n_components).
    """
    if method == "umap":
        try:
            import umap
        except ImportError:
            raise ImportError("umap-learn is required. pip install umap-learn")
        reducer = umap.UMAP(
            n_components=n_components,
            random_state=random_state,
            n_neighbors=min(15, len(vectors) - 1),
            min_dist=0.1,
        )

    elif method == "tsne":
        from sklearn.manifold import TSNE
        reducer = TSNE(
            n_components=n_components,
            random_state=random_state,
            perplexity=min(30, len(vectors) - 1),
            n_iter=1000,
        )

    elif method == "pca":
        from sklearn.decomposition import PCA
        reducer = PCA(n_components=n_components, random_state=random_state)

    else:
        raise ValueError(f"unknown projection method {method!r}")

    return reducer.fit_transform(vectors)


def reduce_embeddings(
    embeddings: list,
    adjacent_embeddings: list,
    method: ProjectionMethod = "umap",
) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """
    Project seed and adjacent embeddings together for a coherent layout.
    Returns (seed_coords, adjacent_coords).
    """
    all_embeddings = embeddings + adjacent_embeddings
    if not all_embeddings:
        raise ValueError("no embeddings to project")

    vectors = np.array(
        [e["vector"] for e in all_embeddings], dtype=np.float32
    )

    reduced = project_embeddings(vectors, method=method)

    seed_coords = [
        (float(row[0]), float(row[1]))
        for row in reduced[:len(embeddings)]
    ]
    adjacent_coords = [
        (float(row[0]), float(row[1]))
        for row in reduced[len(embeddings):]
    ]

    return seed_coords, adjacent_coords
