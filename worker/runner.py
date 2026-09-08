"""Execute one submission as a Harbor job and persist results (PRD §5.2, §14 reproducibility)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arena import harbor_runner
from arena.config import REPO_ROOT, Settings
from arena.db import Store, now_iso
from arena.proxy import ProxyClient


def dataset_hash(ds: Path) -> str:
    ids_path = ds / "task_ids.json"
    return hashlib.sha256(ids_path.read_bytes()).hexdigest()[:16] if ids_path.exists() else "unknown"


def proxy_config_hash() -> str:
    p = REPO_ROOT / "proxy" / "litellm.config.yaml"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "unknown"


def run_submission(store: Store, s: Settings, sub: dict[str, Any], *, dataset: str, n_concurrent: int | None = None, job_name: str | None = None) -> int:
    """Run a submission on `dataset`; returns the run id. Blocks until harbor finishes."""
    team = next(t for t in store.teams() if t["id"] == sub["team_id"])
    ds = REPO_ROOT / "datasets" / dataset
    ids = json.loads((ds / "task_ids.json").read_text())
    job_name = job_name or f"{team['name']}-{dataset}-{datetime.now(UTC):%Y%m%d-%H%M%S}"
    budget = max(0.5, len(ids) * s.cost_cap_per_task)
    client = ProxyClient(s)
    key = client.create_key(alias=job_name, max_budget=budget, team=team["name"], run_id=job_name, duration="3d")["key"]
    run_id = store.create_run(
        submission_id=sub["id"], team_id=team["id"], dataset=dataset, job_name=job_name, proxy_key_alias=job_name,
        status="running", started_at=now_iso(), n_tasks=len(ids), opencode_version=s.opencode_version,
        model=s.upstream_model, bundle_commit=sub["commit_sha"], dataset_hash=dataset_hash(ds), proxy_config_hash=proxy_config_hash(),
    )
    store.set_submission_status(sub["id"], "running")
    cfg = harbor_runner.bundle_job_config(
        s, dataset_path=ds, job_name=job_name, api_key=key, bundle_repo=sub["repo_url"], bundle_commit=sub["commit_sha"],
        run_id=job_name, n_concurrent=n_concurrent or s.n_concurrent,
    )
    cfg_path = harbor_runner.write_job_config(cfg, s.jobs_dir / f"{job_name}.job.yaml")
    try:
        rc = harbor_runner.run_job(cfg_path, settings=s)
        n_resolved = ingest_job(store, run_id, s.jobs_dir / job_name)
        spend = client.key_spend(key)
        store.update_run(run_id, status="done" if rc == 0 else "failed", finished_at=now_iso(), n_resolved=n_resolved, cost_usd=spend, error=None if rc == 0 else f"harbor exit {rc}")
        store.set_submission_status(sub["id"], "done" if rc == 0 else "failed")
    except Exception as exc:  # keep the queue moving; the error is recorded for operators
        store.update_run(run_id, status="failed", finished_at=now_iso(), error=str(exc)[:2000])
        store.set_submission_status(sub["id"], "failed")
        raise
    finally:
        try:
            client.delete_key(key)
        except Exception:
            pass
    return run_id


def ingest_job(store: Store, run_id: int, job_dir: Path) -> int:
    """Parse trial result.json files into the trials table. Returns number resolved."""
    n_resolved = 0
    for td in harbor_runner.iter_trial_dirs(job_dir):
        r = json.loads((td / "result.json").read_text())
        reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        ar = r.get("agent_result") or {}
        timing = r.get("agent_execution") or {}
        dur = None
        if timing.get("started_at") and timing.get("finished_at"):
            dur = (datetime.fromisoformat(timing["finished_at"]) - datetime.fromisoformat(timing["started_at"])).total_seconds()
        traj = td / "agent" / "trajectory.json"
        store.upsert_trial(
            run_id,
            task_id=r["task_name"],
            trial_name=td.name,
            reward=reward,
            cost_usd=ar.get("cost_usd"),
            duration_sec=dur,
            n_input_tokens=ar.get("n_input_tokens"),
            n_output_tokens=ar.get("n_output_tokens"),
            exception_type=(r.get("exception_info") or {}).get("exception_type"),
            trajectory_path=str(traj.relative_to(REPO_ROOT)) if traj.exists() else None,
        )
        if reward is not None and reward >= 1:
            n_resolved += 1
    return n_resolved
