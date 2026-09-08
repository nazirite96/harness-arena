"""Submission contract (PRD §6): load, validate, and apply operator overrides to a bundle.

All participant-facing messages are Korean. Identifiers stay English.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MAX_BUNDLE_BYTES = 5 * 1024 * 1024
BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".tar", ".so", ".dylib", ".dll", ".exe", ".bin", ".wasm", ".pyc", ".jar", ".class", ".o", ".a", ".mp4", ".mp3", ".woff", ".woff2", ".ttf"}
# PRD §6.2: complete agent products may not be submitted wholesale.
FORBIDDEN_DEPENDENCIES = ("oh-my-opencode", "oh-my-openagent", "opencode-superpowers", "claude-code-plugins")
FORBIDDEN_CONFIG_KEYS = ("model", "small_model", "provider", "enabled_providers", "disabled_providers", "permission", "share", "autoupdate", "server", "mcp")
SINGULAR_DIRS = {"agent": "agents", "plugin": "plugins", "tool": "tools", "skill": "skills", "command": "commands"}
# Hard-coded SWE-bench instance hints are a rule violation (PRD §10.4). Flagged, reviewed by operators.
INSTANCE_ID_PATTERN = re.compile(r"\b(django__django|sympy__sympy|astropy__astropy|matplotlib__matplotlib|scikit-learn__scikit-learn|sphinx-doc__sphinx|pytest-dev__pytest|pydata__xarray|psf__requests|pylint-dev__pylint|mwaskom__seaborn|pallets__flask)-\d+\b")


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = []
        for e in self.errors:
            lines.append(f"[오류] {e}")
        for w in self.warnings:
            lines.append(f"[경고] {w}")
        if self.ok:
            lines.append("[통과] 번들 검증을 통과했습니다.")
        return "\n".join(lines)


@dataclass
class Bundle:
    root: Path
    team: str
    main_agent: str
    description: str
    config: dict[str, Any]  # opencode.json (may be empty)
    agents: dict[str, Path]  # agent name -> file
    manifest: dict[str, Any]  # arena.yaml raw


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas (opencode accepts JSONC)."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"(^|[^:\"'])//[^\n]*", r"\1", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def load_jsonc(path: Path) -> dict[str, Any]:
    return json.loads(_strip_jsonc(path.read_text(encoding="utf-8")) or "{}")


def load_bundle(root: Path) -> tuple[Bundle | None, ValidationResult]:
    """Structural load. Returns (bundle, result). bundle is None when arena.yaml is unusable."""
    r = ValidationResult()
    root = root.resolve()
    manifest_path = root / "arena.yaml"
    if not manifest_path.exists():
        r.errors.append("arena.yaml 이 번들 루트에 없습니다.")
        return None, r
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        r.errors.append(f"arena.yaml 을 읽을 수 없습니다 (YAML 문법 오류): {exc}")
        return None, r
    if not isinstance(manifest, dict):
        r.errors.append("arena.yaml 최상위는 매핑(key: value)이어야 합니다.")
        return None, r
    for key in ("team", "main_agent", "description"):
        if not str(manifest.get(key) or "").strip():
            r.errors.append(f"arena.yaml 에 필수 항목 '{key}' 가 없습니다.")
    if r.errors:
        return None, r
    team = str(manifest["team"]).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", team):
        r.errors.append("arena.yaml 의 team 은 소문자·숫자·하이픈 2~40자여야 합니다 (예: team-alpha).")

    agents: dict[str, Path] = {}
    agents_dir = root / ".opencode" / "agents"
    if agents_dir.is_dir():
        for p in sorted(agents_dir.glob("*.md")):
            agents[p.stem] = p
    for singular, plural in SINGULAR_DIRS.items():
        if (root / ".opencode" / singular).exists():
            r.errors.append(f".opencode/{singular}/ 대신 .opencode/{plural}/ 를 사용하세요 (ADR-0002).")

    main_agent = str(manifest["main_agent"]).strip()
    if main_agent not in agents:
        r.errors.append(f"main_agent '{main_agent}' 에 해당하는 .opencode/agents/{main_agent}.md 가 없습니다.")

    config: dict[str, Any] = {}
    cfg_path = root / "opencode.json"
    if cfg_path.exists():
        try:
            config = load_jsonc(cfg_path)
        except json.JSONDecodeError as exc:
            r.errors.append(f"opencode.json 을 읽을 수 없습니다 (JSON 문법 오류): {exc}")
    bundle = Bundle(root=root, team=team, main_agent=main_agent, description=str(manifest["description"]), config=config, agents=agents, manifest=manifest)
    return bundle, r


def validate_bundle(root: Path) -> ValidationResult:
    bundle, r = load_bundle(root)
    if bundle is None:
        return r
    root = bundle.root

    # --- forbidden config keys (they are overwritten anyway; forbid to avoid confusion)
    for key in FORBIDDEN_CONFIG_KEYS:
        if key in bundle.config:
            r.errors.append(f"opencode.json 의 '{key}' 는 운영진이 고정합니다. 항목을 삭제하세요.")
    # --- plugin array: local files only
    for item in bundle.config.get("plugin", []) or []:
        spec = item[0] if isinstance(item, list) else item
        if not isinstance(spec, str) or not (spec.startswith("file://") or spec.startswith("./") or spec.startswith(".opencode/")):
            r.errors.append(f"opencode.json plugin '{spec}' 는 npm 패키지 참조입니다. 플러그인은 .opencode/plugins/ 로컬 파일만 허용됩니다.")
    # --- agent frontmatter model
    for name, path in bundle.agents.items():
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        if fm is None:
            r.errors.append(f".opencode/agents/{name}.md 의 frontmatter(---)를 읽을 수 없습니다.")
            continue
        if "model" in fm:
            r.warnings.append(f".opencode/agents/{name}.md 의 model 은 고정 모델로 덮어써집니다.")
        if name == bundle.main_agent and fm.get("mode") not in (None, "primary", "all"):
            r.errors.append(f"main_agent '{name}' 의 mode 는 primary 여야 합니다 (현재: {fm.get('mode')}).")
    # --- package.json dependencies
    for pkg_path in (root / "package.json", root / ".opencode" / "package.json"):
        if pkg_path.exists():
            try:
                pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                r.errors.append(f"{pkg_path.relative_to(root)} JSON 문법 오류: {exc}")
                continue
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for dep in deps:
                if any(f in dep for f in FORBIDDEN_DEPENDENCIES):
                    r.errors.append(f"{pkg_path.relative_to(root)} 의 의존성 '{dep}' 는 금지 목록에 있습니다 (완성형 에이전트 플러그인).")
    # --- size and binaries
    total = 0
    for p in root.rglob("*"):
        if p.is_dir() or ".git" in p.parts or "node_modules" in p.parts:
            continue
        total += p.stat().st_size
        if p.suffix.lower() in BINARY_EXTENSIONS or _looks_binary(p):
            r.errors.append(f"바이너리 파일은 허용되지 않습니다: {p.relative_to(root)}")
    if total > MAX_BUNDLE_BYTES:
        r.errors.append(f"번들 크기 {total / 1024 / 1024:.1f}MB 가 상한 5MB 를 넘습니다.")
    # --- instance-id hints (operator review)
    for p in root.rglob("*"):
        if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts and p.suffix.lower() in {".md", ".ts", ".js", ".json", ".yaml", ".yml", ".txt"}:
            try:
                hits = INSTANCE_ID_PATTERN.findall(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                hits = []
            if hits:
                r.errors.append(f"{p.relative_to(root)} 에 SWE-bench 인스턴스 ID 패턴이 있습니다 (규칙 §10.4): {', '.join(sorted(set(hits)))[:80]}")
    return r


def _looks_binary(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:4096]
    except OSError:
        return False
    return b"\x00" in chunk


_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _frontmatter(text: str) -> dict[str, Any] | None:
    m = _FM.match(text)
    if not m:
        return {} if not text.lstrip().startswith("---") else None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _set_frontmatter_model(text: str, model: str) -> str:
    m = _FM.match(text)
    if not m:
        return f"---\nmodel: {model}\n---\n{text}"
    fm = yaml.safe_load(m.group(1)) or {}
    fm["model"] = model
    return f"---\n{yaml.safe_dump(fm, sort_keys=False).rstrip()}\n---\n{m.group(2)}"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def stage_bundle(bundle: Bundle, dest: Path, *, arena_config: dict[str, Any], model: str) -> dict[str, Any]:
    """Copy the bundle into `dest` laid out as an opencode global config dir, with overrides applied.

    Returns the merged opencode.json that must be written as `<config dir>/opencode.json`.
    Layout produced:
        dest/agents/*.md  dest/plugins/*  dest/tools/*  dest/skills/**  dest/commands/*
        dest/package.json (if any)  dest/AGENTS.md (copied to /testbed by the adapter)
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    oc = bundle.root / ".opencode"
    for sub in ("agents", "plugins", "tools", "skills", "commands"):
        src = oc / sub
        if src.is_dir():
            shutil.copytree(src, dest / sub, ignore=shutil.ignore_patterns("node_modules", ".git"))
    for name, path in bundle.agents.items():
        target = dest / "agents" / f"{name}.md"
        target.write_text(_set_frontmatter_model(path.read_text(encoding="utf-8"), model), encoding="utf-8")
    for pkg in (bundle.root / "package.json", oc / "package.json"):
        if pkg.exists():
            shutil.copy(pkg, dest / "package.json")
            break
    if (bundle.root / "AGENTS.md").exists():
        shutil.copy(bundle.root / "AGENTS.md", dest / "AGENTS.md")

    team_cfg = {k: v for k, v in bundle.config.items() if k not in FORBIDDEN_CONFIG_KEYS}
    merged = deep_merge(team_cfg, arena_config)
    merged["default_agent"] = bundle.main_agent
    (dest / "opencode.json").write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
