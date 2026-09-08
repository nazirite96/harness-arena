import yaml

from arena import proxy


def test_render_exposes_single_alias(settings, monkeypatch, tmp_path):
    monkeypatch.setattr(proxy, "RENDERED", tmp_path / "litellm.config.yaml")
    out = proxy.render_config(settings)
    cfg = yaml.safe_load(out.read_text())
    assert [m["model_name"] for m in cfg["model_list"]] == ["arena-model"]
    assert cfg["model_list"][0]["litellm_params"]["api_key"] == "os.environ/ANTHROPIC_API_KEY"
    assert cfg["general_settings"]["store_prompts_in_spend_logs"] is True
    # provider secrets never land in the rendered file
    assert "sk-" not in out.read_text()
