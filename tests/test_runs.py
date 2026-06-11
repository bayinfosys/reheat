from reheat.commands.runs import cmd_runs_list, cmd_runs_show, cmd_runs_delete


def test_runs_list_empty(backend):
    result = cmd_runs_list(backend)
    assert result == []


def test_runs_list_after_seed(backend, seeded_run):
    result = cmd_runs_list(backend)
    assert len(result) == 1
    assert result[0]["run_id"] == seeded_run
    assert result[0]["domain"] == "example.com"
    assert result[0]["query_count"] == 20


def test_runs_show(backend, seeded_run):
    result = cmd_runs_show(backend, run_id=seeded_run)
    assert result["run_id"] == seeded_run
    assert len(result["queries"]) == 20


def test_runs_show_missing_raises(backend):
    import pytest
    with pytest.raises(ValueError, match="not found"):
        cmd_runs_show(backend, run_id="nonexistent")


def test_runs_delete(backend, seeded_run):
    cmd_runs_delete(backend, run_id=seeded_run)
    result = cmd_runs_list(backend)
    assert result == []
