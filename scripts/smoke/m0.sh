#!/usr/bin/env bash
# M0 acceptance: one SWE-bench Verified task runs through the LiteLLM proxy with
# Harbor's builtin opencode agent; trajectory.json and result.json are produced;
# the proxy log carries the run tag.
set -euo pipefail
cd "$(dirname "$0")/../.."

TASK="${SMOKE_TASK:-django__django-15098}"
JOB="m0-smoke-$(date +%Y%m%d-%H%M%S)"

echo "== 1. env"
uv run arena env
test -f .env || { echo "FAIL: .env 가 없습니다 (cp .env.example .env 후 키 입력)"; exit 1; }

echo "== 2. proxy"
uv run arena proxy up

echo "== 3. dataset (1 task)"
uv run arena dataset build smoke "$TASK"
test -f "datasets/smoke/$TASK/task.toml"
grep -q 'network_mode = "allowlist"' "datasets/smoke/$TASK/task.toml"

echo "== 4. harbor run (builtin opencode via proxy)"
uv run arena run vanilla --dataset smoke --job-name "$JOB" --budget 2 --keep-key

echo "== 5. artifacts"
JOBDIR="jobs/$JOB"
test -f "$JOBDIR/result.json" || { echo "FAIL: result.json 없음"; exit 1; }
TRIAL=$(ls -d "$JOBDIR"/*/ | head -1)
test -f "$TRIAL/agent/trajectory.json" || { echo "FAIL: trajectory.json 없음 ($TRIAL)"; exit 1; }
test -f "$TRIAL/result.json"
uv run arena run summary "$JOB"

echo "== 6. proxy log tag"
uv run arena keys logs --limit 5 | grep -q "run:$JOB" && echo "tag ok" || { echo "FAIL: run 태그가 spend log 에 없음"; exit 1; }

echo "M0 SMOKE PASSED: $JOB"
