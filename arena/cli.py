"""`arena` operator CLI. Participant-facing messages are Korean; identifiers English."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.table import Table

from arena import harbor_runner
from arena.config import REPO_ROOT, load_settings
from arena.datasets import build_local_dataset
from arena.proxy import ProxyClient, compose, render_config

app = typer.Typer(no_args_is_help=True, help="Harness Arena operator CLI")
proxy_app = typer.Typer(no_args_is_help=True, help="LiteLLM 프록시 관리")
keys_app = typer.Typer(no_args_is_help=True, help="가상 키 발급/폐기/조회 (M1)")
dataset_app = typer.Typer(no_args_is_help=True, help="Harbor 로컬 데이터셋 구성")
run_app = typer.Typer(no_args_is_help=True, help="Harbor 실행")
app.add_typer(proxy_app, name="proxy")
app.add_typer(keys_app, name="keys")
app.add_typer(dataset_app, name="dataset")
app.add_typer(run_app, name="run")


# --------------------------------------------------------------------------- env
@app.command("env")
def env_check() -> None:
    """로컬 툴체인·설정 상태를 점검한다 (M0)."""
    s = load_settings()
    t = Table(title="arena env check")
    t.add_column("item")
    t.add_column("status")
    for tool in ("uv", "docker", "git", "bun", "node", "npm"):
        t.add_row(tool, "ok" if shutil.which(tool) else "[red]missing[/red]")
    buildx = subprocess.run(["docker", "buildx", "version"], capture_output=True).returncode == 0
    t.add_row("docker buildx", "ok" if buildx else "[red]missing (brew install docker-buildx)[/red]")
    t.add_row(".env", "ok" if (REPO_ROOT / ".env").exists() else "[yellow]missing (cp .env.example .env)[/yellow]")
    for k in ("HARBOR_VERSION", "OPENCODE_VERSION", "LITELLM_IMAGE"):
        t.add_row(k, s.versions.get(k, "[red]?[/red]"))
    try:
        hv = subprocess.run(["uv", "run", "harbor", "--version"], capture_output=True, text=True, cwd=REPO_ROOT).stdout.strip()
    except Exception:
        hv = "[red]not installed (uv sync)[/red]"
    t.add_row("harbor (uv run)", hv or "?")
    docker_ok = subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    t.add_row("docker daemon", "ok" if docker_ok else "[red]not running[/red]")
    if (REPO_ROOT / ".env").exists():
        t.add_row("proxy liveliness", "ok" if ProxyClient(s).liveliness() else "[yellow]down[/yellow]")
    rprint(t)


# --------------------------------------------------------------------------- proxy
@proxy_app.command("render")
def proxy_render() -> None:
    """.env 값으로 proxy/litellm.config.yaml 을 생성한다."""
    s = load_settings()
    p = render_config(s)
    rprint(f"rendered {p.relative_to(REPO_ROOT)} (alias={s.model_alias}, upstream={s.upstream_model})")


@proxy_app.command("up")
def proxy_up() -> None:
    """프록시(LiteLLM + Postgres)를 올리고 헬스체크를 기다린다."""
    s = load_settings()
    render_config(s)
    if compose("up", "-d") != 0:
        raise typer.Exit(1)
    c = ProxyClient(s)
    for _ in range(60):
        if c.liveliness():
            rprint(f"[green]proxy up[/green] {s.proxy_url_local}  models={c.models()}")
            return
        time.sleep(2)
    rprint("[red]프록시가 120초 안에 뜨지 않았습니다. `docker compose logs litellm` 확인.[/red]")
    raise typer.Exit(1)


@proxy_app.command("down")
def proxy_down() -> None:
    raise typer.Exit(compose("down"))


@proxy_app.command("logs")
def proxy_logs(tail: int = 100) -> None:
    raise typer.Exit(compose("logs", "--tail", str(tail), "litellm"))


@proxy_app.command("health")
def proxy_health() -> None:
    s = load_settings()
    c = ProxyClient(s)
    rprint({"liveliness": c.liveliness(), "models": c.models() if c.liveliness() else None})


# --------------------------------------------------------------------------- keys
@keys_app.command("create")
def keys_create(
    alias: str = typer.Option(..., help="키 별칭 (예: team-alpha, run-20260907-abc)"),
    max_budget: float = typer.Option(..., help="USD 예산 상한"),
    team: str | None = typer.Option(None),
    run_id: str | None = typer.Option(None),
    duration: str | None = typer.Option(None, help="만료 (예: 30d, 12h)"),
) -> None:
    s = load_settings()
    info = ProxyClient(s).create_key(alias=alias, max_budget=max_budget, team=team, run_id=run_id, duration=duration)
    rprint(json.dumps({"key": info.get("key"), "key_alias": alias, "max_budget": max_budget, "expires": info.get("expires")}, indent=2))


@keys_app.command("delete")
def keys_delete(key: str) -> None:
    ProxyClient(load_settings()).delete_key(key)
    rprint("deleted")


@keys_app.command("info")
def keys_info(key: str) -> None:
    rprint(json.dumps(ProxyClient(load_settings()).key_info(key), indent=2, default=str))


@keys_app.command("spend")
def keys_spend(key: str) -> None:
    rprint({"spend_usd": ProxyClient(load_settings()).key_spend(key)})


@keys_app.command("logs")
def keys_logs(key: str | None = None, limit: int = 20) -> None:
    logs = ProxyClient(load_settings()).spend_logs(api_key=key, limit=limit)
    for row in logs:
        rprint({k: row.get(k) for k in ("startTime", "model", "spend", "total_tokens", "request_tags", "metadata") if k in row})


# --------------------------------------------------------------------------- dataset
@dataset_app.command("build")
def dataset_build(
    name: str = typer.Argument(..., help="datasets/<name>"),
    instance_ids: list[str] = typer.Argument(..., help="SWE-bench instance ids"),
    overwrite: bool = False,
) -> None:
    """레지스트리 태스크를 복사하고 격리 정책을 적용해 로컬 데이터셋을 만든다."""
    s = load_settings()
    root = build_local_dataset(s, name, instance_ids, overwrite=overwrite)
    rprint(f"built {root.relative_to(REPO_ROOT)} with {len(instance_ids)} task(s)")


# --------------------------------------------------------------------------- run
@run_app.command("vanilla")
def run_vanilla(
    dataset: str = typer.Option("smoke", help="datasets/<name>"),
    job_name: str | None = typer.Option(None),
    n_concurrent: int = typer.Option(1),
    budget: float = typer.Option(2.0, help="run 임시 키 예산 USD"),
    task: list[str] | None = typer.Option(None, help="특정 태스크만"),
    keep_key: bool = typer.Option(False, help="실행 후 임시 키를 폐기하지 않음"),
) -> None:
    """Harbor 내장 opencode 에이전트를 프록시 경유로 실행한다 (baseline/opencode-vanilla)."""
    s = load_settings()
    job_name = job_name or f"vanilla-{dataset}-{datetime.now():%Y%m%d-%H%M%S}"
    client = ProxyClient(s)
    if not client.liveliness():
        rprint("[red]프록시가 응답하지 않습니다. `arena proxy up` 먼저.[/red]")
        raise typer.Exit(1)
    key_info = client.create_key(alias=job_name, max_budget=budget, team="baseline", run_id=job_name, duration="2d")
    key = key_info["key"]
    cfg = harbor_runner.vanilla_job_config(
        s,
        dataset_path=REPO_ROOT / "datasets" / dataset,
        job_name=job_name,
        api_key=key,
        n_concurrent=n_concurrent,
        task_names=task or None,
    )
    cfg_path = harbor_runner.write_job_config(cfg, s.jobs_dir / f"{job_name}.job.yaml")
    try:
        rc = harbor_runner.run_job(cfg_path, settings=s)
    finally:
        spend = client.key_spend(key)
        rprint({"job": job_name, "spend_usd": spend})
        if not keep_key:
            client.delete_key(key)
    raise typer.Exit(rc)


@run_app.command("bundle")
def run_bundle(
    repo: str = typer.Argument(..., help="번들 git URL 또는 로컬 경로"),
    commit: str | None = typer.Option(None, help="커밋 SHA (git URL 이면 필수)"),
    dataset: str = typer.Option("dev", help="datasets/<name>"),
    team: str = typer.Option("adhoc", help="예산·태그용 팀 이름"),
    job_name: str | None = typer.Option(None),
    n_concurrent: int = typer.Option(1),
    budget: float | None = typer.Option(None, help="run 임시 키 예산 USD (기본: 문제 수 × 문제당 상한)"),
    task: list[str] | None = typer.Option(None, help="특정 태스크만"),
    keep_key: bool = typer.Option(False),
) -> None:
    """참가자 번들을 OpenCodeBundleAgent 로 실행한다 (dev/official 공용 경로)."""
    s = load_settings()
    ds = REPO_ROOT / "datasets" / dataset
    ids = json.loads((ds / "task_ids.json").read_text()) if (ds / "task_ids.json").exists() else []
    n_tasks = len(task) if task else len(ids)
    budget = budget if budget is not None else max(0.5, n_tasks * s.cost_cap_per_task)
    job_name = job_name or f"{team}-{dataset}-{datetime.now():%Y%m%d-%H%M%S}"
    client = ProxyClient(s)
    if not client.liveliness():
        rprint("[red]프록시가 응답하지 않습니다. `arena proxy up` 먼저.[/red]")
        raise typer.Exit(1)
    key = client.create_key(alias=job_name, max_budget=budget, team=team, run_id=job_name, duration="2d")["key"]
    cfg = harbor_runner.bundle_job_config(
        s, dataset_path=ds, job_name=job_name, api_key=key, bundle_repo=repo, bundle_commit=commit,
        run_id=job_name, n_concurrent=n_concurrent, task_names=task or None,
    )
    cfg_path = harbor_runner.write_job_config(cfg, s.jobs_dir / f"{job_name}.job.yaml")
    try:
        rc = harbor_runner.run_job(cfg_path, settings=s)
    finally:
        rprint({"job": job_name, "budget_usd": budget, "spend_usd": client.key_spend(key)})
        if not keep_key:
            client.delete_key(key)
    raise typer.Exit(rc)


@run_app.command("summary")
def run_summary(job_name: str) -> None:
    """jobs/<job>/result.json 과 trial 별 reward·비용을 표로 보여준다."""
    s = load_settings()
    job_dir = s.jobs_dir / job_name
    res = harbor_runner.load_job_result(job_dir)
    t = Table(title=job_name)
    for col in ("trial", "task", "reward", "cost_usd", "in_tok", "out_tok", "exception", "trajectory"):
        t.add_column(col)
    for td in harbor_runner.iter_trial_dirs(job_dir):
        r = json.loads((td / "result.json").read_text())
        vr = (r.get("verifier_result") or {}).get("rewards") or {}
        ar = r.get("agent_result") or {}
        ex = (r.get("exception_info") or {}).get("exception_type") or ""
        traj = td / "agent" / "trajectory.json"
        t.add_row(
            td.name,
            r.get("task_name", ""),
            str(vr.get("reward", "")),
            f"{(ar.get('cost_usd') or 0):.4f}",
            str(ar.get("n_input_tokens") or ""),
            str(ar.get("n_output_tokens") or ""),
            ex,
            "yes" if traj.exists() else "[red]no[/red]",
        )
    rprint(t)
    st = res.get("stats", {})
    rprint({k: st.get(k) for k in ("n_completed_trials", "n_errored_trials", "cost_usd")})


# --------------------------------------------------------------------------- stubs (later milestones)
@app.command("validate")
def validate(target: str = typer.Argument(..., help="번들 디렉토리 경로 또는 <git-url>@<sha>")) -> None:
    """번들이 제출 계약(§6)을 따르는지 검사한다. 통과 시 종료 코드 0."""
    from arena.bundle import validate_bundle
    from arena_harness.bundle_agent import BundleError, acquire_bundle

    if "@" in target and "://" in target or target.startswith("git@"):
        repo, _, sha = target.rpartition("@")
        try:
            path = acquire_bundle(repo, sha)
        except BundleError as exc:
            rprint(f"[red][오류] {exc}[/red]")
            raise typer.Exit(1)
    else:
        path = Path(target)
    r = validate_bundle(path)
    rprint(r.render())
    raise typer.Exit(0 if r.ok else 1)


@app.command("submit")
def submit(
    url: str = typer.Argument(..., help="번들 git URL"),
    sha: str = typer.Argument(..., help="커밋 SHA"),
    channel: str = typer.Option("dev", help="dev | official"),
    token: str = typer.Option(..., envvar="ARENA_TEAM_TOKEN", help="팀 토큰 (환경변수 ARENA_TEAM_TOKEN)"),
) -> None:
    """번들을 검증하고 큐에 등록한다. 실패 시 한국어 사유를 출력한다."""
    from arena.db import Store
    from arena.intake import submit as do_submit

    s = load_settings()
    r = do_submit(Store(s.db_path), s, token=token, repo_url=url, commit_sha=sha, channel=channel)
    rprint(r.message)
    raise typer.Exit(0 if r.ok else 1)


teams_app = typer.Typer(no_args_is_help=True, help="팀 등록·토큰·dev 예산 키")
app.add_typer(teams_app, name="teams")


@teams_app.command("create")
def teams_create(
    name: str = typer.Argument(..., help="팀 이름 (소문자·숫자·하이픈)"),
    dev_budget: float = typer.Option(30.0, help="dev 채널 총예산 USD"),
    reference: bool = typer.Option(False, help="참조 행 (순위 미포함)"),
    with_proxy_key: bool = typer.Option(True, help="로컬 opencode 용 팀 가상 키도 발급"),
) -> None:
    """팀을 등록하고 팀 토큰(제출용)과 프록시 가상 키(로컬 개발용)를 발급한다."""
    from arena.db import Store

    s = load_settings()
    store = Store(s.db_path)
    if store.team_by_name(name):
        rprint(f"[red]이미 존재하는 팀입니다: {name}[/red]")
        raise typer.Exit(1)
    proxy_key = None
    if with_proxy_key and not reference:
        proxy_key = ProxyClient(s).create_key(alias=f"team-{name}", max_budget=dev_budget, team=name, duration="60d")["key"]
    team = store.create_team(name, dev_budget_usd=dev_budget, is_reference=reference, proxy_key=proxy_key)
    rprint(json.dumps({"team": name, "token": team["token"], "proxy_key": proxy_key, "dev_budget_usd": dev_budget}, indent=2))


@teams_app.command("list")
def teams_list() -> None:
    from arena.db import Store

    s = load_settings()
    t = Table(title="teams")
    for col in ("name", "reference", "dev_budget", "spend", "token(prefix)"):
        t.add_column(col)
    client = ProxyClient(s)
    live = client.liveliness()
    for team in Store(s.db_path).teams():
        spend = f"{client.key_spend(team['proxy_key']):.2f}" if (live and team.get("proxy_key")) else "-"
        t.add_row(team["name"], "yes" if team["is_reference"] else "", f"{team['dev_budget_usd']:.0f}", spend, team["token"][:10] + "…")
    rprint(t)


@app.command("queue")
def queue(channel: str = typer.Option("dev")) -> None:
    """큐에 대기 중인 제출을 보여준다."""
    from arena.db import Store

    s = load_settings()
    for sub in Store(s.db_path).queued(channel):
        rprint({k: sub[k] for k in ("id", "team_id", "channel", "commit_sha", "submitted_at", "official_day")})


curate_app = typer.Typer(no_args_is_help=True, help="문제 셋 큐레이션 (M3): sample → baseline → assemble")
app.add_typer(curate_app, name="curate")


@curate_app.command("sample")
def curate_sample(n: int = 200, seed: int = 2026, build: bool = typer.Option(True, help="datasets/candidates 도 생성")) -> None:
    """SWE-bench Verified 에서 후보 200개를 표본추출한다 (난이도 필터, 레포 상한 20%)."""
    from arena import curate as cur

    rows = cur.load_verified_rows()
    picked = cur.sample_candidates(rows, n=n, seed=seed)
    cur.CURATION_DIR.mkdir(parents=True, exist_ok=True)
    (cur.CURATION_DIR / "candidates.json").write_text(json.dumps(picked, indent=2) + "\n")
    from collections import Counter

    rprint({"candidates": len(picked), "repos": dict(Counter(p["repo"] for p in picked))})
    if build:
        s = load_settings()
        build_local_dataset(s, "candidates", [p["instance_id"] for p in picked])
        rprint("built datasets/candidates — 다음: `arena run vanilla --dataset candidates -n 16` 를 3회 실행")


@curate_app.command("assemble")
def curate_assemble(
    job: list[str] = typer.Option(..., help="베이스라인 job 이름 (3개)"),
    private_dir: Path = typer.Option(..., help="비공개 데이터셋을 쓸 저장소 밖 경로"),
    seed: int = 2026,
) -> None:
    """베이스라인 3회 결과로 Public 50 / Private 100 / Dev 5 를 구성하고 리포트를 쓴다."""
    from arena import curate as cur

    s = load_settings()
    candidates = json.loads((cur.CURATION_DIR / "candidates.json").read_text())
    outcomes = cur.collect_baseline([s.jobs_dir / j for j in job], candidates)
    sets = cur.assemble_sets(outcomes, seed=seed)
    cur.materialize(s, sets, private_dir=private_dir)
    cur.write_report(outcomes, sets, REPO_ROOT / "docs" / "curation-report.md", model=s.upstream_model)
    (cur.CURATION_DIR / "sets.public-dev.json").write_text(json.dumps({k: sets[k] for k in ("public", "dev")}, indent=2) + "\n")
    rprint({k: len(v) for k, v in sets.items()}, "report → docs/curation-report.md")


final_app = typer.Typer(no_args_is_help=True, help="최종 채점 (M8): run → score → table")
app.add_typer(final_app, name="final")


@final_app.command("run")
def final_run(
    runs: int = typer.Option(2, help="Private 실행 횟수 (예산 부족 시 1)"),
    private_dir: Path = typer.Option(..., help="비공개 데이터셋 경로 (저장소 밖)"),
    team: list[str] | None = typer.Option(None, help="특정 팀만"),
    n_concurrent: int | None = typer.Option(None),
) -> None:
    """각 팀의 마지막 official 제출(코드 프리즈 전)을 Private 셋에서 N회 실행한다."""
    from arena.db import Store
    from worker.runner import run_submission

    s = load_settings()
    store = Store(s.db_path)
    if private_dir.resolve().is_relative_to(REPO_ROOT):
        rprint("[red]private_dir 은 저장소 밖이어야 합니다.[/red]")
        raise typer.Exit(1)
    link = REPO_ROOT / "datasets" / "private"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(private_dir.resolve())  # harbor needs datasets/<name>; symlink is git-ignored
    try:
        for t in store.teams():
            if t["is_reference"] or (team and t["name"] not in team):
                continue
            subs = [x for x in store.submissions_for_team(t["id"]) if x["channel"] == "official" and x["status"] in ("done", "queued", "running")]
            if not subs:
                rprint(f"[yellow]{t['name']}: official 제출 없음, 건너뜀[/yellow]")
                continue
            last = subs[0]
            for i in range(runs):
                rprint(f"[bold]{t['name']}[/bold] private run {i + 1}/{runs} (commit {last['commit_sha'][:7]})")
                run_submission(store, s, last, dataset="private", n_concurrent=n_concurrent, job_name=f"final-{t['name']}-{i + 1}-{datetime.now():%Y%m%d-%H%M%S}")
    finally:
        link.unlink(missing_ok=True)


@final_app.command("score")
def final_score(team: str, score: float = typer.Argument(..., help="발표 점수 0~100"), notes: str = "") -> None:
    """발표 점수를 입력한다 (루브릭 30점 만점 → 0~100 환산해서 입력)."""
    from arena.db import Store

    s = load_settings()
    store = Store(s.db_path)
    t = store.team_by_name(team)
    if not t:
        rprint(f"[red]팀 없음: {team}[/red]")
        raise typer.Exit(1)
    with store.conn() as c:
        c.execute("INSERT INTO presentation_scores(team_id, score, notes) VALUES (?,?,?) ON CONFLICT(team_id) DO UPDATE SET score=excluded.score, notes=excluded.notes", (t["id"], score, notes))
    rprint(f"{team}: presentation={score}")


@final_app.command("table")
def final_table_cmd(out: Path = typer.Option(REPO_ROOT / "data" / "final")) -> None:
    """최종 순위표(final.md, final.json)를 생성한다. 공개 전까지 data/ 에만 둔다."""
    from arena.db import Store
    from arena.final import write_final

    s = load_settings()
    path = write_final(Store(s.db_path), out)
    rprint(path.read_text())


if __name__ == "__main__":
    app()
