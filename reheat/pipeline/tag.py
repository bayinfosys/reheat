from typing import Dict, List, Optional

from reheat.state import QueryRecord

AUTO_TAG_PREFIX = "auto:"
USER_TAG_PREFIX = "user:"


def auto_tag(record: QueryRecord, adjacent_data: Optional[dict] = None) -> List[str]:
    tags = []
    if len(record.query) > 150:
        tags.append("auto:long-query")
    if record.query.count("-site:") > 2:
        tags.append("auto:ai-generated")
    if record.query.count("-filetype:") > 2:
        tags.append("auto:ai-generated")
    if record.impressions == 0:
        tags.append("auto:zero-impression")
    if record.clicks == 0 and record.impressions < 2:
        tags.append("auto:low-signal")
    if adjacent_data:
        query_serp = adjacent_data.get(record.query, {})
        if not query_serp.get("related"):
            tags.append("auto:no-serp-data")
    return tags


def tag_all(
    records: List[QueryRecord],
    adjacent_data: Optional[dict] = None,
) -> Dict[str, List[str]]:
    return {record.query: auto_tag(record, adjacent_data=adjacent_data) for record in records}
