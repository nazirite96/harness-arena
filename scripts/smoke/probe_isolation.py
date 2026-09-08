"""Run one trial with NetworkProbeAgent and assert: proxy reachable, github.com blocked."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime

import yaml

from arena.config import REPO_ROOT, load_settings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="smoke")
    ap.add_argument("--task", default=None)
    args = ap.parse_args()
    s = load_settings()
    ds = REPO_ROOT / "datasets" / args.dataset
    ids = json.loads((ds / "task_ids.json").read_text())
    task = args.task or ids[0]
    job = f"probe-isolation-{datetime.now():%Y%m%d-%H%M%S}"
    cfg = {
        "job_name": job,
        "jobs_dir": str(s.jobs_dir),
        "n_concurrent_trials": 1,
        "agents": [{
            "import_path": "arena_harness.probe:NetworkProbeAgent",
            "kwargs": {"proxy_url": f"http://{s.proxy_host_for_containers}:{s.proxy_port}/health/liveliness"},
        }],
        "datasets": [{"path": str(ds), "task_names": [task]}],
        "verifier": {"disable": True},
    }
    path = s.jobs_dir / f"{job}.job.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    env = {"DOCKER_DEFAULT_PLATFORM": s.docker_platform}
    import os
    rc = subprocess.call(["uv", "run", "harbor", "run", "--config", str(path), "--yes", "-q"], cwd=REPO_ROOT, env={**os.environ, **env})
    trial_dirs = [p for p in (s.jobs_dir / job).iterdir() if (p / "agent").is_dir()]
    if not trial_dirs:
        print("FAIL: no trial directory", file=sys.stderr)
        return 1
    probe_path = trial_dirs[0] / "agent" / "probe.json"
    if not probe_path.exists():
        print(f"FAIL: probe.json missing (harbor rc={rc}); see {trial_dirs[0]}/trial.log", file=sys.stderr)
        return 1
    probe = json.loads(probe_path.read_text())
    print("probe:", probe)
    def reached(code: str) -> bool:
        return code[:1] in ("2", "3")

    ok_proxy = reached(str(probe.get("proxy", "")))
    # curl prints 000 (and our fallback appends BLOCKED) when the connection is refused
    ok_block = not reached(str(probe.get("blocked", "")))
    if not ok_proxy:
        print("FAIL: proxy not reachable from the agent phase", file=sys.stderr)
    if not ok_block:
        print("FAIL: github.com reachable from the agent phase (egress control inactive?)", file=sys.stderr)
    return 0 if (ok_proxy and ok_block) else 1


if __name__ == "__main__":
    raise SystemExit(main())
