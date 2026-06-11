import asyncio
import logging
from typing import List

import httpx

from reheat.sources.base import SourceError, SourceProvider
from reheat.state import QueryRecord

logger = logging.getLogger(__name__)

SERP_API_URL = "https://serpapi.com/search"
_ENV_API_KEY = "SERPAPI_KEY"

_TIMEOUT        = 8.0
_MAX_CONCURRENT = 5
_RETRY_WAIT     = 3.0
_BACKOFF_429    = [5.0, 15.0, 30.0]


# ---------------------------------------------------------------------------
# Per-engine response processors
# Each takes the raw SerpAPI response dict and returns {"related": [...]}
# ---------------------------------------------------------------------------

def _process_google(data: dict) -> dict:
    paa = [
        item.get("question", "")
        for item in data.get("related_questions", [])
        if item.get("question")
    ]
    related = [
        item.get("query", "")
        for item in data.get("related_searches", [])
        if item.get("query")
    ]
    return {"related": paa + related}


def _process_youtube(data: dict) -> dict:
    return {
        "related": [
            item.get("title", "")
            for item in data.get("related_videos", [])
            if item.get("title")
        ]
    }


def _process_google_patents(data: dict) -> dict:
    return {
        "related": [
            item.get("title", "")
            for item in data.get("organic_results", [])
            if item.get("title")
        ]
    }


def _process_google_news(data: dict) -> dict:
    return {
        "related": [
            item.get("title", "")
            for item in data.get("news_results", [])
            if item.get("title")
        ]
    }


_PROCESSORS: dict = {
    "google":         _process_google,
    "youtube":        _process_youtube,
    "google_patents": _process_google_patents,
    "google_news":    _process_google_news,
}


def _extract_adjacent(engine: str, data: dict) -> dict:
    processor = _PROCESSORS.get(engine)
    if processor is None:
        sample_keys = list(data.keys())[:10]
        logger.warning(
            "no post-processor for engine %r -- adjacent data will be empty. "
            "Response top-level keys: %s. "
            "Add a _process_%s() function and register it in _PROCESSORS in serp.py.",
            engine, sample_keys, engine.replace("-", "_"),
        )
        return {"related": []}
    return processor(data)


# ---------------------------------------------------------------------------
# Async HTTP
# ---------------------------------------------------------------------------

async def _fetch_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    query: str,
    api_key: str,
    engine: str,
) -> tuple[str, dict]:
    """
    Fetch SerpAPI results for a single query.
    Returns (query, normalised_adjacent_dict).
    On failure returns (query, {"related": []}) after logging a warning.
    Respects the semaphore for concurrency control.
    Retries once on timeout, backs off on 429.
    """
    params = {
        "q":       query,
        "hl":      "en",
        "gl":      "gb",
        "api_key": api_key,
        "engine":  engine,
    }

    async with semaphore:
        for attempt, backoff in enumerate([0.0] + _BACKOFF_429):
            if backoff:
                logger.warning(
                    "rate limited on %r, waiting %.0fs (attempt %d)",
                    query, backoff, attempt,
                )
                await asyncio.sleep(backoff)

            try:
                response = await client.get(
                    SERP_API_URL, params=params, timeout=_TIMEOUT
                )
                if response.status_code == 429:
                    if attempt < len(_BACKOFF_429):
                        continue
                    logger.warning(
                        "rate limit exhausted for %r after %d retries",
                        query, len(_BACKOFF_429),
                    )
                    return query, {"related": []}

                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    logger.warning("SerpAPI error for %r: %s", query, data["error"])
                    return query, {"related": []}

                return query, _extract_adjacent(engine, data)

            except httpx.TimeoutException:
                if attempt == 0:
                    logger.warning("timeout on %r, retrying once", query)
                    continue
                logger.warning("timeout on %r after retry, skipping", query)
                return query, {"related": []}

            except httpx.HTTPStatusError as e:
                logger.warning("HTTP error for %r: %s", query, e)
                return query, {"related": []}

            except httpx.RequestError as e:
                logger.warning("request error for %r: %s", query, e)
                return query, {"related": []}

    return query, {"related": []}


async def _enrich_all(
    queries: List[QueryRecord],
    api_key: str,
    engine: str,
    limit: int,
    max_concurrent: int,
) -> dict:
    candidates = sorted(queries, key=lambda q: q.impressions, reverse=True)[:limit]
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(http2=True) as client:
        tasks = [
            _fetch_one(client, semaphore, record.query, api_key, engine)
            for record in candidates
        ]
        results = await asyncio.gather(*tasks)

    return {query: data for query, data in results}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class SerpAPIProvider(SourceProvider):
    """
    Enriches QueryRecords with related queries from SerpAPI.

    The engine is taken from SourceConfig.domain (e.g. "google", "youtube",
    "google_patents", "google_news"). Defaults to "google" if domain is unset.

    Supported engines and their data source:
        google          related searches + people also asked
        youtube         related videos (titles)
        google_patents  organic patent results (titles)
        google_news     news headlines (titles)

    To add an engine: implement _process_<engine>() and register it in _PROCESSORS.

    Required env vars:
        SERPAPI_KEY  -- SerpAPI API key

    Settings (optional, set via sources create --setting key=value):
        limit          -- max queries to enrich (default 50)
        max_concurrent -- max simultaneous requests (default 5)
    """

    source_type = "serp"

    def validate(self) -> None:
        self._env(_ENV_API_KEY)

    def fetch(self) -> List[QueryRecord]:
        raise SourceError(
            "SerpAPIProvider does not support fetch(). "
            "Call enrich(queries) instead."
        )

    def enrich(self, queries: List[QueryRecord]) -> dict:
        api_key        = self._env(_ENV_API_KEY)
        engine         = self.config.domain or "google"
        limit          = int(self._setting("limit", 50))
        max_concurrent = int(self._setting("max_concurrent", _MAX_CONCURRENT))

        logger.info(
            "enriching up to %d queries via %s (max_concurrent=%d)",
            limit, engine, max_concurrent,
        )

        enriched_map = asyncio.run(
            _enrich_all(queries, api_key, engine, limit, max_concurrent)
        )

        enriched_count = sum(1 for v in enriched_map.values() if v["related"])
        logger.info(
            "enrichment complete via %s: %d/%d queries enriched",
            engine, enriched_count, len(enriched_map),
        )

        return enriched_map
