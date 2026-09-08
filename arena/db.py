"""SQLite store: teams, submissions, runs, trials (PRD §5.1 #6). stdlib sqlite3, no ORM."""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
OFFICIAL_CUTOFF_HOUR = 22  # 22:00 KST

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  token TEXT UNIQUE NOT NULL,
  proxy_key TEXT,
  dev_budget_usd REAL NOT NULL DEFAULT 30,
  is_reference INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY,
  team_id INTEGER NOT NULL REFERENCES teams(id),
  channel TEXT NOT NULL CHECK (channel IN ('dev','official')),
  repo_url TEXT NOT NULL,
  commit_sha TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed','invalid')),
  submitted_at TEXT NOT NULL,
  official_day TEXT,
  validation TEXT,
  UNIQUE (team_id, official_day)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER REFERENCES submissions(id),
  team_id INTEGER NOT NULL REFERENCES teams(id),
  dataset TEXT NOT NULL,
  job_name TEXT UNIQUE NOT NULL,
  proxy_key_alias TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  started_at TEXT,
  finished_at TEXT,
  n_tasks INTEGER,
  n_resolved INTEGER,
  cost_usd REAL,
  opencode_version TEXT,
  model TEXT,
  bundle_commit TEXT,
  dataset_hash TEXT,
  proxy_config_hash TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS trials (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES runs(id),
  task_id TEXT NOT NULL,
  trial_name TEXT NOT NULL,
  reward REAL,
  cost_usd REAL,
  duration_sec REAL,
  n_input_tokens INTEGER,
  n_output_tokens INTEGER,
  exception_type TEXT,
  trajectory_path TEXT,
  UNIQUE (run_id, trial_name)
);
CREATE TABLE IF NOT EXISTS presentation_scores (
  team_id INTEGER PRIMARY KEY REFERENCES teams(id),
  score REAL NOT NULL,
  notes TEXT
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def official_day_for(ts: datetime) -> str:
    """Submission day in KST; a submission after 22:00 counts toward the next day's batch."""
    local = ts.astimezone(KST)
    if local.hour >= OFFICIAL_CUTOFF_HOUR:
        local = local + timedelta(days=1)
    return local.strftime("%Y-%m-%d")


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        c.execute("PRAGMA journal_mode = WAL")
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # ---- teams ------------------------------------------------------------
    def create_team(self, name: str, *, dev_budget_usd: float = 30, is_reference: bool = False, proxy_key: str | None = None) -> dict[str, Any]:
        token = "tm_" + secrets.token_urlsafe(24)
        with self.conn() as c:
            c.execute(
                "INSERT INTO teams(name, token, proxy_key, dev_budget_usd, is_reference, created_at) VALUES (?,?,?,?,?,?)",
                (name, token, proxy_key, dev_budget_usd, int(is_reference), now_iso()),
            )
            return dict(c.execute("SELECT * FROM teams WHERE name=?", (name,)).fetchone())

    def team_by_token(self, token: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM teams WHERE token=?", (token,)).fetchone()
            return dict(row) if row else None

    def team_by_name(self, name: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM teams WHERE name=?", (name,)).fetchone()
            return dict(row) if row else None

    def teams(self) -> list[dict[str, Any]]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM teams ORDER BY name")]

    # ---- submissions ------------------------------------------------------
    def add_submission(self, team_id: int, *, channel: str, repo_url: str, commit_sha: str, validation: str, at: datetime | None = None) -> dict[str, Any]:
        at = at or datetime.now(UTC)
        day = official_day_for(at) if channel == "official" else None
        with self.conn() as c:
            try:
                c.execute(
                    "INSERT INTO submissions(team_id, channel, repo_url, commit_sha, submitted_at, official_day, validation) VALUES (?,?,?,?,?,?,?)",
                    (team_id, channel, repo_url, commit_sha, at.isoformat(timespec="seconds"), day, validation),
                )
            except sqlite3.IntegrityError as exc:
                raise DailyLimitError(day or "") from exc
            return dict(c.execute("SELECT * FROM submissions WHERE id=last_insert_rowid()").fetchone())

    def next_queued(self, channel: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM submissions WHERE channel=? AND status='queued' ORDER BY submitted_at LIMIT 1", (channel,)
            ).fetchone()
            return dict(row) if row else None

    def queued(self, channel: str, *, official_day: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM submissions WHERE channel=? AND status='queued'"
        args: list[Any] = [channel]
        if official_day:
            q += " AND official_day=?"
            args.append(official_day)
        with self.conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY submitted_at", args)]

    def set_submission_status(self, sub_id: int, status: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE submissions SET status=? WHERE id=?", (status, sub_id))

    def submissions_for_team(self, team_id: int) -> list[dict[str, Any]]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM submissions WHERE team_id=? ORDER BY submitted_at DESC", (team_id,))]

    # ---- runs / trials ----------------------------------------------------
    def create_run(self, **fields: Any) -> int:
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self.conn() as c:
            cur = c.execute(f"INSERT INTO runs({cols}) VALUES ({marks})", tuple(fields.values()))
            return int(cur.lastrowid)

    def update_run(self, run_id: int, **fields: Any) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.conn() as c:
            c.execute(f"UPDATE runs SET {sets} WHERE id=?", (*fields.values(), run_id))

    def upsert_trial(self, run_id: int, **fields: Any) -> None:
        fields["run_id"] = run_id
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{k}=excluded.{k}" for k in fields if k not in ("run_id", "trial_name"))
        with self.conn() as c:
            c.execute(f"INSERT INTO trials({cols}) VALUES ({marks}) ON CONFLICT(run_id, trial_name) DO UPDATE SET {updates}", tuple(fields.values()))

    def runs_for_team(self, team_id: int, dataset: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT * FROM runs WHERE team_id=?"
        args: list[Any] = [team_id]
        if dataset:
            q += " AND dataset=?"
            args.append(dataset)
        with self.conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY id DESC", args)]

    def run_by_job(self, job_name: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM runs WHERE job_name=?", (job_name,)).fetchone()
            return dict(row) if row else None

    def trials_for_run(self, run_id: int) -> list[dict[str, Any]]:
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM trials WHERE run_id=? ORDER BY task_id", (run_id,))]

    def latest_public_runs(self) -> list[dict[str, Any]]:
        """Most recent finished public run per team (leaderboard rows)."""
        with self.conn() as c:
            return [
                dict(r)
                for r in c.execute(
                    """
                    SELECT r.*, t.name AS team_name, t.is_reference,
                           (SELECT COUNT(*) FROM runs r2 JOIN submissions s2 ON s2.id=r2.submission_id
                              WHERE r2.team_id=r.team_id AND r2.dataset='public' AND s2.channel='official') AS n_submissions,
                           (SELECT r3.n_resolved FROM runs r3 WHERE r3.team_id=r.team_id AND r3.dataset='public'
                              AND r3.status='done' AND r3.id < r.id ORDER BY r3.id DESC LIMIT 1) AS prev_resolved
                    FROM runs r JOIN teams t ON t.id=r.team_id
                    WHERE r.dataset='public' AND r.status='done'
                      AND r.id = (SELECT MAX(id) FROM runs WHERE team_id=r.team_id AND dataset='public' AND status='done')
                    """
                )
            ]


class DailyLimitError(Exception):
    def __init__(self, day: str):
        super().__init__(day)
        self.day = day
