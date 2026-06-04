import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from reheat.providers.instruct import get_instruct_provider, ConfigError, InstructError
from reheat.pipeline.cluster import ClusterAssignment
from reheat.state.execution import ClusterSummary, QueryRecord
from reheat.state.user import UserState

logger = logging.getLogger(__name__)


class SummarisationError(Exception):
    """Raised when a cluster cannot be summarised."""


SUMMARISE_PROMPT = """\
You are analysing search query data to identify user intent clusters.

The following search queries have been grouped into a single intent cluster.
Provide a short label (3-6 words) and a one-sentence description of the
underlying intent these queries share.

Queries:
{queries}

Respond in JSON only, with this structure:
{{"label": "...", "description": "..."}}
"""


def _build_metrics_index(records: List[QueryRecord]) -> Dict[str, QueryRecord]:
    return {r.query: r for r in records}


def _top_queries_by_impression(
    queries: List[str],
    metrics: Dict[str, QueryRecord],
    top_n: int,
) -> List[str]:
    return sorted(
        queries,
        key=lambda q: metrics[q].impressions if q in metrics else 0,
        reverse=True,
    )[:top_n]


def summarise_cluster(
    cluster_id: int,
    queries: List[str],
    metrics: Dict[str, QueryRecord],
    user: UserState,
) -> ClusterSummary:
    """
    Generate a natural language label and description for a single cluster.

    Uses the configured instruct provider (Marigold or OpenAI). Raises
    SummarisationError if the provider is not configured or the call fails.
    """
    logger.debug("summarising cluster %d (%d queries)", cluster_id, len(queries))

    top = _top_queries_by_impression(queries, metrics, user.summarise_top_n)
    logger.debug(
        "top %d queries for cluster %d: %s",
        user.summarise_top_n, cluster_id, top,
    )

    try:
        provider = get_instruct_provider(user)
    except ConfigError as e:
        raise SummarisationError(str(e)) from e

    prompt = SUMMARISE_PROMPT.format(queries="\n".join(top))

    try:
        content = provider.complete(prompt)
        result = json.loads(content)
    except InstructError as e:
        raise SummarisationError(f"instruct call failed for cluster {cluster_id}: {e}") from e
    except (json.JSONDecodeError, KeyError) as e:
        raise SummarisationError(
            f"could not parse LLM response for cluster {cluster_id}: {e}"
        ) from e

    total_impressions = sum(metrics[q].impressions for q in queries if q in metrics)
    total_clicks = sum(metrics[q].clicks for q in queries if q in metrics)
    positions = [
        metrics[q].position for q in queries
        if q in metrics and metrics[q].position > 0
    ]
    avg_position = sum(positions) / len(positions) if positions else 0.0

    summary = ClusterSummary(
        cluster_id=cluster_id,
        label=result.get("label", ""),
        description=result.get("description", ""),
        top_queries=top,
        query_count=len(queries),
        total_impressions=total_impressions,
        total_clicks=total_clicks,
        avg_position=round(avg_position, 2),
    )

    logger.info(
        "cluster %d labelled: %r (%d queries, %d impressions)",
        cluster_id, summary.label, summary.query_count, summary.total_impressions,
    )
    return summary


def summarise_all(
    assignments: List[ClusterAssignment],
    records: List[QueryRecord],
    user: UserState,
    cluster_id: Optional[int] = None,
) -> List[ClusterSummary]:
    """
    Summarise all clusters, or a single cluster if cluster_id is given.

    Groups assignments by cluster_id, calls summarise_cluster for each.
    Only seed queries (is_adjacent=False) are used for label generation.
    Returns summaries sorted by total_impressions descending.
    Clusters that fail summarisation are logged as errors and skipped.
    """
    metrics = _build_metrics_index(records)

    grouped: Dict[int, List[str]] = defaultdict(list)
    for assignment in assignments:
        if not assignment.is_adjacent:
            grouped[assignment.cluster_id].append(assignment.query)

    target_ids = [cluster_id] if cluster_id is not None else sorted(grouped.keys())

    logger.info(
        "summarising %d cluster(s) with top_n=%d",
        len(target_ids), user.summarise_top_n,
    )

    summaries = []
    for cid in target_ids:
        queries = grouped.get(cid, [])
        if not queries:
            logger.warning("cluster %d has no seed queries, skipping", cid)
            continue
        try:
            summary = summarise_cluster(
                cluster_id=cid,
                queries=queries,
                metrics=metrics,
                user=user,
            )
            summaries.append(summary)
        except SummarisationError as e:
            logger.error("failed to summarise cluster %d: %s", cid, e)

    summaries.sort(key=lambda s: s.total_impressions, reverse=True)
    logger.info(
        "summarisation complete: %d/%d clusters labelled",
        len(summaries), len(target_ids),
    )
    return summaries
