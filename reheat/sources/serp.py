import logging
import time
from typing import List

import requests

from reheat.state.execution import QueryRecord, SourceConfig
from reheat.sources.base import SourceProvider, SourceError

logger = logging.getLogger(__name__)

SERP_API_URL = "https://serpapi.com/search"

# backoff schedule for 429 responses: wait this many seconds before each retry
_BACKOFF_SECONDS = [5.0, 15.0, 30.0]


def _fetch_single(query: str, api_key: str) -> dict:
    """
    Fetch SerpAPI results for a single query.
    Retries up to len(_BACKOFF_SECONDS) times on 429 with increasing waits.
    Raises SourceError on non-retryable errors or exhausted retries.
    """
    params = {
        "q": query,
        "hl": "en",
        "gl": "gb",
        "api_key": api_key,
        "engine": "google",
    }

    for attempt, backoff in enumerate([0.0] + _BACKOFF_SECONDS):
        if backoff:
            logger.warning(
                "rate limited on %r, waiting %.0fs before retry %d/%d",
                query, backoff, attempt, len(_BACKOFF_SECONDS),
            )
            time.sleep(backoff)

        try:
            response = requests.get(SERP_API_URL, params=params, timeout=15)
            if response.status_code == 429:
                if attempt < len(_BACKOFF_SECONDS):
                    continue
                raise SourceError(
                    f"SerpAPI rate limit exhausted for {query!r} after "
                    f"{len(_BACKOFF_SECONDS)} retries"
                )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            raise SourceError(f"SerpAPI request failed for {query!r}: {e}") from e
        except requests.exceptions.RequestException as e:
            raise SourceError(f"SerpAPI request failed for {query!r}: {e}") from e

    # unreachable but satisfies type checkers
    raise SourceError(f"SerpAPI request failed for {query!r}: retries exhausted")


def _extract_paa(data: dict) -> List[str]:
    return [
        item.get("question", "")
        for item in data.get("related_questions", [])
        if item.get("question")
    ]


def _extract_related(data: dict) -> List[str]:
    return [
        item.get("query", "")
        for item in data.get("related_searches", [])
        if item.get("query")
    ]


class SerpAPIProvider(SourceProvider):
    """
    Enriches QueryRecords with PAA and related searches from SerpAPI.

    Unlike other source providers, this operates on an existing list
    of QueryRecords rather than producing them from scratch.

    Required credentials:
        api_key  -- SerpAPI API key

    Settings:
        delay        -- seconds between requests (default 1.0)
        limit        -- max queries to enrich (default 50)
        headless     -- suppress progress bar if true (default false)
    """

    source_type = "serp"

    def validate(self) -> None:
        self._credential("api_key")

    def fetch(self) -> List[QueryRecord]:
        raise SourceError(
            "SerpAPIProvider.fetch() requires input queries. "
            "Call enrich(queries) instead."
        )

    def enrich(
        self,
        queries: List[QueryRecord],
    ) -> List[QueryRecord]:
        api_key = self._credential("api_key")
        delay = float(self._setting("delay", 1.0))
        limit = int(self._setting("limit", 50))
        headless = bool(self._setting("headless", False))

        candidates = sorted(
            queries, key=lambda q: q.impressions, reverse=True
        )[:limit]

        try:
            from tqdm import tqdm
            iterator = enumerate(
                tqdm(candidates, desc="enriching", unit="query", ncols=80)
                if not headless
                else candidates
            )
        except ImportError:
            iterator = enumerate(candidates)

        enriched_map = {}
        total = len(candidates)

        for i, record in iterator:
            if headless and i % 10 == 0:
                logger.info("enriching query %d/%d", i + 1, total)
            try:
                data = _fetch_single(record.query, api_key)
                if "error" in data:
                    raise SourceError(f"SerpAPI error: {data['error']}")
                enriched_map[record.query] = {
                    "paa": _extract_paa(data),
                    "related": _extract_related(data),
                }
                logger.debug(
                    "enriched %r: %d paa, %d related",
                    record.query,
                    len(enriched_map[record.query]["paa"]),
                    len(enriched_map[record.query]["related"]),
                )
            except SourceError as e:
                logger.warning("enrichment failed for %r: %s", record.query, e)

            if i < total - 1:
                time.sleep(delay)

        enriched_count = sum(
            1 for v in enriched_map.values() if v["paa"] or v["related"]
        )
        logger.info(
            "enrichment complete: %d/%d queries enriched",
            enriched_count, total,
        )

        return enriched_map
