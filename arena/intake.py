"""Submission intake shared by the CLI (`arena submit`) and the web form (PRD §5.1 #4)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from arena.bundle import validate_bundle
from arena.config import Settings
from arena.db import DailyLimitError, Store
from arena_harness.bundle_agent import BundleError, acquire_bundle

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
# https / ssh remotes for participants; file:// for operator dry runs (PRD §13 M5 fake teams)
URL_RE = re.compile(r"^(https://[\w.-]+/[\w./-]+?(\.git)?|git@[\w.-]+:[\w./-]+?(\.git)?|file:///[\w./-]+)$")


@dataclass
class IntakeResult:
    ok: bool
    message: str  # Korean, shown to the participant
    submission_id: int | None = None


def submit(store: Store, s: Settings, *, token: str, repo_url: str, commit_sha: str, channel: str) -> IntakeResult:
    team = store.team_by_token(token.strip())
    if not team:
        return IntakeResult(False, "팀 토큰이 올바르지 않습니다.")
    if channel not in ("dev", "official"):
        return IntakeResult(False, "채널은 dev 또는 official 이어야 합니다.")
    repo_url = repo_url.strip()
    commit_sha = commit_sha.strip().lower()
    if not URL_RE.match(repo_url):
        return IntakeResult(False, "git URL 형식이 올바르지 않습니다 (https://github.com/org/repo.git 형태).")
    if not SHA_RE.match(commit_sha):
        return IntakeResult(False, "commit SHA 는 7~40자리 16진수여야 합니다.")
    try:
        path = acquire_bundle(repo_url, commit_sha)
    except BundleError as exc:
        return IntakeResult(False, str(exc))
    result = validate_bundle(path)
    if not result.ok:
        return IntakeResult(False, "번들 검증 실패 — 큐에 등록되지 않았습니다.\n" + result.render())
    try:
        sub = store.add_submission(team["id"], channel=channel, repo_url=repo_url, commit_sha=commit_sha, validation=result.render())
    except DailyLimitError as exc:
        return IntakeResult(False, f"공식 제출은 하루 1회입니다. {exc.day} 배치에 이미 제출이 있습니다 (마감 22:00 KST).")
    when = "곧 실행됩니다 (dev)." if channel == "dev" else f"{sub['official_day']} 23:00 KST 배치에서 실행됩니다."
    return IntakeResult(True, f"제출 #{sub['id']} 접수 완료. {when}\n" + result.render(), sub["id"])
