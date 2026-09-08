"""Seed a DEMO database (never the real one) so the leaderboard/team pages can be previewed.

    ARENA_DB_PATH=data/demo.sqlite3 uv run python scripts/dev/seed_demo.py
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from pathlib import Path

from arena.config import REPO_ROOT
from arena.db import Store

db = Path(os.environ.get("ARENA_DB_PATH", "data/demo.sqlite3"))
if db.name == "arena.sqlite3":
    raise SystemExit("refusing to seed the real database; set ARENA_DB_PATH=data/demo.sqlite3")
if db.exists():
    db.unlink()
store = Store(REPO_ROOT / db)
rng = random.Random(7)
N = 50


def run(team, day, resolved, cost, commit):
    rid = store.create_run(team_id=team["id"], dataset="public", job_name=f"{team['name']}-{day}", status="done",
                           n_tasks=N, n_resolved=resolved, cost_usd=cost, bundle_commit=commit,
                           started_at=f"2026-10-{day:02d}T14:00:00", finished_at=f"2026-10-{day:02d}T17:{rng.randint(10,59)}:00")
    for i in range(N):
        store.upsert_trial(rid, task_id=f"demo__task-{i:03d}", trial_name=f"demo__task-{i:03d}__x{rng.randint(100,999)}",
                           reward=1.0 if i < resolved else 0.0, cost_usd=round(cost / N * rng.uniform(0.5, 1.5), 3),
                           duration_sec=rng.uniform(120, 1500))
    return rid


for name, score in (("baseline/opencode-vanilla", 19), ("reference/oh-my-opencode", 27)):
    t = store.create_team(name, is_reference=True)
    run(t, 1, score, N * 0.31, "vanilla" if "vanilla" in name else "omo")

teams = [("team-repro-first", [14, 18, 23, 24]), ("team-ralph", [12, 16, 17, 22]), ("team-testgate", [10, 15, 20, 20]),
         ("team-minimal-diff", [11, 13, 14, 19]), ("team-explorer", [9, 9, 13, 16]), ("team-yolo", [8, 7, 11, 12])]
for name, curve in teams:
    t = store.create_team(name)
    for day, res in enumerate(curve, start=1):
        sub = store.add_submission(t["id"], channel="official", repo_url=f"https://github.com/demo/{name}.git",
                                   commit_sha=f"{rng.randrange(16**40):040x}", validation="[통과]",
                                   at=datetime(2026, 10, day, 11, 0, tzinfo=timezone.utc))
        store.set_submission_status(sub["id"], "done")
        rid = run(t, day, res, N * rng.uniform(0.18, 0.42), sub["commit_sha"])
        store.update_run(rid, submission_id=sub["id"])
print("seeded", db, "teams:", [t["name"] for t in store.teams()])
print("demo team token:", store.team_by_name("team-repro-first")["token"])
