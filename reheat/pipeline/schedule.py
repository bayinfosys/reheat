import json
import logging

from reheat.errors import ConfigError, InstructError, ScheduleError
from reheat.providers.instruct import get_instruct_provider
from reheat.state.user import UserState

logger = logging.getLogger(__name__)


SCHEDULE_PROMPT = """\
You are a content strategist analysing SEO data for {domain}.

SITE CONTEXT
- {query_count} indexed queries, {impressions} total impressions
- {cluster_count} intent clusters identified

INTENT CLUSTERS (by impression, highest first)
Each cluster shows: label, seed queries, impressions, adjacent queries (unranked demand)
{clusters}

CONTENT OPPORTUNITIES (top 10 by score)
{opportunities}

HIGH-VALUE TOPICS (queries appearing across multiple clusters)
{high_value}

Produce a JSON array of 10-15 content schedule items ordered by priority.
Each item must follow this exact structure:

{{
  "priority": 1,
  "title": "Specific suggested article or content title",
  "cluster_label": "Label of the primary cluster this serves",
  "opportunity_type": "expand",
  "rationale": "One sentence referencing the data: include the adjacent query count and impression count to justify the priority.",
  "target_queries": ["exact search query 1", "exact search query 2"],
  "seo_terms": ["specific phrase or term to include in the article", "another term", "another"]
}}

opportunity_type must be "expand" (building on existing ranked content) or "new" (no current ranking).
target_queries: 2-3 specific search queries the article should rank for.
seo_terms: 4-6 specific phrases, vocabulary, or related concepts to weave into the article body.
Respond with a JSON object: {{"schedule": [...]}}
"""


def build_schedule(
    domain: str,
    query_count: int,
    impressions: int,
    summaries: list,
    opportunities: list,
    high_value_topics: list,
    user: UserState,
) -> dict:
    clusters_text = "\n".join(
        f"- {s['label']}: {s['query_count']} seed queries, "
        f"{s['total_impressions']} impressions, "
        f"{s.get('adjacent_count', 0)} adjacent queries. "
        f"{s.get('description', '')}"
        for s in summaries[:12]
    )

    opps_text = "\n".join(
        f"- {o['query']} (score {o['score']}, "
        f"adjacent to: {', '.join(o['seeds'][:3])})"
        for o in opportunities[:30]
    )

    high_value_text = "\n".join(
        f"- {h['query']} (appears across {h['seed_count']} topics)"
        for h in high_value_topics[:10]
    )

    prompt = SCHEDULE_PROMPT.format(
        domain=domain,
        query_count=query_count,
        impressions=impressions,
        cluster_count=len(summaries),
        clusters=clusters_text,
        opportunities=opps_text,
        high_value=high_value_text,
    )

    try:
        provider = get_instruct_provider(user)
    except ConfigError as e:
        raise ScheduleError(str(e)) from e

    try:
        content = provider.complete(prompt, max_tokens=4000)
        result = json.loads(content)
    except InstructError as e:
        raise ScheduleError(f"instruct call failed: {e}") from e
    except (json.JSONDecodeError, KeyError) as e:
        raise ScheduleError(f"could not parse schedule response: {e}") from e

    logger.info("schedule generated: %d items", len(result.get("schedule", [])))
    return result


OVERVIEW_PROMPT = """\
You are writing an executive summary for an SEO analysis report for {domain}.

SITE DATA
- {query_count} indexed queries, {impressions} total impressions
- {cluster_count} intent clusters identified

TOP CLUSTERS BY IMPRESSION
{clusters}

CONTENT SCHEDULE (already generated)
{schedule}

Write a three-paragraph plain-English overview suitable for a printed report.

Paragraph 1 -- Data review: describe the site's current search presence, \
the main topic areas, and the scale of visibility the data shows.

Paragraph 2 -- Analysis: describe what the cluster and adjacent query data \
reveals about the audience's intent, where the site has strong coverage, \
and where demand is unmet.

Paragraph 3 -- Schedule summary: summarise the content schedule in plain \
language -- what to write, in what order, and the overall strategic direction \
it represents.

Respond in JSON only:
{{"paragraphs": ["...", "...", "..."]}}
"""


def build_overview(
    domain: str,
    query_count: int,
    impressions: int,
    summaries: list,
    schedule: list,
    user: UserState,
) -> dict:
    clusters_text = "\n".join(
        f"- {s['label']}: {s['total_impressions']} impressions, {s['query_count']} queries"
        for s in summaries[:10]
    )

    schedule_text = "\n".join(
        f"{i['priority']}. {i['title']} ({i['opportunity_type']}): {i['rationale']}"
        for i in schedule
    )

    prompt = OVERVIEW_PROMPT.format(
        domain=domain,
        query_count=query_count,
        impressions=impressions,
        cluster_count=len(summaries),
        clusters=clusters_text,
        schedule=schedule_text,
    )

    try:
        provider = get_instruct_provider(user)
    except ConfigError as e:
        raise ScheduleError(str(e)) from e

    try:
        content = provider.complete(prompt, max_tokens=1000)
        result = json.loads(content)
    except InstructError as e:
        raise ScheduleError(f"instruct call failed: {e}") from e
    except (json.JSONDecodeError, KeyError) as e:
        raise ScheduleError(f"could not parse overview response: {e}") from e

    if "paragraphs" not in result or len(result["paragraphs"]) != 3:
        raise ScheduleError(
            f"unexpected overview response shape: {list(result.keys())}"
        )

    logger.info("overview generated")
    return result
