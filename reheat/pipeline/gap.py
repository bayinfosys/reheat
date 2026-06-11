import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def owned_set(queries: list) -> Set[str]:
    """Return the lowercase set of query strings the site already ranks for."""
    return {q.query.lower() for q in queries}


def adjacent_map(adjacent_data: dict) -> Dict[str, List[str]]:
    """
    Build seed -> [related] map from adjacent enrichment data.
    Input is the merged dict keyed by query string:
        {seed_query: {"related": [...]}}
    """
    result = {}
    for query, data in adjacent_data.items():
        queries = data.get("related", [])
        if queries:
            result[query] = queries
    return result


def gaps_per_seed(
    owned: Set[str],
    adjacent: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """Adjacent queries not in owned set, grouped by seed."""
    return {
        seed: [q for q in queries if q.lower() not in owned]
        for seed, queries in adjacent.items()
        if any(q.lower() not in owned for q in queries)
    }


def overlapping_gaps(
    owned: Set[str],
    adjacent: Dict[str, List[str]],
) -> List[Tuple[str, int, List[str]]]:
    """
    Adjacent queries appearing across multiple seeds, not in owned set.
    Returns list of (query, seed_count, seeds) sorted by seed_count desc.
    """
    counts: Dict[str, List[str]] = defaultdict(list)
    for seed, queries in adjacent.items():
        for q in queries:
            if q.lower() not in owned:
                counts[q].append(seed)
    return sorted(
        [(q, len(seeds), seeds) for q, seeds in counts.items()],
        key=lambda x: x[1],
        reverse=True,
    )


def opportunity_scores(
    owned: Set[str],
    adjacent: Dict[str, List[str]],
    impressions: Dict[str, int],
) -> List[Tuple[str, int, List[str]]]:
    """
    Score adjacent queries by sum of impressions of seeds they appear beside.
    Returns list of (query, score, seeds) sorted by score desc.
    """
    scores: Dict[str, Dict] = defaultdict(lambda: {"score": 0, "seeds": []})
    for seed, queries in adjacent.items():
        seed_impressions = impressions.get(seed, 0)
        for q in queries:
            if q.lower() not in owned:
                scores[q]["score"] += seed_impressions
                scores[q]["seeds"].append(seed)
    return sorted(
        [(q, v["score"], v["seeds"]) for q, v in scores.items()],
        key=lambda x: x[1],
        reverse=True,
    )
