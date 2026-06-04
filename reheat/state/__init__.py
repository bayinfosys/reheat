import logging
import os
from pathlib import Path

from dynawrap.backends.base import DBBackend

from reheat.state.user import UserState


logger = logging.getLogger(__name__)

# FIXME: we should not access this constant, but use get_user()
USER_ID = "default"

SOURCES_TABLE = "reheat_sources"
USER_TABLE = "reheat_user"
PROJECTIONS_TABLE = "reheat_projections"
ENRICHMENTS_TABLE = "reheat_enrichments"
MODELS_TABLE = "reheat_models"
REPORTS_TABLE = "reheat_reports"
RUNS_TABLE = "reheat_runs"

TABLES = [
    USER_TABLE,
    SOURCES_TABLE,
    RUNS_TABLE,
    ENRICHMENTS_TABLE,
    PROJECTIONS_TABLE,
    REPORTS_TABLE,
    MODELS_TABLE,
]


def init_backend(location: str = None) -> DBBackend:
    """
    Construct and return the appropriate backend.

    location can be:
        postgresql://...   postgres backend
        /path/to/dir       json file backend (local dev, default)

    Falls back to DATABASE_URL, then CONFIG_LOCATION, then ~/.reheat.
    """
    loc = (
        location
        or os.environ.get("DATABASE_URL")
        or os.environ.get("CONFIG_LOCATION")
        or str(Path.home() / ".reheat")
    )

    if loc.startswith("postgresql://") or loc.startswith("postgres://"):
        import psycopg2
        from dynawrap.backends.postgres import PostgresBackend
        conn = psycopg2.connect(loc)
        for table in TABLES:
            PostgresBackend.create_table(conn, table)
        logger.info("using postgres backend")
        return PostgresBackend(conn)

    if loc.startswith("dynamodb://"):
        import boto3
        from dynawrap.backends.dynamodb import DynamoDBBackend
        logger.info("using dynamodb backend")
        return DynamoDBBackend(boto3.client("dynamodb"))

    from dynawrap.backends.json_file import JsonFileBackend
    logger.info("using json file backend at %s", loc)
    return JsonFileBackend(loc)


def get_user(backend: DBBackend) -> UserState:
    """get the user object
    TODO: also make a put_user to centralise that code
    """
    return backend.get(USER_TABLE, UserState, user_id=USER_ID) or UserState()


def get_user_id(backend: DBBackend) -> str:
    """get the string id for the user
    When a multi-tennant setup is used, cache the user identity here for db lookups
    TODO: cache this with lru
    """
    return get_user(backend).user_id
