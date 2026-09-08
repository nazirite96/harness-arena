from arena.db import Store
from arena.final import final_table, render_markdown


def test_final_scoring(tmp_path):
    st = Store(tmp_path / "a.sqlite3")
    a = st.create_team("team-a"); b = st.create_team("team-b"); st.create_team("ref", is_reference=True)
    for team, resolved in ((a, (60, 50)), (b, (55, 55))):
        for i, n in enumerate(resolved):
            st.create_run(team_id=team["id"], dataset="private", job_name=f"{team['name']}-{i}", status="done", n_tasks=100, n_resolved=n, cost_usd=10.0, bundle_commit="abc")
    with st.conn() as c:
        c.execute("INSERT INTO presentation_scores(team_id, score) VALUES (?,?)", (a["id"], 80.0))
        c.execute("INSERT INTO presentation_scores(team_id, score) VALUES (?,?)", (b["id"], 90.0))
    rows = final_table(st)
    by = {r["team"]: r for r in rows}
    assert by["team-a"]["private_rate"] == 55.0 and by["team-a"]["total"] == 0.7 * 55 + 0.3 * 80
    assert by["team-b"]["total"] == 0.7 * 55 + 0.3 * 90
    assert rows[0]["team"] == "team-b" and rows[0]["rank"] == 1
    assert "ref" not in by
    md = render_markdown(rows)
    assert "team-b" in md and "최종 순위" in md
