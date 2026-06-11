import logging
from datetime import date, timedelta
from pathlib import Path
from typing import List

from reheat.sources.base import SourceError, SourceProvider
from reheat.state import QueryRecord

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

_ENV_SECRETS = "GOOGLE_CLIENT_SECRETS_PATH"
_ENV_TOKEN   = "GOOGLE_TOKEN_PATH"


def _normalise_domain(domain: str) -> str:
    if (
        domain.startswith("sc-domain:")
        or domain.startswith("https://")
        or domain.startswith("http://")
    ):
        return domain
    return f"sc-domain:{domain}"


def _build_service(client_secrets_path: str, token_path: str):
    """
    Build a Search Console API service client using OAuth2.
    Opens a browser on first run to complete the consent flow.
    Persists the token to GOOGLE_TOKEN_PATH for subsequent runs.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    secrets = Path(client_secrets_path).expanduser()
    token = Path(token_path).expanduser()

    if not secrets.exists():
        raise SourceError(
            f"client secrets file not found at {secrets}. "
            f"Check that {_ENV_SECRETS} points to the correct path."
        )

    credentials = None

    if token.exists():
        try:
            credentials = Credentials.from_authorized_user_file(str(token), SCOPES)
        except Exception:
            logger.warning("failed to load token at %s, re-authenticating", token)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                logger.info("refreshed OAuth2 token")
            except Exception:
                credentials = None

        if not credentials:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
            except ValueError as e:
                raise SourceError(
                    f"invalid client secrets file at {secrets}: {e}. "
                    "The file must be an OAuth 2.0 Client ID of type Desktop app. "
                    "In Google Cloud Console go to APIs & Services > Credentials, "
                    "create an OAuth 2.0 Client ID, select Desktop app, and "
                    "download the JSON file."
                ) from e
            credentials = flow.run_local_server(port=0)
            logger.info("completed OAuth2 consent flow")

        token.parent.mkdir(parents=True, exist_ok=True)
        token.write_text(credentials.to_json())
        logger.info("token written to %s", token)

    try:
        return build("searchconsole", "v1", credentials=credentials)
    except Exception as e:
        raise SourceError(f"failed to build Search Console service: {e}") from e


class GoogleSearchConsoleProvider(SourceProvider):
    """
    Fetches search analytics from Google Search Console.

    Required env vars:
        GOOGLE_CLIENT_SECRETS_PATH  -- path to an OAuth 2.0 Desktop app
                                       client_secrets JSON file
        GOOGLE_TOKEN_PATH           -- path where the OAuth2 token is
                                       written after the consent flow;
                                       must point to a persistent location

    Settings (optional, set via sources create --setting key=value):
        days   -- lookback window in days (default 90)
        limit  -- max queries to return (default 200)
    """

    source_type = "google_search_console"

    def validate(self) -> None:
        self._env(_ENV_SECRETS)
        self._env(_ENV_TOKEN)

    def fetch(self) -> List[QueryRecord]:
        client_secrets_path = self._env(_ENV_SECRETS)
        token_path = self._env(_ENV_TOKEN)
        domain = self.config.domain
        days = int(self._setting("days", 90))
        limit = int(self._setting("limit", 200))

        if not domain:
            raise SourceError(
                f"source {self.config.source_id!r} has no domain configured"
            )

        domain = _normalise_domain(domain)
        logger.info("fetching queries from Search Console for %s", domain)

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
            raise SourceError(f"Search Console API request failed: {e}") from e

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
