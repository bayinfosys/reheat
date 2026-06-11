import logging
import os
from pathlib import Path

from dynawrap.backends.base import DBBackend

from .user import UserState
from .tables import TABLES, USER_TABLE

logger = logging.getLogger(__name__)

# FIXME: we should not access this constant, but use get_user()
USER_ID = "default"


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

    if loc is None:
        raise ValueError(
            "no backend configured. Set DATABASE_URL to a postgres connection "
            "string or CONFIG_LOCATION to a directory path."
        )


def get_user(backend: DBBackend) -> UserState:
    """get the user object
    TODO: also make a put_user to centralise that code
    """
    return backend.get(USER_TABLE, UserState, user_id=USER_ID) or UserState()


def get_user_id(backend: DBBackend) -> str:
    """get the string id for the user
    cache the user identity here for db lookups
    TODO: cache this with lru
    """
    return get_user(backend).user_id
