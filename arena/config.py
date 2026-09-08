"""Central settings: .env + versions.lock, resolved once per process."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parent.parent

# Hosts the task container may reach while the agent is being INSTALLED.
# (opencode via npm, nvm's node tarball, apt mirrors, models.dev metadata cache).
INSTALL_ALLOWED_HOSTS: tuple[str, ...] = (
    "registry.npmjs.org",
    "nodejs.org",
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
    "models.dev",
    "deb.debian.org",
    "security.debian.org",
    "archive.ubuntu.com",
    "security.ubuntu.com",
    "ports.ubuntu.com",
    "pypi.org",
    "files.pythonhosted.org",
    "astral.sh",
)

# Hosts the task container may reach while the agent is RUNNING: only the proxy.
RUN_ALLOWED_HOSTS: tuple[str, ...] = ()


def load_versions(path: Path | None = None) -> dict[str, str]:
    path = path or REPO_ROOT / "versions.lock"
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


@dataclass
class Settings:
    env: dict[str, str] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)

    # ---- helpers -------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        # Shell environment overrides .env (dotenv convention) so operators can
        # point one-off commands at another DB or proxy without editing files.
        return os.environ.get(key) or self.env.get(key) or default

    def require(self, key: str) -> str:
        v = self.get(key)
        if not v:
            raise SystemExit(f"[config] {key} 가 .env 에 설정되어 있지 않습니다.")
        return v

    @property
    def model_alias(self) -> str:
        return self.get("ARENA_MODEL_ALIAS", "arena-model") or "arena-model"

    @property
    def upstream_model(self) -> str:
        return self.require("ARENA_UPSTREAM_MODEL")

    @property
    def upstream_key_env(self) -> str:
        """Which provider env var the upstream model needs, inferred from the litellm prefix."""
        prefix = self.upstream_model.split("/", 1)[0].lower()
        table = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "google": "GEMINI_API_KEY",
        }
        env = self.get("ARENA_UPSTREAM_KEY_ENV")
        if env:
            return env
        if prefix not in table:
            raise SystemExit(
                f"[config] ARENA_UPSTREAM_MODEL 접두어 '{prefix}' 의 키 env 를 알 수 없습니다. "
                "ARENA_UPSTREAM_KEY_ENV 를 .env 에 직접 지정하세요."
            )
        return table[prefix]

    @property
    def proxy_port(self) -> int:
        return int(self.get("LITELLM_PORT", "4000") or 4000)

    @property
    def proxy_host_for_containers(self) -> str:
        return self.get("ARENA_PROXY_HOST", "host.docker.internal") or "host.docker.internal"

    @property
    def proxy_url_for_containers(self) -> str:
        return f"http://{self.proxy_host_for_containers}:{self.proxy_port}/v1"

    @property
    def proxy_url_local(self) -> str:
        return f"http://127.0.0.1:{self.proxy_port}"

    @property
    def master_key(self) -> str:
        return self.require("LITELLM_MASTER_KEY")

    @property
    def opencode_version(self) -> str:
        return self.versions["OPENCODE_VERSION"]

    @property
    def jobs_dir(self) -> Path:
        return REPO_ROOT / (self.get("ARENA_JOBS_DIR", "jobs") or "jobs")

    @property
    def db_path(self) -> Path:
        return REPO_ROOT / (self.get("ARENA_DB_PATH", "data/arena.sqlite3") or "data/arena.sqlite3")

    @property
    def task_timeout_sec(self) -> int:
        return int(self.get("ARENA_TASK_TIMEOUT_SEC", "1800") or 1800)

    @property
    def cost_cap_per_task(self) -> float:
        return float(self.get("ARENA_COST_CAP_PER_TASK_USD", "0.50") or 0.5)

    @property
    def n_concurrent(self) -> int:
        return int(self.get("ARENA_N_CONCURRENT", "16") or 16)

    @property
    def docker_platform(self) -> str:
        """Platform for task images. SWE-bench Verified ships linux/amd64 only."""
        return self.get("ARENA_DOCKER_PLATFORM", "linux/amd64") or "linux/amd64"

    @property
    def opencode_model_string(self) -> str:
        """The provider/model string opencode is forced to use."""
        return f"arena/{self.model_alias}"


def load_settings(env_file: Path | None = None) -> Settings:
    env_file = env_file or REPO_ROOT / ".env"
    env = {k: v for k, v in dotenv_values(env_file).items() if v is not None} if env_file.exists() else {}
    return Settings(env=env, versions=load_versions())
