#!/usr/bin/env bash
# M2 acceptance: the starter-kit bundle completes the dev set through
# OpenCodeBundleAgent; the proxy log shows only the fixed model; during the agent
# phase the container can reach the proxy but nothing else.
set -euo pipefail
cd "$(dirname "$0")/../.."
DATASET="${SMOKE_DATASET:-dev}"
JOB="m2-smoke-$(date +%Y%m%d-%H%M%S)"

echo "== validate template bundle"
uv run arena validate starter-kit/bundle

echo "== dataset"
test -f "datasets/$DATASET/task_ids.json" || { echo "FAIL: datasets/$DATASET 가 없습니다 (arena dataset build / arena curate)"; exit 1; }

echo "== run bundle"
uv run arena run bundle starter-kit/bundle --dataset "$DATASET" --team template --job-name "$JOB" --n-concurrent "${SMOKE_CONCURRENCY:-2}" --keep-key
uv run arena run summary "$JOB"

echo "== every trial produced a trajectory"
for t in jobs/$JOB/*/; do
  test -f "$t/agent/trajectory.json" || { echo "FAIL: no trajectory in $t"; exit 1; }
done

echo "== forced model: every spend-log row uses the alias"
uv run arena keys logs --limit 50 | grep -q "run:$JOB" || { echo "FAIL: run tag missing"; exit 1; }
if uv run arena keys logs --limit 50 | grep "run:$JOB" | grep -v -q "arena-model"; then echo "FAIL: non-alias model in logs"; exit 1; fi

echo "== isolation: agent-phase egress denied except proxy (probe trial)"
# The starter kit's dangerous-command hook blocks curl for the agent, so probe from the
# operator side: run a one-off trial whose bundle instruction curls github.com.
uv run python scripts/smoke/probe_isolation.py --dataset "$DATASET"

echo "M2 SMOKE PASSED: $JOB"
