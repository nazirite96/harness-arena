#!/usr/bin/env bash
# M5 acceptance: three fake teams submit official bundles; the nightly batch runs all
# of them on datasets/public (n=16, ≤4h), failed trials are retried once
# (harbor retry.max_retries=1), results land in the DB and on the leaderboard.
# Requires a provider key in .env and datasets/public (arena curate).
set -euo pipefail
cd "$(dirname "$0")/../.."
DATASET="${SMOKE_DATASET:-public}"
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
test -f "datasets/$DATASET/task_ids.json" || { echo "FAIL: datasets/$DATASET 없음"; exit 1; }

for i in 1 2 3; do
  cp -r starter-kit/bundle "$WORK/t$i"; sed -i.bak "s/team-template/fake-team-$i/" "$WORK/t$i/arena.yaml"; rm "$WORK/t$i/arena.yaml.bak"
  (cd "$WORK/t$i" && git init -q && git add -A && git -c user.email=a@b -c user.name=t commit -qm init)
  SHA=$(git -C "$WORK/t$i" rev-parse HEAD)
  TOKEN=$(uv run arena teams create "fake-team-$i" --no-with-proxy-key 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])" || uv run python -c "from arena.db import Store; from arena.config import load_settings; print(Store(load_settings().db_path).team_by_name('fake-team-$i')['token'])")
  ARENA_TEAM_TOKEN=$TOKEN uv run arena submit "file://$WORK/t$i" "$SHA" --channel official
done
DAY=$(uv run python -c "from arena.db import official_day_for; from datetime import datetime, timezone; print(official_day_for(datetime.now(timezone.utc)))")
START=$(date +%s)
uv run python -m worker.main official "$DAY"
ELAPSED=$(( $(date +%s) - START ))
echo "batch took ${ELAPSED}s"
test $ELAPSED -le 14400 || { echo "FAIL: batch exceeded 4h"; exit 1; }
uv run python - <<'PY'
from arena.db import Store; from arena.config import load_settings
st = Store(load_settings().db_path)
rows = {r["team_name"]: r for r in st.latest_public_runs()}
for i in (1,2,3):
    r = rows.get(f"fake-team-{i}"); assert r and r["status"] == "done", f"fake-team-{i} run missing"
    assert st.trials_for_run(r["id"]), "no trials ingested"
print("DB rows ok:", {k: (v["n_resolved"], v["n_tasks"]) for k, v in rows.items() if k.startswith("fake-team")})
PY
echo "M5 SMOKE PASSED"
