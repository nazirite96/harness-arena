from datetime import UTC, datetime, timedelta

import pytest

from arena.db import KST, DailyLimitError, Store, official_day_for


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "arena.sqlite3")


def test_official_day_cutoff_22_kst():
    assert official_day_for(datetime(2026, 9, 10, 21, 59, tzinfo=KST)) == "2026-09-10"
    assert official_day_for(datetime(2026, 9, 10, 22, 0, tzinfo=KST)) == "2026-09-11"
    # UTC input is converted
    assert official_day_for(datetime(2026, 9, 10, 13, 30, tzinfo=UTC)) == "2026-09-11"


def test_one_official_submission_per_day(store):
    t = store.create_team("team-a")
    at = datetime(2026, 9, 10, 20, 0, tzinfo=KST)
    store.add_submission(t["id"], channel="official", repo_url="u", commit_sha="a" * 40, validation="ok", at=at)
    with pytest.raises(DailyLimitError) as exc:
        store.add_submission(t["id"], channel="official", repo_url="u", commit_sha="b" * 40, validation="ok", at=at + timedelta(minutes=5))
    assert exc.value.day == "2026-09-10"
    store.add_submission(t["id"], channel="official", repo_url="u", commit_sha="c" * 40, validation="ok", at=at + timedelta(hours=3))
    for i in range(3):
        store.add_submission(t["id"], channel="dev", repo_url="u", commit_sha=str(i) * 40, validation="ok", at=at)
    assert len(store.queued("dev")) == 3
    assert len(store.queued("official", official_day="2026-09-10")) == 1


def test_runs_and_leaderboard_rows(store):
    t = store.create_team("team-a")
    ref = store.create_team("baseline/opencode-vanilla", is_reference=True)
    r1 = store.create_run(team_id=t["id"], dataset="public", job_name="j1", status="done", n_tasks=50, n_resolved=10, cost_usd=5.0)
    r2 = store.create_run(team_id=t["id"], dataset="public", job_name="j2", status="done", n_tasks=50, n_resolved=15, cost_usd=6.0)
    store.create_run(team_id=ref["id"], dataset="public", job_name="j3", status="done", n_tasks=50, n_resolved=12, cost_usd=4.0)
    store.upsert_trial(r2, task_id="x", trial_name="x__1", reward=1.0, cost_usd=0.1)
    store.upsert_trial(r2, task_id="x", trial_name="x__1", reward=0.0, cost_usd=0.2)  # idempotent update
    rows = {r["team_name"]: r for r in store.latest_public_runs()}
    assert rows["team-a"]["n_resolved"] == 15 and rows["team-a"]["prev_resolved"] == 10
    assert rows["baseline/opencode-vanilla"]["is_reference"] == 1
    assert store.trials_for_run(r2)[0]["cost_usd"] == 0.2
    assert store.run_by_job("j1")["id"] == r1
