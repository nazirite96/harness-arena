"""Final scoring (PRD §4): 0.7 × Private resolved % (mean of N runs) + 0.3 × presentation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from arena.db import Store


def final_table(store: Store, *, private_dataset: str = "private") -> list[dict[str, Any]]:
    rows = []
    with store.conn() as c:
        pres = {r["team_id"]: r["score"] for r in c.execute("SELECT team_id, score FROM presentation_scores")}
    for team in store.teams():
        if team["is_reference"]:
            continue
        runs = [r for r in store.runs_for_team(team["id"], private_dataset) if r["status"] == "done" and r["n_tasks"]]
        if not runs:
            continue
        rates = [100.0 * (r["n_resolved"] or 0) / r["n_tasks"] for r in runs]
        private_rate = sum(rates) / len(rates)
        presentation = pres.get(team["id"])
        total = 0.7 * private_rate + 0.3 * (presentation or 0.0)
        cost = sum((r["cost_usd"] or 0) for r in runs) / len(runs)
        rows.append({
            "team": team["name"], "private_runs": len(runs), "private_rate": private_rate, "private_rates": rates,
            "presentation": presentation, "total": total, "avg_cost_per_task": cost / runs[0]["n_tasks"],
            "commit": runs[0]["bundle_commit"],
        })
    rows.sort(key=lambda r: (-r["total"], r["avg_cost_per_task"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def render_markdown(rows: list[dict[str, Any]]) -> str:
    out = ["# 최종 순위", "", "최종 점수 = 0.7 × Private 해결률 + 0.3 × 발표 점수. 동점은 문제당 평균 비용이 낮은 팀 우위.", "",
           "| 순위 | 팀 | Private 해결률 (실행별) | 발표 | 최종 | 비용/문제 | 커밋 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        rates = " / ".join(f"{x:.1f}" for x in r["private_rates"])
        pres = f"{r['presentation']:.1f}" if r["presentation"] is not None else "미입력"
        out.append(f"| {r['rank']} | {r['team']} | {r['private_rate']:.1f}% ({rates}) | {pres} | **{r['total']:.1f}** | ${r['avg_cost_per_task']:.3f} | `{(r['commit'] or '')[:7]}` |")
    return "\n".join(out) + "\n"


def write_final(store: Store, out_dir: Path) -> Path:
    rows = final_table(store)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "final.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    path = out_dir / "final.md"
    path.write_text(render_markdown(rows))
    return path
