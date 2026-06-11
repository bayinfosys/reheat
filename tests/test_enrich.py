import pytest
from unittest.mock import patch

from reheat.commands.enrich import (
    cmd_enrich_tags,
    cmd_enrich_embed,
    cmd_enrich_cluster,
    cmd_enrich_adjacent,
)


def test_enrich_tags(backend, seeded_run):
    result = cmd_enrich_tags(backend, run_id=seeded_run)
    assert result["run_id"] == seeded_run
    assert result["tagged"] > 0


def test_enrich_embed(backend, seeded_run):
    result = cmd_enrich_embed(backend, run_id=seeded_run)
    assert result["run_id"] == seeded_run
    assert result["embedded"] == 20


def test_enrich_cluster(backend, seeded_run):
    cmd_enrich_embed(backend, run_id=seeded_run)
    result = cmd_enrich_cluster(backend, run_id=seeded_run)
    assert result["run_id"] == seeded_run
    assert result["k"] > 0


def test_enrich_cluster_requires_embeddings(backend, seeded_run):
    with pytest.raises(ValueError, match="no embeddings"):
        cmd_enrich_cluster(backend, run_id=seeded_run)


def test_enrich_adjacent_mock(backend, seeded_run, serp_responses):
    """
    Seed a serp SourceConfig then patch SerpAPIProvider.enrich so no
    HTTP calls are made.
    """
    from datetime import datetime, timezone
    from reheat.state import SOURCES_TABLE, SourceConfig
    from reheat.state.backend import get_user_id

    serp_source = SourceConfig(
        user_id=get_user_id(backend),
        source_id="serp:google",
        source_type="serp",
        domain="google",
        settings={"limit": 50},
        created_at=datetime.now(timezone.utc),
    )
    backend.save(SOURCES_TABLE, serp_source)

    with patch(
        "reheat.sources.serp.SerpAPIProvider.enrich",
        return_value=serp_responses,
    ):
        result = cmd_enrich_adjacent(backend, run_id=seeded_run)

    assert result["run_id"] == seeded_run
    assert result["total_enriched"] > 0
