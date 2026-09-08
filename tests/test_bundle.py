import json
import shutil
from pathlib import Path

from arena.bundle import load_bundle, stage_bundle, validate_bundle
from arena.config import REPO_ROOT

TEMPLATE = REPO_ROOT / "starter-kit" / "bundle"


def copy_template(tmp_path: Path) -> Path:
    dst = tmp_path / "bundle"
    shutil.copytree(TEMPLATE, dst)
    return dst


def test_starter_kit_template_is_valid():
    r = validate_bundle(TEMPLATE)
    assert r.ok, r.render()


def test_missing_arena_yaml(tmp_path):
    b = copy_template(tmp_path)
    (b / "arena.yaml").unlink()
    r = validate_bundle(b)
    assert any("arena.yaml" in e for e in r.errors)


def test_missing_main_agent(tmp_path):
    b = copy_template(tmp_path)
    (b / ".opencode" / "agents" / "main.md").unlink()
    r = validate_bundle(b)
    assert any("main_agent" in e for e in r.errors)


def test_forbidden_config_key_and_npm_plugin(tmp_path):
    b = copy_template(tmp_path)
    cfg = json.loads((b / "opencode.json").read_text())
    cfg["model"] = "anthropic/claude-opus-5"
    cfg["plugin"] = ["oh-my-openagent@latest"]
    (b / "opencode.json").write_text(json.dumps(cfg))
    r = validate_bundle(b)
    assert any("'model'" in e for e in r.errors)
    assert any("npm 패키지" in e for e in r.errors)


def test_forbidden_dependency(tmp_path):
    b = copy_template(tmp_path)
    pkg = json.loads((b / "package.json").read_text())
    pkg["dependencies"]["oh-my-openagent"] = "*"
    (b / "package.json").write_text(json.dumps(pkg))
    r = validate_bundle(b)
    assert any("금지 목록" in e for e in r.errors)


def test_singular_dir_rejected(tmp_path):
    b = copy_template(tmp_path)
    (b / ".opencode" / "plugin").mkdir()
    r = validate_bundle(b)
    assert any(".opencode/plugins/" in e for e in r.errors)


def test_binary_and_instance_hint(tmp_path):
    b = copy_template(tmp_path)
    (b / "blob.bin").write_bytes(b"\x00\x01\x02")
    (b / "AGENTS.md").write_text("if repo is django__django-15098 then patch trans_real")
    r = validate_bundle(b)
    assert any("바이너리" in e for e in r.errors)
    assert any("인스턴스 ID" in e for e in r.errors)


def test_stage_forces_model_and_default_agent(tmp_path):
    b = copy_template(tmp_path)
    bundle, r = load_bundle(b)
    assert bundle and r.ok
    arena_cfg = {"model": "arena/arena-model", "provider": {"arena": {"npm": "x"}}, "permission": "allow"}
    merged = stage_bundle(bundle, tmp_path / "staged", arena_config=arena_cfg, model="arena/arena-model")
    assert merged["model"] == "arena/arena-model"
    assert merged["default_agent"] == "main"
    assert merged["permission"] == "allow"
    assert merged["agent"]["build"]["disable"] is True  # team config preserved
    main = (tmp_path / "staged" / "agents" / "main.md").read_text()
    assert "model: arena/arena-model" in main
    assert (tmp_path / "staged" / "plugins" / "arena-hooks.ts").exists()
    assert (tmp_path / "staged" / "tools" / "run_related_tests.ts").exists()
    assert (tmp_path / "staged" / "package.json").exists()
    assert (tmp_path / "staged" / "AGENTS.md").exists()
    assert json.loads((tmp_path / "staged" / "opencode.json").read_text()) == merged
