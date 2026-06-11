import pytest

from reheat.commands.enrich import cmd_enrich_embed, cmd_enrich_cluster
from reheat.commands.analyse import (
    cmd_analyse_summarise,
    cmd_analyse_opportunities,
    cmd_analyse_schedule,
)
from reheat.commands.project import cmd_project_create
from reheat.commands.report import (
    cmd_report_scatter_create,
    cmd_report_scatter_read,
    cmd_report_summary_create,
    cmd_report_summary_read,
    cmd_report_coverage_create,
    cmd_report_coverage_read,
    cmd_report_schedule_read,
    cmd_report_opportunities_read,
)


@pytest.fixture()
def analysed_run(backend, seeded_run):
    cmd_enrich_embed(backend, run_id=seeded_run)
    cmd_enrich_cluster(backend, run_id=seeded_run)
    cmd_analyse_summarise(backend, run_id=seeded_run)
    cmd_analyse_opportunities(backend, run_id=seeded_run)
    cmd_analyse_schedule(backend, run_id=seeded_run)
    cmd_project_create(backend, run_id=seeded_run)
    return seeded_run


def test_report_scatter_create_and_read(backend, analysed_run):
    cmd_report_scatter_create(backend, run_id=analysed_run)
    result = cmd_report_scatter_read(backend, run_id=analysed_run)
    assert "datasets" in result
    assert len(result["datasets"]) > 0


def test_report_summary_create_and_read(backend, analysed_run):
    cmd_report_summary_create(backend, run_id=analysed_run)
    result = cmd_report_summary_read(backend, run_id=analysed_run)
    assert "top_clusters" in result


def test_report_coverage_create_and_read(backend, analysed_run):
    cmd_report_coverage_create(backend, run_id=analysed_run)
    result = cmd_report_coverage_read(backend, run_id=analysed_run)
    assert "queries" in result
    assert len(result["queries"]) > 0


def test_report_schedule_read(backend, analysed_run):
    result = cmd_report_schedule_read(backend, run_id=analysed_run)
    assert "schedule" in result
    assert len(result["schedule"]) > 0


def test_report_opportunities_read(backend, analysed_run):
    result = cmd_report_opportunities_read(backend, run_id=analysed_run)
    assert "opportunities" in result


def test_report_read_before_create_raises(backend, seeded_run):
    with pytest.raises(ValueError, match="no scatter"):
        cmd_report_scatter_read(backend, run_id=seeded_run)
