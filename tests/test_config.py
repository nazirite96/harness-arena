from arena.config import load_versions


def test_versions_lock_pins_everything():
    v = load_versions()
    for k in ("HARBOR_VERSION", "OPENCODE_VERSION", "LITELLM_IMAGE", "HARBOR_DATASETS_COMMIT"):
        assert v[k], k
    assert v["HARBOR_VERSION"] == "0.22.0"


def test_upstream_key_env_inferred(settings):
    assert settings.upstream_key_env == "ANTHROPIC_API_KEY"
    assert settings.opencode_model_string == "arena/arena-model"
    assert settings.proxy_url_for_containers == "http://host.docker.internal:4000/v1"
