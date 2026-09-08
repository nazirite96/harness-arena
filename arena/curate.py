"""Problem-set curation (PRD §8).

Pipeline (each step is a CLI subcommand so operators can inspect between steps):
  sample   → data/curation/candidates.json        200 ids from SWE-bench Verified
  baseline → (operator runs `arena run vanilla` 3x on datasets/candidates)
  assemble → datasets/public, datasets/dev, <private dir>, docs/curation-report.md

Private ids are written ONLY under `private_dir` (outside this repo) and to
~/.cache/harness-arena/private_task_ids.json (used by tests/test_no_private_leak.py).
"""

from __future__ import annotations

import json
import random
import shutil
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arena.config import REPO_ROOT, Settings
from arena.datasets import build_local_dataset

CURATION_DIR = REPO_ROOT / "data" / "curation"
PRIVATE_IDS_CACHE = Path.home() / ".cache" / "harness-arena" / "private_task_ids.json"
ELIGIBLE_DIFFICULTY = ("<15 min fix", "15 min - 1 hour")
HF_DATASET = "princeton-nlp/SWE-bench_Verified"

# Composition (PRD §8.3): counts per bucket. flaky = solved 1-2 of 3, zero = 0/3, stable = 3/3.
COMPOSITION = {
    "public": {"flaky": 30, "zero": 12, "stable": 8},
    "private": {"flaky": 60, "zero": 25, "stable": 15},
}
DEV = {"flaky": 3, "stable": 2}


def load_verified_rows() -> list[dict[str, Any]]:
    from datasets import load_dataset  # optional extra `curate`

    ds = load_dataset(HF_DATASET, split="test")
    return [{"instance_id": r["instance_id"], "repo": r["repo"], "difficulty": r["difficulty"]} for r in ds]


def sample_candidates(rows: Iterable[dict[str, Any]], *, n: int = 200, repo_cap_ratio: float = 0.2, seed: int = 2026) -> list[dict[str, Any]]:
    """Eligible difficulties only; no repo may exceed `repo_cap_ratio` of the sample."""
    rng = random.Random(seed)
    eligible = [r for r in rows if r["difficulty"] in ELIGIBLE_DIFFICULTY]
    by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in eligible:
        by_repo[r["repo"]].append(r)
    for lst in by_repo.values():
        rng.shuffle(lst)
    cap = int(n * repo_cap_ratio)
    picked: list[dict[str, Any]] = []
    # round-robin over repos so small repos are represented, respecting the cap
    repos = sorted(by_repo)
    counts: Counter[str] = Counter()
    while len(picked) < n:
        progressed = False
        for repo in repos:
            if counts[repo] >= cap or not by_repo[repo]:
                continue
            picked.append(by_repo[repo].pop())
            counts[repo] += 1
            progressed = True
            if len(picked) >= n:
                break
        if not progressed:
            break
    return sorted(picked, key=lambda r: r["instance_id"])


@dataclass
class BaselineOutcome:
    instance_id: str
    repo: str
    solved: int  # 0..3
    cost_usd: float

    @property
    def bucket(self) -> str:
        return "zero" if self.solved == 0 else ("stable" if self.solved >= 3 else "flaky")


def collect_baseline(job_dirs: list[Path], candidates: list[dict[str, Any]]) -> list[BaselineOutcome]:
    """Aggregate reward per task across N vanilla jobs (one job = one attempt over all candidates)."""
    repo_of = {c["instance_id"]: c["repo"] for c in candidates}
    solved: Counter[str] = Counter()
    cost: dict[str, float] = defaultdict(float)
    seen: Counter[str] = Counter()
    for job in job_dirs:
        for trial in job.iterdir():
            rp = trial / "result.json"
            if not rp.exists() or not (trial / "agent").is_dir():
                continue
            r = json.loads(rp.read_text())
            tid = r["task_name"]
            if tid not in repo_of:
                continue
            seen[tid] += 1
            reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward", 0) or 0
            solved[tid] += 1 if reward >= 1 else 0
            cost[tid] += ((r.get("agent_result") or {}).get("cost_usd") or 0.0)
    out = []
    for tid, repo in repo_of.items():
        if seen[tid] == 0:
            continue
        out.append(BaselineOutcome(tid, repo, solved[tid], cost[tid] / max(seen[tid], 1)))
    return out


