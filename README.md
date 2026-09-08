# Harness Arena

opencode 설정 번들로 경쟁하는 코딩 에이전트 대회 플랫폼입니다.

참가 팀은 에이전트 프롬프트, 훅, 커스텀 툴, 작업 지침을 담은 **번들**을 git 저장소로 제출합니다.
서버는 모든 팀에 같은 모델과 같은 opencode 버전을 강제한 상태로 SWE-bench Verified에서 고른
문제를 돌리고, 테스트 통과 여부로 채점해 리더보드에 올립니다. 캐글처럼 Public 셋으로 매일
순위를 매기고, 마지막 날 비공개 Private 셋으로 최종 점수를 냅니다.

모델과 도구 루프는 누구나 같습니다. 차이를 만드는 건 하네스, 즉 에이전트를 어떻게 지시하고
어디서 막고 언제 다시 시키는가입니다. 비개발자 수강생도 2주 안에 결과를 낼 수 있도록
설계했습니다.

## 어떻게 돌아가나

```
팀 git push
  └─ arena submit (URL + 커밋)  ──▶ 번들 검증 (한국어 오류 메시지)
                                        └─ 큐 등록
                                              ├─ dev 채널: 즉시 Dev 5문제 실행, 팀 예산 차감
                                              └─ official 채널: 23:00 KST 배치, Public 50문제
                                                    │
                          Harbor ─ 태스크 컨테이너(SWE-bench 이미지) 안에
                                   opencode 고정 버전 설치 → 번들 주입 → 모델/권한 덮어쓰기
                                   → 실행 (네트워크는 LLM 프록시만 허용) → 테스트로 채점
                                                    │
                          LiteLLM 프록시 ─ 실행마다 예산이 걸린 임시 키, 전 호출 로그
                                                    │
                          SQLite ─▶ 리더보드 / 팀 페이지 / 궤적 뷰어 (FastAPI)
```

구성 요소는 넷입니다.

| 폴더 | 역할 |
|---|---|
| `arena/` | 운영 CLI. 프록시 키, 데이터셋 구성, 실행, 번들 검증, 제출 접수, 큐레이션, 최종 채점 |
| `arena_harness/` | Harbor 에이전트 어댑터. 번들을 컨테이너에 넣고 opencode를 헤드리스로 돌립니다 |
| `worker/` | 큐 소비자. dev는 바로, official은 야간 배치로 |
| `web/` | 리더보드, 참가 안내, 팀 페이지, 궤적 뷰어, 운영진 뷰 |

그 외 `starter-kit/`(참가자용 번들 템플릿과 안내), `datasets/`(Public/Dev 문제 셋),
`scripts/smoke/`(마일스톤별 인수 테스트), `docs/`(기획서, 규칙, 운영 문서, 결정 기록).

## 참가자라면

[starter-kit/README.md](starter-kit/README.md)부터 읽으세요. opencode 설치부터 첫 dev 실행까지
30분 안에 끝나도록 썼습니다. 운영 서버가 떠 있다면 `/guide` 페이지에 같은 내용이 있습니다.
규칙은 [docs/rules.md](docs/rules.md)에 있습니다.

번들 구조는 이렇습니다.

```
bundle/
  arena.yaml                team, main_agent, description
  opencode.json             instructions 등. model / provider / permission 은 넣지 마세요 (덮어씀)
  AGENTS.md                 저장소 루트에 놓이는 작업 지침
  .opencode/agents/*.md     에이전트 정의. main_agent 파일은 필수
  .opencode/plugins/*.ts    훅과 커스텀 툴 플러그인
  .opencode/tools/*.ts      커스텀 툴 (파일명이 툴 이름)
  package.json              플러그인 의존성 (선택)
```

## 운영자라면

필요한 것: Docker(buildx 포함), [uv](https://docs.astral.sh/uv/), 그리고 모델 프로바이더 API 키 하나.

```bash
cp .env.example .env         # 프로바이더 키, ARENA_UPSTREAM_MODEL, 마스터/솔트 키
scripts/install-harbor.sh    # uv sync, harbor 와 arena CLI 설치
uv run arena proxy up        # LiteLLM + Postgres
scripts/smoke/m0.sh          # SWE-bench 문제 1개를 프록시 경유로 끝까지 돌려봄
```

이후 절차는 [docs/runbook.md](docs/runbook.md)에 순서대로 있습니다. 요약하면
문제 셋 큐레이션 → 팀 등록과 키 배포 → 워커와 웹 서버 기동 → 마지막 날 최종 채점입니다.

웹 페이지는 `/`(리더보드, `/?kiosk=1`은 강의실 화면용), `/guide`(참가 안내), `/team`(팀 페이지),
`/admin?admin=<토큰>`(운영진)입니다. 결과가 아직 없을 때 화면을 보고 싶으면 데모 DB를 쓰세요.

```bash
ARENA_DB_PATH=data/demo.sqlite3 uv run python scripts/dev/seed_demo.py
ARENA_DB_PATH=data/demo.sqlite3 uv run uvicorn web.app:app --port 8000
```

## 몇 가지 설계 결정

- **Harbor를 그대로 씁니다.** 실행과 채점은 [Harbor](https://harborframework.com)가 하고,
  우리는 어댑터·프록시·인테이크·리더보드만 만들었습니다. Harbor 0.22의 네트워크 allowlist로
  에이전트 단계에서는 프록시 외 모든 접속을 막습니다.
- **모델은 프록시 뒤에 하나만 있습니다.** 팀은 LiteLLM 가상 키만 받고, 실행마다 예산이 걸린
  임시 키를 새로 만듭니다. 프로바이더 키는 프록시 서버 밖으로 나가지 않습니다.
- **문제는 베이스라인이 불안정하게 푸는 것 위주로 고릅니다.** 바닐라 opencode를 3번 돌려
  1~2번만 성공하는 문제를 많이 넣어야 훅 하나의 효과가 점수로 보입니다.
- **지루한 기술만 씁니다.** VM 한 대, docker compose, SQLite, cron. 오케스트레이터나
  메시지 브로커는 없습니다.

결정의 배경은 [docs/decisions/](docs/decisions/)에 한 장씩 적어 두었습니다.
버전은 [versions.lock](versions.lock)에 고정되어 있고, 바꿀 때는 결정 기록을 남깁니다.

## 개발

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
```

`scripts/smoke/m*.sh`는 마일스톤별 인수 테스트입니다. LLM 호출이 필요한 것(m0, m1 일부, m2, m5)은
`.env`에 프로바이더 키가 있어야 합니다. m4(번들 검증·제출 제한), m6(웹),
`probe_isolation.py`(네트워크 격리)는 키 없이 돌아갑니다.

Apple Silicon에서 개발한다면 SWE-bench 이미지가 amd64라서 에뮬레이션으로 느리게 돌고,
Harbor의 격리용 사이드카를 `scripts/dev/prebuild-egress-sidecar.sh`로 한 번 미리 빌드해야 합니다.
실제 운영은 x86_64 VM에서 하세요.

## 현재 상태

기획서의 마일스톤 M0~M8 코드가 모두 들어 있습니다. 프록시·격리·검증기·인테이크·웹은 실제로
돌려 확인했고, 실제 모델을 부르는 경로(베이스라인, 큐레이션, 야간 배치)는 프로바이더 키를
넣고 `scripts/smoke/m0.sh`부터 순서대로 돌리면 됩니다. 첫 회차 운영 중 바뀌는 것은
[docs/runbook.md](docs/runbook.md)에 계속 반영합니다.
