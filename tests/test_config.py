from reheat.commands.config import cmd_config_show, cmd_config_set


def test_config_show_returns_all_fields(backend):
    result = cmd_config_show(backend)
    expected_keys = {
        "user_id", "default_source_id", "embedding_provider",
        "embedding_model", "instruct_model", "projection_method",
        "cluster_k", "summarise_top_n", "fetch_days",
        "fetch_limit", "serp_enrich_limit", "serp_delay",
    }
    assert expected_keys == set(result.keys())


def test_config_set_cluster_k(backend):
    cmd_config_set(backend, key="cluster_k", value="8")
    result = cmd_config_show(backend)
    assert result["cluster_k"] == 8


def test_config_set_unknown_key_raises(backend):
    import pytest
    with pytest.raises(ValueError, match="unknown config key"):
        cmd_config_set(backend, key="summary_model", value="gpt-4")
