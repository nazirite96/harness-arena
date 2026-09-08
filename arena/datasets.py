"""Build Harbor local datasets from the pinned harbor-datasets checkout.

A local dataset is a directory of task directories; `harbor run -p <dir>` runs
every task in it. We copy registry tasks and patch task.toml so that the
environment starts in allowlist mode (proxy + package registries) and the agent
phase can reach ONLY the proxy.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import toml

from arena.config import INSTALL_ALLOWED_HOSTS, REPO_ROOT, RUN_ALLOWED_HOSTS, Settings

CACHE_DIR = Path.home() / ".cache" / "harness-arena" / "harbor-datasets"


def ensure_source_checkout(s: Settings) -> Path:
    """Sparse, blob-less clone of harbor-datasets pinned to the locked commit."""
    repo = s.versions["HARBOR_DATASETS_REPO"]
    commit = s.versions["HARBOR_DATASETS_COMMIT"]
    if not (CACHE_DIR / ".git").exists():
        CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--sparse", "--no-checkout", repo, str(CACHE_DIR)],
            check=True,
        )
    subprocess.run(["git", "-C", str(CACHE_DIR), "fetch", "-q", "origin", commit], check=True)
    subprocess.run(["git", "-C", str(CACHE_DIR), "checkout", "-q", commit], check=True)
    return CACHE_DIR


def fetch_task(s: Settings, instance_id: str) -> Path:
    src_root = ensure_source_checkout(s)
    rel = f"datasets/{s.versions['SWEBENCH_DATASET_NAME']}/{instance_id}"
    subprocess.run(["git", "-C", str(src_root), "sparse-checkout", "add", rel], check=True)
    path = src_root / rel
    if not (path / "task.toml").exists():
        raise SystemExit(f"[dataset] 태스크를 찾을 수 없습니다: {instance_id}")
    return path


def patch_task_toml(task_dir: Path, s: Settings) -> None:
    """Enforce network isolation and the arena time limit on a copied task."""
    cfg = tomllib.loads((task_dir / "task.toml").read_text())
    env = cfg.setdefault("environment", {})
    env["network_mode"] = "allowlist"
    env["allowed_hosts"] = sorted({s.proxy_host_for_containers, *INSTALL_ALLOWED_HOSTS})
    agent = cfg.setdefault("agent", {})
    agent["network_mode"] = "allowlist"
    agent["allowed_hosts"] = sorted({s.proxy_host_for_containers, *RUN_ALLOWED_HOSTS})
    agent["timeout_sec"] = float(s.task_timeout_sec)
    # The verifier phase inherits the environment baseline (registries reachable)
    # so `pip install -e .` in SWE-bench test scripts keeps working.
    cfg.setdefault("verifier", {})["network_mode"] = "allowlist"
    cfg["verifier"]["allowed_hosts"] = env["allowed_hosts"]
    (task_dir / "task.toml").write_text(toml.dumps(cfg))


def build_local_dataset(s: Settings, name: str, instance_ids: list[str], *, overwrite: bool = False) -> Path:
    dest_root = REPO_ROOT / "datasets" / name
    dest_root.mkdir(parents=True, exist_ok=True)
    for iid in instance_ids:
        dest = dest_root / iid
        if dest.exists():
            if not overwrite:
                continue
            shutil.rmtree(dest)
        shutil.copytree(fetch_task(s, iid), dest)
        patch_task_toml(dest, s)
    (dest_root / "task_ids.json").write_text(
        __import__("json").dumps(sorted(p.name for p in dest_root.iterdir() if (p / "task.toml").exists()), indent=2) + "\n"
    )
    return dest_root
