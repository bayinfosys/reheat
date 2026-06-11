import json
import os
import random
from pathlib import Path
from unittest.mock import patch

import psycopg2
import pytest

from reheat.commands import register_all_commands
from reheat.providers.embeddings import EmbeddingProvider
from reheat.providers.instruct import InstructProvider
from reheat.state.backend import init_backend
from reheat.state.tables import TABLES

register_all_commands()

FIXTURE_DIR = Path(__file__).parent / "fixtures"

TEST_DB_URL = os.environ.get(
    "REHEAT_TEST_DB",
    "postgresql://localhost/reheat_test",
)

# ---------------------------------------------------------------------------
# Postgres backend
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db_conn():
    from dynawrap.backends.postgres import PostgresBackend
    conn = psycopg2.connect(TEST_DB_URL)
    for table in TABLES:
        PostgresBackend.create_table(conn, table)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def backend(db_conn):
    """
    Truncate all tables before each test so tests are fully isolated.
    PostgresBackend commits internally so rollback teardown is not viable.
    """
    from dynawrap.backends.postgres import PostgresBackend
    cur = db_conn.cursor()
    for table in TABLES:
        cur.execute(f"TRUNCATE TABLE {table} CASCADE")
    db_conn.commit()
    cur.close()
    yield PostgresBackend(db_conn)


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def gsc_queries():
    with open(FIXTURE_DIR / "gsc_queries.json") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def serp_responses():
    with open(FIXTURE_DIR / "serp_response.json") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Provider mocks
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 16


class _DummyEmbeddingProvider(EmbeddingProvider):
    provider_name = "dummy"
    model_name    = "dummy"

    def embed(self, texts: list[str]) -> list[list[float]]:
        rng = random.Random(42)
        return [
            [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
            for _ in texts
        ]

    def dimension(self) -> int:
        return EMBEDDING_DIM


class _DummyInstructProvider(InstructProvider):
    provider_name = "dummy"
    model_name    = "dummy"

    _SUMMARIES = json.dumps({"summaries": [
        {
            "cluster_id": str(i),
            "label": f"Test Topic {i}",
            "description": f"Description for topic {i}.",
            "adjacent_count": 3,
        }
        for i in range(4)
    ]})

    _SCHEDULE = json.dumps({"schedule": [
        {
            "priority": 1,
            "title": "Test Article Title",
            "cluster_label": "Test Topic 0",
            "opportunity_type": "expand",
            "rationale": "High adjacent demand with 3 related queries.",
            "target_queries": ["test query one", "test query two"],
            "seo_terms": ["term one", "term two", "term three"],
        },
        {
            "priority": 2,
            "title": "New Topic Article",
            "cluster_label": "Test Topic 1",
            "opportunity_type": "new",
            "rationale": "No existing content for this gap.",
            "target_queries": ["gap query"],
            "seo_terms": ["gap term"],
        },
    ]})

    _OVERVIEW = json.dumps({"paragraphs": [
        "Paragraph one.",
        "Paragraph two.",
        "Paragraph three.",
    ]})

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        # Route by the unique structural marker in each prompt template.
        # SCHEDULE_PROMPT contains "content schedule items ordered by priority"
        # OVERVIEW_PROMPT contains "three-paragraph plain-English overview"
        # SUMMARISE_PROMPT (summarise.py) contains neither -- returns summaries
        if "three-paragraph" in prompt:
            return self._OVERVIEW
        if "content schedule items" in prompt:
            return self._SCHEDULE
        return self._SUMMARIES


@pytest.fixture()
def dummy_embedding_provider():
    return _DummyEmbeddingProvider()


@pytest.fixture()
def dummy_instruct_provider():
    return _DummyInstructProvider()


@pytest.fixture(autouse=True)
def patch_providers(dummy_embedding_provider, dummy_instruct_provider):
    with (
        patch(
            "reheat.providers.embeddings.get_embedding_provider",
            return_value=dummy_embedding_provider,
        ),
        patch(
            "reheat.providers.instruct.get_instruct_provider",
            return_value=dummy_instruct_provider,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Seeded run fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded_run(backend, gsc_queries):
    from datetime import datetime, timezone
    from reheat.state import RUNS_TABLE, RunRecord
    from reheat.state.runs import QueryRecord
    from reheat.state.backend import get_user_id

    queries = [
        QueryRecord(
            query=row["query"],
            clicks=row["clicks"],
            impressions=row["impressions"],
            ctr=row["ctr"],
            position=row["position"],
        )
        for row in gsc_queries
    ]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_test"
    run = RunRecord(
        user_id=get_user_id(backend),
        run_id=run_id,
        domain="example.com",
        source_id="gsc:example-com",
        queries=queries,
        fetched_at=datetime.now(timezone.utc),
    )
    backend.save(RUNS_TABLE, run)
    return run_id
