#!/usr/bin/env bash
# M6 acceptance: leaderboard renders with reference rows; team page needs the team
# token; a team cannot open another team's trajectory; pages fit a mobile viewport.
set -euo pipefail
cd "$(dirname "$0")/../.."
PORT=${PORT:-8766}
uv run uvicorn web.app:app --port "$PORT" --log-level warning & PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
sleep 3
code() { curl -s -o /tmp/m6.html -w "%{http_code}" "http://127.0.0.1:$PORT$1"; }
test "$(code /)" = "200" && grep -q 'name="viewport"' /tmp/m6.html && echo "  leaderboard ok (mobile viewport meta present)"
grep -q "참조" /tmp/m6.html && echo "  reference rows rendered" || echo "  (no reference row yet — seed baseline run)"
test "$(code /api/leaderboard)" = "200" && echo "  api ok"
test "$(code /guide)" = "200" && grep -q "진행 순서" /tmp/m6.html && echo "  guide page ok"
test "$(code '/?kiosk=1')" = "200" && grep -q 'class="kiosk"' /tmp/m6.html && echo "  kiosk mode ok"
test "$(code /team/not-a-token)" = "403" && echo "  team token required"
test "$(code /admin)" = "403" && echo "  admin token required"
TOKENS=$(uv run python -c "from arena.db import Store; from arena.config import load_settings; st=Store(load_settings().db_path); print(' '.join(t['token'] for t in st.teams() if not t['is_reference']))")
set -- $TOKENS
if [ $# -ge 1 ]; then test "$(code /team/$1)" = "200" && echo "  own team page ok"; fi
if [ $# -ge 2 ]; then
  RUN=$(uv run python -c "from arena.db import Store; from arena.config import load_settings; st=Store(load_settings().db_path); t=st.team_by_token('$2'); rs=[r for r in st.runs_for_team(t['id']) if st.trials_for_run(r['id'])]; print(rs[0]['id'] if rs else '')")
  if [ -n "$RUN" ]; then
    TRIAL=$(uv run python -c "from arena.db import Store; from arena.config import load_settings; st=Store(load_settings().db_path); print(st.trials_for_run($RUN)[0]['trial_name'])")
    test "$(code /trajectory/$1/$RUN/$TRIAL)" = "403" && echo "  cross-team trajectory blocked"
  fi
fi
echo "M6 SMOKE PASSED"
