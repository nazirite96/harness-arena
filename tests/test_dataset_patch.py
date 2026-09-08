import tomllib

from arena.datasets import patch_task_toml

ORIGINAL = """
[metadata]
difficulty = "15 min - 1 hour"

[verifier]
timeout_sec = 3000

[agent]
timeout_sec = 3000

[environment]
build_timeout_sec = 1800.0
cpus = 1
memory = '4G'
"""


def test_agent_phase_reaches_only_proxy(settings, tmp_path):
    (tmp_path / "task.toml").write_text(ORIGINAL)
    patch_task_toml(tmp_path, settings)
    cfg = tomllib.loads((tmp_path / "task.toml").read_text())
    assert cfg["agent"]["network_mode"] == "allowlist"
    assert cfg["agent"]["allowed_hosts"] == ["host.docker.internal"]
    assert cfg["agent"]["timeout_sec"] == 1800.0
    assert cfg["environment"]["network_mode"] == "allowlist"
    assert "registry.npmjs.org" in cfg["environment"]["allowed_hosts"]
    assert "host.docker.internal" in cfg["environment"]["allowed_hosts"]
    # original fields preserved
    assert cfg["environment"]["cpus"] == 1
    assert cfg["metadata"]["difficulty"] == "15 min - 1 hour"
