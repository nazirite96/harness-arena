"""Compose Harbor job configs and launch `harbor run`."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import yaml

from arena.config import REPO_ROOT, Settings

HARBOR_BIN = ["uv", "run", "harbor"]


def opencode_provider_config(s: Settings) -> dict[str, Any]:
    """The opencode.json fragment that pins every agent to the proxy model.

    The API key is read from the container env var ARENA_API_KEY, which we pass
    per run via Harbor's agent env (`--ae` / agents[].env).
    """
    alias = s.model_alias
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": s.opencode_model_string,
        "small_model": s.opencode_model_string,
        "enabled_providers": ["arena"],
        "provider": {
            "arena": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Harness Arena Proxy",
                "options": {
                    "baseURL": s.proxy_url_for_containers,
                    "apiKey": "{env:ARENA_API_KEY}",
                },
                "models": {
                    alias: {
                        "name": alias,
                        "tool_call": True,
                        "limit": {
                            "context": int(s.get("ARENA_MODEL_CONTEXT", "200000") or 200000),
                            "output": int(s.get("ARENA_MODEL_OUTPUT", "32000") or 32000),
                        },
                    }
                },
            }
        },
        "permission": "allow",
        "share": "disabled",
        "autoupdate": False,
    }


def vanilla_job_config(
    s: Settings,
    *,
    dataset_path: Path,
    job_name: str,
    api_key: str,
    n_concurrent: int = 1,
    task_names: list[str] | None = None,
) -> dict[str, Any]:
    """Job config for the reference `baseline/opencode-vanilla` row (Harbor's builtin agent)."""
    agent: dict[str, Any] = {
        "name": "opencode",
        "model_name": s.opencode_model_string,
        "kwargs": {
            "version": s.opencode_version,
            "opencode_config": opencode_provider_config(s),
        },
        "env": {"ARENA_API_KEY": api_key},
    }
    dataset: dict[str, Any] = {"path": str(dataset_path)}
    if task_names:
        dataset["task_names"] = task_names
    return {
        "job_name": job_name,
        "jobs_dir": str(s.jobs_dir),
        "n_concurrent_trials": n_concurrent,
        "quiet": False,
        "retry": {"max_retries": 1},
        "agents": [agent],
        "datasets": [dataset],
    }


def bundle_job_config(
    s: Settings,
    *,
    dataset_path: Path,
    job_name: str,
    api_key: str,
    bundle_repo: str,
    bundle_commit: str | None,
    run_id: str,
    n_concurrent: int = 1,
    task_names: list[str] | None = None,
) -> dict[str, Any]:
    """Job config for a participant bundle via arena_harness:OpenCodeBundleAgent."""
    cfg = vanilla_job_config(
        s, dataset_path=dataset_path, job_name=job_name, api_key=api_key, n_concurrent=n_concurrent, task_names=task_names
    )
    agent = cfg["agents"][0]
    agent.pop("name")
    agent["import_path"] = "arena_harness:OpenCodeBundleAgent"
    agent["kwargs"].update({"bundle_repo": bundle_repo, "bundle_commit": bundle_commit, "run_id": run_id})
    return cfg


def write_job_config(cfg: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path


def run_job(config_path: Path, *, settings: Settings | None = None, extra_args: list[str] | None = None) -> int:
    cmd = [*HARBOR_BIN, "run", "--config", str(config_path), "--yes", *(extra_args or [])]
    env = {**os.environ}
    # SWE-bench Verified images are published for linux/amd64 only. Harbor builds the
    # task image with `docker compose build`, which defaults to the daemon's platform,
    # so on arm64 hosts (Apple Silicon) the platform must be pinned explicitly.
    platform = (settings.docker_platform if settings else None) or "linux/amd64"
    env.setdefault("DOCKER_DEFAULT_PLATFORM", platform)
    print("$", f"DOCKER_DEFAULT_PLATFORM={env['DOCKER_DEFAULT_PLATFORM']}", " ".join(cmd))
    return subprocess.call(cmd, cwd=REPO_ROOT, env=env)


def load_job_result(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / "result.json").read_text())


def iter_trial_dirs(job_dir: Path):
    for p in sorted(job_dir.iterdir()):
        if (p / "result.json").exists():
            yield p
