import pytest

from arena.config import Settings, load_versions


@pytest.fixture
def settings(tmp_path):
    env = {
        "ARENA_UPSTREAM_MODEL": "anthropic/claude-haiku-4-5-20251001",
        "ARENA_MODEL_ALIAS": "arena-model",
        "LITELLM_MASTER_KEY": "sk-test-master",
        "LITELLM_PORT": "4000",
        "ARENA_PROXY_HOST": "host.docker.internal",
        "ARENA_TASK_TIMEOUT_SEC": "1800",
        "ARENA_JOBS_DIR": str(tmp_path / "jobs"),
    }
    return Settings(env=env, versions=load_versions())
