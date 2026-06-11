import pytest

from reheat.commands.enrich import cmd_enrich_embed, cmd_enrich_cluster
from reheat.commands.analyse import (
    cmd_analyse_summarise,
    cmd_analyse_opportunities,
    cmd_analyse_schedule,
    cmd_analyse_overview,
)


@pytest.fixture()
def clustered_run(backend, seeded_run):
    cmd_enrich_embed(backend, run_id=seeded_run)
    cmd_enrich_cluster(backend, run_id=seeded_run)
    return seeded_run


def test_analyse_summarise(backend, clustered_run):
    result = cmd_analyse_summarise(backend, run_id=clustered_run)
    assert result["run_id"] == clustered_run
    assert result["labelled"] > 0
    assert isinstance(result["summaries"], list)


def test_analyse_opportunities(backend, clustered_run):
    result = cmd_analyse_opportunities(backend, run_id=clustered_run)
    assert result["run_id"] == clustered_run
    assert "opportunities" in result


def test_analyse_schedule(backend, clustered_run):
    cmd_analyse_summarise(backend, run_id=clustered_run)
    cmd_analyse_opportunities(backend, run_id=clustered_run)
    result = cmd_analyse_schedule(backend, run_id=clustered_run)
    assert result["run_id"] == clustered_run
    assert result["scheduled"] > 0


def test_analyse_overview(backend, clustered_run):
    cmd_analyse_summarise(backend, run_id=clustered_run)
    cmd_analyse_opportunities(backend, run_id=clustered_run)
    cmd_analyse_schedule(backend, run_id=clustered_run)
    result = cmd_analyse_overview(backend, run_id=clustered_run)
    assert result["run_id"] == clustered_run
    assert result["paragraphs"] > 0


def test_analyse_schedule_missing_summaries_raises(backend, clustered_run):
    # opportunities present but no summaries
    cmd_analyse_opportunities(backend, run_id=clustered_run)
    with pytest.raises(ValueError, match="no summaries"):
        cmd_analyse_schedule(backend, run_id=clustered_run)
