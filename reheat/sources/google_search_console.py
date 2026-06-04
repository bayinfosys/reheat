import logging
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from reheat.state.execution import QueryRecord, SourceConfig
from reheat.sources.base import SourceProvider, SourceError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _normalise_domain(domain: str) -> str:
    if (
        domain.startswith("sc-domain:")
        or domain.startswith("https://")
        or domain.startswith("http://")
    ):
        return domain
    return f"sc-domain:{domain}"


def _build_service(
    client_secrets_path: str,
    token_path: str,
):
    """
    Build a Search Console API service client using OAuth2.
    Opens browser on first run, persists token for subsequent runs.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    secrets = Path(client_secrets_path).expanduser()
    token = Path(token_path).expanduser()

    if not secrets.exists():
        raise SourceError(
            f"client_secrets.json not found at {secrets}. "
            "Download from Google Cloud Console > APIs & Services > "
            "Credentials > OAuth 2.0 Client IDs (Desktop app type)."
        )

    credentials = None

    if token.exists():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(token), SCOPES
            )
        except Exception:
            logger.warning("failed to load token, re-authenticating")

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                logger.info("refreshed OAuth2 token")
            except Exception:
                credentials = None

        if not credentials:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secrets), SCOPES
            )
            credentials = flow.run_local_server(port=0)
            logger.info("completed OAuth2 consent flow")

        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(credentials.to_json())

    try:
        return build("searchconsole", "v1", credentials=credentials)
    except Exception as e:
        raise SourceError(f"failed to build Search Console service: {e}") from e


class GoogleSearchConsoleProvider(SourceProvider):
    """
    Fetches search analytics from Google Search Console.

    Required credentials:
        client_secrets_path  -- path to OAuth2 client_secrets.json
        token_path           -- path to persist the OAuth2 token

    Settings:
        days    -- lookback window in days (default 90)
        limit   -- max queries to return (default 200)
    """

    source_type = "google_search_console"

    def validate(self) -> None:
        self._credential("client_secrets_path")

    def fetch(self) -> List[QueryRecord]:
        client_secrets_path = self._credential("client_secrets_path")
        token_path = self._credential("token_path")
        domain = self.config.domain
        days = int(self._setting("days", 90))
        limit = int(self._setting("limit", 200))

        if not domain:
            raise SourceError(
                f"source {self.config.source_id!r} has no domain configured"
            )

        domain = _normalise_domain(domain)
        logger.info(
            "fetching queries from Search Console for %s", domain
        )

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        service = _build_service(client_secrets_path, token_path)

        request_body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["query"],
            "rowLimit": limit,
            "startRow": 0,
            "dataState": "final",
        }

        try:
            response = (
                service.searchanalytics()
                .query(siteUrl=domain, body=request_body)
                .execute()
            )
        except Exception as e:
            raise SourceError(
                f"Search Console API request failed: {e}"
            ) from e

        rows = response.get("rows", [])
        logger.info("received %d query rows", len(rows))

        records = []
        for row in rows:
            try:
                records.append(QueryRecord(
                    query=row["keys"][0],
                    clicks=int(row.get("clicks", 0)),
                    impressions=int(row.get("impressions", 0)),
                    ctr=float(row.get("ctr", 0.0)),
                    position=float(row.get("position", 0.0)),
                ))
            except Exception:
                logger.warning("failed to parse row: %s", row)

        logger.info("parsed %d query records", len(records))
        return records
