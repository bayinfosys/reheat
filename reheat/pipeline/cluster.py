import logging
from typing import List

import numpy as np
from pydantic import BaseModel
from sklearn.cluster import AgglomerativeClustering, KMeans

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline-internal structs -- not persisted directly
# ---------------------------------------------------------------------------

class EmbeddedQuery(BaseModel):
    """An embedding vector paired with its source query string."""
    query: str
    vector: list
    is_adjacent: bool = False


class ClusterAssignment(BaseModel):
    """
    Result of assigning a single query to a cluster centroid.
    Pipeline-internal struct. The command layer converts a list of these
    into a ClusterAssignments DBItem for persistence.
    """
    query: str
    cluster_id: int
    distance_to_centroid: float = 0.0
    is_adjacent: bool = False


class ClusteringError(Exception):
    """Raised when clustering cannot be performed."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _vectors(embeddings: List[EmbeddedQuery]) -> np.ndarray:
    return np.array([e.vector for e in embeddings], dtype=np.float32)


def _validate(embeddings: List[EmbeddedQuery], k: int) -> None:
    if len(embeddings) == 0:
        raise ClusteringError("no embeddings to cluster")
    if k < 2:
        raise ClusteringError(f"k must be at least 2, got {k}")
    if k > len(embeddings):
        raise ClusteringError(
            f"k ({k}) exceeds number of embeddings ({len(embeddings)}). "
            "Reduce cluster_k in config or fetch more queries."
        )


def _agglomerative_centroids(vectors: np.ndarray, k: int) -> np.ndarray:
    """
    Run agglomerative clustering and return per-cluster mean vectors
    to use as k-means initial centres. This produces stable, well-separated
    initial centroids and reduces k-means sensitivity to random
    initialisation.
    """
    logger.debug("agglomerative init with k=%d over %d vectors", k, len(vectors))
    agg = AgglomerativeClustering(n_clusters=k)
    labels = agg.fit_predict(vectors)

    centroids = np.zeros((k, vectors.shape[1]), dtype=np.float32)
    for cluster_id in range(k):
        mask = labels == cluster_id
        if mask.sum() > 0:
            centroids[cluster_id] = vectors[mask].mean(axis=0)
        else:
            centroids[cluster_id] = vectors[np.random.randint(len(vectors))]
            logger.warning(
                "agglomerative cluster %d was empty, using random centroid",
                cluster_id,
            )

    return centroids


# ---------------------------------------------------------------------------
# Public pipeline functions
# ---------------------------------------------------------------------------

def fit_cluster_model(
    embeddings: List[EmbeddedQuery],
    k: int,
) -> List[List[float]]:
    """
    Fit a k-means model (agglomerative-initialised) over the full embedding
    pool and return the cluster centroids.

    The full pool should contain both seed and adjacent queries so that the
    cluster structure represents the complete intent landscape, not just the
    subset the site already ranks for.

    Returns centroids as list[list[float]]. The caller (command layer) is
    responsible for constructing and persisting the ClusterModel DBItem.

    Raises ClusteringError if k is invalid or the embedding list is empty.
    """
    _validate(embeddings, k)
    logger.info(
        "fitting cluster model: %d embeddings, k=%d "
        "(%d seed, %d adjacent)",
        len(embeddings),
        k,
        sum(1 for e in embeddings if not e.is_adjacent),
        sum(1 for e in embeddings if e.is_adjacent),
    )

    vectors = _vectors(embeddings)
    init_centroids = _agglomerative_centroids(vectors, k)

    kmeans = KMeans(
        n_clusters=k,
        init=init_centroids,
        n_init=1,
        max_iter=300,
        random_state=42,
    )
    kmeans.fit(vectors)

    centroids = kmeans.cluster_centers_.tolist()
    sizes = np.bincount(kmeans.labels_, minlength=k)
    logger.info(
        "model fit complete: k=%d, cluster sizes min=%d max=%d mean=%.1f",
        k,
        int(sizes.min()),
        int(sizes.max()),
        float(sizes.mean()),
    )

    return centroids


def apply_cluster_model(
    centroids: List[List[float]],
    embeddings: List[EmbeddedQuery],
) -> List[ClusterAssignment]:
    """
    Assign each embedding to the nearest centroid by L2 distance.

    Works for both the initial run that produced the centroids and any
    subsequent run using the same model. The is_adjacent flag on each
    EmbeddedQuery is preserved on the returned ClusterAssignment.

    Returns one ClusterAssignment per input embedding.
    """
    if not embeddings:
        return []

    centroid_arr = np.array(centroids, dtype=np.float32)          # (k, d)
    vectors = np.array([e.vector for e in embeddings], dtype=np.float32)  # (n, d)

    # (n, k) -- squared distances, then argmin
    diff = vectors[:, np.newaxis, :] - centroid_arr[np.newaxis, :, :]   # (n, k, d)
    distances = np.linalg.norm(diff, axis=2)                             # (n, k)
    cluster_ids = np.argmin(distances, axis=1)                           # (n,)
    min_distances = distances[np.arange(len(embeddings)), cluster_ids]   # (n,)

    assignments = [
        ClusterAssignment(
            query=embedding.query,
            cluster_id=int(cluster_ids[i]),
            distance_to_centroid=float(min_distances[i]),
            is_adjacent=embedding.is_adjacent,
        )
        for i, embedding in enumerate(embeddings)
    ]

    seed_count = sum(1 for a in assignments if not a.is_adjacent)
    adj_count = len(assignments) - seed_count
    logger.info(
        "applied cluster model: %d assignments (%d seed, %d adjacent)",
        len(assignments), seed_count, adj_count,
    )
    return assignments
