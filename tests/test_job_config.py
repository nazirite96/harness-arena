from pathlib import Path

from arena import harbor_runner


def test_vanilla_job_config_forces_model_and_key(settings):
    cfg = harbor_runner.vanilla_job_config(
        settings, dataset_path=Path("/ds"), job_name="j", api_key="sk-run-key"
    )
    agent = cfg["agents"][0]
    assert agent["name"] == "opencode"
    assert agent["model_name"] == "arena/arena-model"
    assert agent["kwargs"]["version"] == settings.opencode_version
    oc = agent["kwargs"]["opencode_config"]
    assert oc["model"] == "arena/arena-model"
    assert oc["enabled_providers"] == ["arena"]
    assert oc["provider"]["arena"]["npm"] == "@ai-sdk/openai-compatible"
    assert oc["provider"]["arena"]["options"]["apiKey"] == "{env:ARENA_API_KEY}"
    assert oc["share"] == "disabled" and oc["autoupdate"] is False
    assert agent["env"] == {"ARENA_API_KEY": "sk-run-key"}
    # the raw key never appears inside the opencode config itself
    assert "sk-run-key" not in str(oc)


def test_bundle_job_config_uses_adapter(settings):
    cfg = harbor_runner.bundle_job_config(
        settings, dataset_path=Path("/ds"), job_name="j", api_key="sk-run-key",
        bundle_repo="https://github.com/x/y.git", bundle_commit="abc1234def", run_id="run-1",
    )
    agent = cfg["agents"][0]
    assert "name" not in agent
    assert agent["import_path"] == "arena_harness:OpenCodeBundleAgent"
    assert agent["kwargs"]["bundle_repo"] == "https://github.com/x/y.git"
    assert agent["kwargs"]["bundle_commit"] == "abc1234def"
    assert agent["kwargs"]["run_id"] == "run-1"
    assert agent["model_name"] == "arena/arena-model"
