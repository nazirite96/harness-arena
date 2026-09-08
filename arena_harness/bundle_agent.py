"""OpenCodeBundleAgent: Harbor agent that runs a participant's opencode bundle.

Reuses Harbor's builtin OpenCode agent for install (pinned `opencode-ai`), run
(`opencode run --format=json`) and ATIF trajectory parsing. Adds:

* bundle acquisition on the HOST (git clone at a pinned commit, or a local path),
* validation against the submission contract (arena.bundle),
* operator overrides (model/provider/permission forced; ADR-0003),
* upload of the staged bundle into the container's opencode global config dir,
* `AGENTS.md` copied into the task repo root (/testbed),
* plugin dependency pre-install (`bun install`) while registries are reachable,
* `--agent <main_agent>` on the run command.

Kwargs (via `--ak k=v` or agents[].kwargs):
    bundle_repo     git URL or local directory
    bundle_commit   commit SHA (required for git URLs)
    run_id          arena run id (recorded in the trajectory metadata)
    version         opencode version (from versions.lock)
    opencode_config arena provider/model config fragment (see arena.harbor_runner)
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, override

from harbor.agents.installed.opencode import OpenCode
from harbor.environments.base import BaseEnvironment

from arena.bundle import load_bundle, stage_bundle, validate_bundle

BUNDLE_CACHE = Path.home() / ".cache" / "harness-arena" / "bundles"
REMOTE_BUNDLE_DIR = "/installed-agent/arena-bundle"
REMOTE_CONFIG_DIR = "$HOME/.config/opencode"  # expanded by the shell; never shlex-quote it
REPO_ROOT_IN_TASK = "/testbed"


class BundleError(RuntimeError):
    """Bundle could not be acquired or failed validation (not an agent runtime error)."""


def acquire_bundle(repo: str, commit: str | None) -> Path:
    """Return a local directory with the bundle checked out at `commit` (host side)."""
    src = Path(repo).expanduser()
    if src.is_dir():
        return src.resolve()
    if not commit or len(commit) < 7:
        raise BundleError("bundle_commit (커밋 SHA) 이 필요합니다.")
    dest = BUNDLE_CACHE / commit
    if (dest / ".git").exists():
        return dest
    BUNDLE_CACHE.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="arena-bundle-", dir=BUNDLE_CACHE))
    try:
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
        subprocess.run(["git", "-C", str(tmp), "remote", "add", "origin", repo], check=True)
        subprocess.run(["git", "-C", str(tmp), "fetch", "-q", "--depth", "1", "origin", commit], check=True, timeout=300)
        subprocess.run(["git", "-C", str(tmp), "checkout", "-q", "FETCH_HEAD"], check=True)
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise BundleError(f"번들 저장소를 가져올 수 없습니다: {repo}@{commit[:12]} (git 종료 코드 {exc.returncode}). URL 과 커밋이 push 되었는지 확인하세요.") from exc
    tmp.rename(dest)
    return dest


def install_bundle_command(
    *, bundle_dir: str = REMOTE_BUNDLE_DIR, config_dir: str = REMOTE_CONFIG_DIR, repo_root: str = REPO_ROOT_IN_TASK
) -> str:
    """Shell that places the staged bundle into opencode's global config dir.

    Runs while the install-phase allowlist (npm registry etc.) is active:
    copies agents/plugins/tools/skills, puts AGENTS.md at the repo root, installs
    plugin dependencies with bun, and warms opencode's models.dev cache so the
    run phase needs only the proxy.
    """
    nvm = "[ -f ~/.nvm/nvm.sh ] && . ~/.nvm/nvm.sh"
    return (
        f'CFG="{config_dir}" && mkdir -p "$CFG" && '
        f'cp -r {bundle_dir}/. "$CFG"/ && rm -f "$CFG"/AGENTS.md && '
        f'if [ -f {bundle_dir}/AGENTS.md ]; then cp {bundle_dir}/AGENTS.md {repo_root}/AGENTS.md; fi && '
        f'if [ -f "$CFG"/package.json ]; then ( cd "$CFG" && {nvm}; '
        'command -v bun >/dev/null 2>&1 || npm i -g bun >/dev/null 2>&1; bun install --no-progress ); fi && '
        f'( {nvm}; opencode models >/dev/null 2>&1 || true ) && '
        'test -f "$CFG"/opencode.json && test -d "$CFG"/agents'
    )


class OpenCodeBundleAgent(OpenCode):
    """Runs a participant bundle (git url + commit) with the fixed proxy model."""

    def __init__(
        self,
        *args: Any,
        bundle_repo: str | None = None,
        bundle_commit: str | None = None,
        run_id: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        if not bundle_repo:
            raise BundleError("bundle_repo 가 필요합니다 (--ak bundle_repo=<git url | path>).")
        self.bundle_repo = bundle_repo
        self.bundle_commit = bundle_commit
        self.run_id = run_id
        self.main_agent: str | None = None
        self._staged: Path | None = None

    @staticmethod
    @override
    def name() -> str:
        return "opencode-bundle"

    # ------------------------------------------------------------------ install
    @override
    async def install(self, environment: BaseEnvironment) -> None:
        # 1. host side: acquire, validate, stage
        src = acquire_bundle(self.bundle_repo, self.bundle_commit)
        result = validate_bundle(src)
        if not result.ok:
            raise BundleError("번들 검증 실패:\n" + result.render())
        bundle, _ = load_bundle(src)
        assert bundle is not None
        self.main_agent = bundle.main_agent
        staged = Path(tempfile.mkdtemp(prefix="arena-staged-"))
        merged = stage_bundle(bundle, staged / "bundle", arena_config=self._opencode_config, model=self.model_name or "")
        merged.setdefault("experimental", {})
        # The parent run() writes ~/.config/opencode/opencode.json from this dict.
        self._opencode_config = merged
        self._staged = staged / "bundle"
        (self.logs_dir / "bundle-meta.json").write_text(
            json.dumps({"repo": self.bundle_repo, "commit": self.bundle_commit, "team": bundle.team, "main_agent": bundle.main_agent, "run_id": self.run_id}, indent=2)
        )

        # 2. container side: node + pinned opencode (parent), then bundle files
        await super().install(environment)
        await environment.upload_dir(self._staged, REMOTE_BUNDLE_DIR)
        await self.exec_as_agent(environment, command=install_bundle_command())
        shutil.rmtree(staged, ignore_errors=True)

    # ------------------------------------------------------------------ run
    @override
    def build_cli_flags(self) -> str:
        flags = super().build_cli_flags()
        if self.main_agent:
            flags = f"{flags} --agent {shlex.quote(self.main_agent)}".strip()
        return flags
