#!/usr/bin/env bash
# M4 acceptance: six kinds of invalid bundles produce Korean errors; the daily
# official-submission limit is enforced; a valid bundle is queued.
set -euo pipefail
cd "$(dirname "$0")/../.."
WORK=$(mktemp -d)
export ARENA_DB_PATH="$WORK/arena.sqlite3"
trap 'rm -rf "$WORK"' EXIT

mk() { rm -rf "$WORK/b"; cp -r starter-kit/bundle "$WORK/b"; }
expect_err() { # $1 = grep pattern; validate exits 1 on errors, so capture first
  local out
  out=$(uv run arena validate "$WORK/b" 2>&1 || true)
  if echo "$out" | grep -q "$1"; then echo "  ok: $1"; else echo "FAIL: expected error matching '$1'"; echo "$out"; exit 1; fi
}

echo "== 1 arena.yaml missing";           mk; rm "$WORK/b/arena.yaml";                                   expect_err "arena.yaml"
echo "== 2 main_agent file missing";      mk; rm "$WORK/b/.opencode/agents/main.md";                     expect_err "main_agent"
echo "== 3 forbidden key (model)";        mk; python3 - "$WORK/b" <<'PY'
import json,sys,pathlib; p=pathlib.Path(sys.argv[1])/"opencode.json"; d=json.loads(p.read_text()); d["model"]="x/y"; p.write_text(json.dumps(d))
PY
                                                                                                          expect_err "'model'"
echo "== 4 npm plugin reference";         mk; python3 - "$WORK/b" <<'PY'
import json,sys,pathlib; p=pathlib.Path(sys.argv[1])/"opencode.json"; d=json.loads(p.read_text()); d["plugin"]=["oh-my-openagent@latest"]; p.write_text(json.dumps(d))
PY
                                                                                                          expect_err "npm 패키지"
echo "== 5 forbidden dependency";         mk; python3 - "$WORK/b" <<'PY'
import json,sys,pathlib; p=pathlib.Path(sys.argv[1])/"package.json"; d=json.loads(p.read_text()); d["dependencies"]["oh-my-opencode"]="*"; p.write_text(json.dumps(d))
PY
                                                                                                          expect_err "금지 목록"
echo "== 6 binary file + instance hint";  mk; printf '\x00\x01' > "$WORK/b/x.bin"; echo "django__django-15098" >> "$WORK/b/AGENTS.md"; expect_err "바이너리"; expect_err "인스턴스 ID"

echo "== valid bundle + daily limit"
mk; (cd "$WORK/b" && git init -q && git add -A && git -c user.email=a@b -c user.name=t commit -qm init)
SHA=$(git -C "$WORK/b" rev-parse HEAD)
TOKEN=$(uv run arena teams create team-smoke --no-with-proxy-key | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
export ARENA_TEAM_TOKEN=$TOKEN
uv run arena submit "file://$WORK/b" "$SHA" --channel official | grep -q "접수 완료"
if uv run arena submit "file://$WORK/b" "$SHA" --channel official 2>/dev/null; then echo "FAIL: second official submission accepted"; exit 1; fi
uv run arena submit "file://$WORK/b" "$SHA" --channel official 2>&1 | grep -q "하루 1회" && echo "  daily limit ok"
uv run arena submit "file://$WORK/b" "$SHA" --channel dev | grep -q "접수 완료" && echo "  dev unlimited ok"
echo "M4 SMOKE PASSED"
