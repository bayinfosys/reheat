import logging
from collections import defaultdict

from reheat.state import RunRecord

logger = logging.getLogger(__name__)


def build_scatter_data(
    embeddings: list,
    seed_coords: list,
    assignments: list,
    adjacent_embeddings: list,
    adjacent_coords: list,
    adjacent_assignments: list,
    summaries: list,
) -> list:
    """
    Build Chart.js dataset list from projection coords and cluster assignments.
    Returns the datasets list (stored in ScatterData.datasets).
    """
    assignment_map = {a["query"]: a["cluster_id"] for a in assignments}
    adjacent_map = {a["query"]: a["cluster_id"] for a in adjacent_assignments}
    cluster_to_label = {s["cluster_id"]: s["label"] for s in summaries}
    num_clusters = len(set(a["cluster_id"] for a in assignments))

    def cluster_colour(cluster_id: int, saturation: int, lightness: int) -> str:
        hue = int(360 * cluster_id / max(num_clusters, 1))
        return f"hsl({hue}, {saturation}%, {lightness}%)"

    seed_clusters: dict = {}
    for embedding, (x, y) in zip(embeddings, seed_coords):
        cluster_id = assignment_map.get(embedding["query"], -1)
        label = cluster_to_label.get(cluster_id, f"Cluster {cluster_id}")
        seed_clusters.setdefault(cluster_id, {
            "label": label,
            "colour": cluster_colour(cluster_id, 65, 55),
            "data": [],
        })
        seed_clusters[cluster_id]["data"].append({
            "x": x, "y": y,
            "query": embedding["query"],
            "is_adjacent": False,
        })

    adj_clusters: dict = {}
    for embedding, (x, y) in zip(adjacent_embeddings, adjacent_coords):
        cluster_id = adjacent_map.get(embedding["query"], -1)
        adj_clusters.setdefault(cluster_id, {
            "colour": cluster_colour(cluster_id, 25, 75),
            "data": [],
        })
        adj_clusters[cluster_id]["data"].append({
            "x": x, "y": y,
            "query": embedding["query"],
            "type": embedding.get("type", "adjacent"),
            "is_adjacent": True,
        })

    datasets = []

    for cluster_id, cluster in sorted(adj_clusters.items()):
        datasets.append({
            "label": f"_adj_{cluster_id}",
            "clusterId": cluster_id,
            "isAdjacent": True,
            "data": cluster["data"],
            "backgroundColor": cluster["colour"],
            "pointRadius": 3,
            "pointHoverRadius": 5,
        })

    for cluster_id, cluster in sorted(seed_clusters.items()):
        datasets.append({
            "label": cluster["label"],
            "clusterId": cluster_id,
            "isAdjacent": False,
            "data": cluster["data"],
            "backgroundColor": cluster["colour"],
            "pointRadius": 6,
            "pointHoverRadius": 8,
        })

    return datasets


def build_summary_data(
    run: RunRecord,
    adjacent_data: dict,
    assignments: list,
    opportunities: list,
    labels: dict = None,
) -> dict:
    """
    Build summary panel data from run and enrichments.
    Returns a dict matching SummaryData fields.
    """
    serp_queries = adjacent_data.get("queries", {})
    labels = labels or {}

    # top performing -- queries with clicks
    top_performing = [
        {
            "query":    q.query,
            "clicks":   q.clicks,
            "impressions": q.impressions,
            "position": q.position,
            "ctr":      q.ctr,
        }
        for q in sorted(
            [q for q in run.queries if q.clicks > 0],
            key=lambda q: (q.clicks, q.ctr),
            reverse=True,
        )[:5]
    ]

    # top clusters by total impressions
    cluster_impressions: dict = defaultdict(int)
    query_to_cluster: dict = defaultdict(list)
    for a in assignments:
        imp = next(
            (q.impressions for q in run.queries if q.query == a["query"]), 0
        )
        cluster_impressions[a["cluster_id"]] += imp
        query_to_cluster[a["cluster_id"]].append(a["query"])


    top_clusters = [
        {
            "cluster_id":  cid,
            "label":       labels.get(str(cid), f"Cluster {cid}"),
            "impressions": imp,
            "query_count": len(query_to_cluster[cid]),
            "sample":      query_to_cluster[cid][:3],
        }
        for cid, imp in sorted(
            cluster_impressions.items(), key=lambda x: x[1], reverse=True
        )[:5]
    ]

    # missed opportunities -- ranked but position > 20 with serp data
    missed = [
        {
            "query":    q.query,
            "position": q.position,
            "impressions": q.impressions,
            "adjacent": (
                serp_queries[q.query].get("paa", []) +
                serp_queries[q.query].get("related", [])
            )[:3],
        }
        for q in sorted(
            [
                q for q in run.queries
                if q.impressions > 0
                and q.position > 20
                and q.query in serp_queries
                and (
                    serp_queries[q.query].get("paa")
                    or serp_queries[q.query].get("related")
                )
            ],
            key=lambda q: (q.impressions, -q.position),
            reverse=True,
        )[:5]
    ]

    # new opportunities
    new_opps = [
        o for o in opportunities
        if o["recommendation"] == "new content"
    ][:5] or opportunities[:5]

    return {
        "top_performing":       top_performing,
        "top_clusters":         top_clusters,
        "missed_opportunities": missed,
        "new_opportunities":    new_opps,
    }