def assemble_sets(outcomes: list[BaselineOutcome], *, seed: int = 2026) -> dict[str, list[str]]:
    """Split into public/private/dev per COMPOSITION, balancing repos within each bucket."""
    rng = random.Random(seed)
    buckets: dict[str, list[BaselineOutcome]] = defaultdict(list)
    for o in outcomes:
        buckets[o.bucket].append(o)

    def take(bucket: str, n: int, exclude: set[str]) -> list[BaselineOutcome]:
        pool = [o for o in buckets[bucket] if o.instance_id not in exclude]
        by_repo: dict[str, list[BaselineOutcome]] = defaultdict(list)
        for o in pool:
            by_repo[o.repo].append(o)
        for lst in by_repo.values():
            rng.shuffle(lst)
        chosen: list[BaselineOutcome] = []
        repos = sorted(by_repo)
        while len(chosen) < n and any(by_repo[r] for r in repos):
            for r in repos:
                if by_repo[r] and len(chosen) < n:
                    chosen.append(by_repo[r].pop())
        if len(chosen) < n:
            raise SystemExit(f"[curate] '{bucket}' 버킷에 문제가 부족합니다: 필요 {n}, 가용 {len(chosen)}. 후보 풀을 늘리세요.")
        return chosen

    used: set[str] = set()
    sets: dict[str, list[str]] = {}
    for name in ("public", "private"):
        ids: list[str] = []
        for bucket, n in COMPOSITION[name].items():
            picked = take(bucket, n, used)
            ids += [o.instance_id for o in picked]
            used.update(o.instance_id for o in picked)
        sets[name] = sorted(ids)
    public_outcomes = {o.instance_id: o for o in outcomes if o.instance_id in set(sets["public"])}
    dev: list[str] = []
    for bucket, n in DEV.items():
        pool = sorted(o.instance_id for o in public_outcomes.values() if o.bucket == bucket)
        rng.shuffle(pool)
        dev += pool[:n]
    sets["dev"] = sorted(dev)
    assert not (set(sets["public"]) & set(sets["private"]))
    assert set(sets["dev"]) <= set(sets["public"])
    return sets


def write_report(outcomes: list[BaselineOutcome], sets: dict[str, list[str]], path: Path, *, model: str) -> None:
    """Curation report without private ids (PRD §8.4)."""
    by_bucket = Counter(o.bucket for o in outcomes)
    pub = [o for o in outcomes if o.instance_id in set(sets["public"])]
    lines = [
        "# Curation report",
        "",
        f"- Baseline model: `{model}`",
        f"- Candidates with baseline results: {len(outcomes)}",
        f"- Buckets (3 attempts): flaky={by_bucket['flaky']} zero={by_bucket['zero']} stable={by_bucket['stable']}",
        f"- Public: {len(sets['public'])} · Private: {len(sets['private'])} (ids withheld) · Dev: {len(sets['dev'])}",
        "",
        "## Public set",
        "",
        "| instance_id | repo | baseline solved/3 | avg cost USD |",
        "|---|---|---|---|",
    ]
    for o in sorted(pub, key=lambda o: o.instance_id):
        lines.append(f"| {o.instance_id} | {o.repo} | {o.solved} | {o.cost_usd:.3f} |")
    lines += ["", "## Dev set", ""] + [f"- {i}" for i in sets["dev"]]
    lines += ["", "## Private set", "", f"{len(sets['private'])} tasks. Repo distribution only:", ""]
    priv_repos = Counter(o.repo for o in outcomes if o.instance_id in set(sets["private"]))
    lines += [f"- {repo}: {n}" for repo, n in sorted(priv_repos.items())]
    path.write_text("\n".join(lines) + "\n")


def materialize(s: Settings, sets: dict[str, list[str]], *, private_dir: Path) -> None:
    from arena import datasets as ds_mod

    if private_dir.resolve().is_relative_to(REPO_ROOT):
        raise SystemExit("[curate] private_dir 은 이 저장소 밖이어야 합니다 (PRD §0.5).")
    build_local_dataset(s, "public", sets["public"], overwrite=True)
    build_local_dataset(s, "dev", sets["dev"], overwrite=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    for iid in sets["private"]:
        dest = private_dir / iid
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ds_mod.fetch_task(s, iid), dest)
        ds_mod.patch_task_toml(dest, s)
    (private_dir / "task_ids.json").write_text(json.dumps(sets["private"], indent=2) + "\n")
    PRIVATE_IDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_IDS_CACHE.write_text(json.dumps(sets["private"], indent=2) + "\n")
