"""FastAPI leaderboard · team pages · trajectory viewer · operator view (PRD §7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from arena.config import REPO_ROOT, load_settings
from arena.db import Store
from arena.intake import submit as do_submit

app = FastAPI(title="Harness Arena")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
settings = load_settings()
store = Store(settings.db_path)

PUBLIC_DATASETS = {"public", "dev"}  # PRD §7.4: private never rendered

SCHEDULE = [  # PRD §11 (10-day sprint)
    ("D1", "킥오프 · opencode 확장점 강의 · OMO 훅 코드 리딩 · 스타터 킷으로 첫 dev 실행 · 리더보드 오픈"),
    ("D2~D4", "반복 개선 · 매일 공식 제출 (22:00 KST 마감)"),
    ("D5", "중간 세션 · 운영진이 전 팀 실패 유형 공유"),
    ("D6~D8", "반복 개선 · 매일 공식 제출"),
    ("D9", "18:00 코드 프리즈 → 야간 Private 채점 2회"),
    ("D10", "결과 공개 · 발표 · 최종 순위"),
]


def _event_ctx() -> dict[str, Any]:
    from datetime import date, timedelta

    d1 = settings.get("ARENA_D1_DATE") or ""
    dates: dict[str, str] = {}
    if d1:
        try:
            start = date.fromisoformat(d1)
            for i in range(1, 11):
                dates[f"D{i}"] = (start + timedelta(days=i - 1)).strftime("%m/%d")
        except ValueError:
            dates = {}
    return {
        "event_name": settings.get("ARENA_EVENT_NAME", "Harness Arena"),
        "d_dates": dates,
        "schedule": SCHEDULE,
        "proxy_url": settings.get("ARENA_PROXY_PUBLIC_URL", "http://<proxy-host>:4000/v1"),
        "starter_kit_url": settings.get("ARENA_STARTER_KIT_URL", ""),
        "public_url": settings.get("ARENA_PUBLIC_URL", ""),
        "contact": settings.get("ARENA_CONTACT", "운영진"),
        "opencode_version": settings.opencode_version,
        "model_alias": settings.model_alias,
        "dev_budget": settings.get("ARENA_TEAM_DEV_BUDGET_USD", "30"),
        "cost_cap": settings.get("ARENA_COST_CAP_PER_TASK_USD", "0.50"),
        "timeout_min": int(settings.task_timeout_sec // 60),
    }


def _team_from_token(token: str | None) -> dict[str, Any]:
    team = store.team_by_token(token) if token else None
    if not team:
        raise HTTPException(403, "팀 토큰이 올바르지 않습니다.")
    return team


def _is_admin(request: Request) -> bool:
    return bool(settings.get("ARENA_ADMIN_TOKEN")) and request.query_params.get("admin") == settings.get("ARENA_ADMIN_TOKEN")


def leaderboard_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = store.latest_public_runs()
    for r in rows:
        n = r["n_tasks"] or 0
        r["rate"] = (100.0 * (r["n_resolved"] or 0) / n) if n else 0.0
        r["delta"] = (r["n_resolved"] or 0) - r["prev_resolved"] if r["prev_resolved"] is not None else None
        r["avg_cost"] = (r["cost_usd"] or 0) / n if n else 0.0
        trials = store.trials_for_run(r["id"])
        durs = [t["duration_sec"] for t in trials if t["duration_sec"]]
        r["avg_time_min"] = (sum(durs) / len(durs) / 60) if durs else None
    refs = [r for r in rows if r["is_reference"]]
    ranked = sorted((r for r in rows if not r["is_reference"]), key=lambda r: (-r["rate"], r["avg_cost"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return refs, ranked


@app.get("/", response_class=HTMLResponse)
def index(request: Request, kiosk: int = 0):
    from datetime import datetime, timedelta, timezone

    refs, ranked = leaderboard_rows()
    now_kst = datetime.now(timezone(timedelta(hours=9))).strftime("%m/%d %H:%M")
    n_public = ranked[0]["n_tasks"] if ranked else (refs[0]["n_tasks"] if refs else 50)
    return templates.TemplateResponse(
        request, "leaderboard.html",
        {"refs": refs, "ranked": ranked, "n_public": n_public, "kiosk": kiosk, "now_kst": now_kst, **_event_ctx()},
    )


@app.get("/guide", response_class=HTMLResponse)
def guide(request: Request):
    """참가 방법 안내 (starter-kit/README.md 와 docs/rules.md 의 웹 버전)."""
    return templates.TemplateResponse(request, "guide.html", _event_ctx())


@app.get("/team", response_class=HTMLResponse)
def team_login(request: Request):
    return templates.TemplateResponse(request, "team_login.html", {})


@app.get("/team/{token}", response_class=HTMLResponse)
def team_page(request: Request, token: str, message: str | None = None):
    team = _team_from_token(token)
    runs = [r for r in store.runs_for_team(team["id"]) if r["dataset"] in PUBLIC_DATASETS]
    for r in runs:
        r["trials"] = store.trials_for_run(r["id"])
    subs = store.submissions_for_team(team["id"])
    spend = None
    try:
        from arena.proxy import ProxyClient

        if team.get("proxy_key"):
            spend = ProxyClient(settings).key_spend(team["proxy_key"])
    except Exception:
        spend = None
    return templates.TemplateResponse(
        request, "team.html", {"team": team, "runs": runs, "subs": subs, "spend": spend, "token": token, "message": message}
    )


@app.post("/team/{token}/submit")
def team_submit(token: str, repo_url: str = Form(...), commit_sha: str = Form(...), channel: str = Form("dev")):
    _team_from_token(token)
    r = do_submit(store, settings, token=token, repo_url=repo_url, commit_sha=commit_sha, channel=channel)
    return RedirectResponse(url=f"/team/{token}?message={r.message}", status_code=303)


@app.get("/trajectory/{token}/{run_id}/{trial_name}", response_class=HTMLResponse)
def trajectory(request: Request, token: str, run_id: int, trial_name: str):
    """Teams see only their own trajectories; the admin token sees all (PRD §7.3)."""
    run = next((r for r in store.runs_for_team(_owner_for_run(run_id)) if r["id"] == run_id), None)
    if not run or run["dataset"] not in PUBLIC_DATASETS:
        raise HTTPException(404)
    admin = _is_admin(request)
    if not admin:
        team = _team_from_token(token)
        if team["id"] != run["team_id"]:
            raise HTTPException(403, "자기 팀의 궤적만 볼 수 있습니다.")
    trial = next((t for t in store.trials_for_run(run_id) if t["trial_name"] == trial_name), None)
    if not trial or not trial["trajectory_path"]:
        raise HTTPException(404, "궤적이 없습니다.")
    traj = json.loads((REPO_ROOT / trial["trajectory_path"]).read_text())
    return templates.TemplateResponse(request, "trajectory.html", {"traj": traj, "trial": trial, "run": run, "token": token})


def _owner_for_run(run_id: int) -> int:
    with store.conn() as c:
        row = c.execute("SELECT team_id FROM runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404)
    return int(row["team_id"])


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not _is_admin(request):
        raise HTTPException(403)
    teams = store.teams()
    runs_by_team = {t["id"]: store.runs_for_team(t["id"]) for t in teams}
    queued = {"dev": store.queued("dev"), "official": store.queued("official")}
    return templates.TemplateResponse(request, "admin.html", {"teams": teams, "runs_by_team": runs_by_team, "queued": queued, "admin": request.query_params.get("admin")})


@app.get("/api/leaderboard")
def api_leaderboard():
    refs, ranked = leaderboard_rows()
    keys = ("rank", "team_name", "rate", "delta", "n_resolved", "n_tasks", "avg_cost", "avg_time_min", "n_submissions", "bundle_commit", "finished_at")
    return {"reference": [{k: r.get(k) for k in keys} for r in refs], "ranked": [{k: r.get(k) for k in keys} for r in ranked]}
