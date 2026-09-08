#!/usr/bin/env bash
# M1 acceptance: virtual keys with budgets; budget overrun is rejected (429);
# spend logs carry team/run tags.
set -euo pipefail
cd "$(dirname "$0")/../.."
RUN="m1-smoke-$(date +%s)"

echo "== proxy"
uv run arena proxy health | grep -q "liveliness.*True" || uv run arena proxy up

echo "== zero-budget key must be rejected with 429"
ZERO=$(uv run arena keys create --alias "$RUN-zero" --max-budget 0 --team smoke --run-id "$RUN" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $ZERO" -H 'content-type: application/json' \
  -d '{"model":"arena-model","messages":[{"role":"user","content":"hi"}],"max_tokens":4}')
test "$STATUS" = "429" || { echo "FAIL: expected 429, got $STATUS"; exit 1; }
uv run arena keys delete "$ZERO" >/dev/null

echo "== key restricted to the single alias (403 on another model)"
KEY=$(uv run arena keys create --alias "$RUN" --max-budget 0.05 --team smoke --run-id "$RUN" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hi"}]}')
test "$STATUS" = "403" || { echo "FAIL: expected 403, got $STATUS"; exit 1; }

echo "== one real request, then tags must appear in spend logs"
STATUS=$(curl -s -o /tmp/m1.body -w "%{http_code}" http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"model":"arena-model","messages":[{"role":"user","content":"Reply with: pong"}],"max_tokens":4}')
if [ "$STATUS" != "200" ]; then
  echo "FAIL: upstream call returned $STATUS (provider key in .env?)"; head -c 300 /tmp/m1.body; echo; exit 1
fi
sleep 3
uv run arena keys logs --key "$KEY" --limit 5 | grep -q "run:$RUN" || { echo "FAIL: run tag missing from spend logs"; exit 1; }
uv run arena keys logs --key "$KEY" --limit 5 | grep -q "team:smoke" || { echo "FAIL: team tag missing from spend logs"; exit 1; }
SPEND=$(uv run arena keys spend "$KEY" | tr -d "{}' " | cut -d: -f2)
echo "spend after one call: $SPEND"
uv run arena keys delete "$KEY" >/dev/null
echo "M1 SMOKE PASSED"
