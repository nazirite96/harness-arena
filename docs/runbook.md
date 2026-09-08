# 운영 문서

운영진이 대회를 준비하고 돌리는 순서입니다. 명령은 모두 저장소 루트에서 실행합니다.

## 준비물

- x86_64 리눅스 VM 한 대 (SWE-bench 이미지가 amd64입니다). 16 동시 실행 기준 8코어·32GB 이상.
- Docker와 `docker buildx`, `docker compose`. 커널에 nftables(`CONFIG_NFT_FIB_INET`)가 있어야
  Harbor의 네트워크 allowlist가 동작합니다. 일반 Ubuntu 커널은 됩니다.
- uv, git.
- 모델 프로바이더 API 키 하나.

Apple Silicon Mac에서 개발할 때만 추가로 필요한 것:
`brew install docker-buildx` 후 `~/.docker/cli-plugins/docker-buildx`에 링크,
그리고 `scripts/dev/prebuild-egress-sidecar.sh`를 Harbor 버전마다 한 번 실행.
Colima는 `/private/tmp`를 컨테이너에 공유하지 않으니 마운트할 파일은 홈 디렉토리 아래에 두세요.

## 처음 한 번

```bash
cp .env.example .env
```

`.env`에서 채울 것: 프로바이더 키(`ANTHROPIC_API_KEY` 등), `ARENA_UPSTREAM_MODEL`,
`LITELLM_MASTER_KEY`와 `LITELLM_SALT_KEY`(둘 다 임의 문자열, 솔트 키는 한 번 정하면 바꾸지 않음),
`ARENA_PROXY_HOST`(VM에서는 VM 내부 IP), 공개 페이지 문구용 `ARENA_EVENT_NAME`, `ARENA_D1_DATE`,
`ARENA_PROXY_PUBLIC_URL`, `ARENA_STARTER_KIT_URL`, `ARENA_CONTACT`.

```bash
scripts/install-harbor.sh      # uv sync, harbor, arena CLI
uv run arena env               # 툴체인 점검
uv run arena proxy up          # LiteLLM + Postgres 기동, 헬스체크 대기
scripts/smoke/m0.sh            # SWE-bench 1문제 완주. 여기까지 되면 나머지는 순서 문제
scripts/smoke/m1.sh            # 예산 초과 429, 태그가 spend log 에 남는지
```

## 모델 고르기와 문제 셋 만들기 (D-14 ~ D-10)

기준: 저가 티어 후보 중 바닐라 opencode가 Public에서 30~50%를 내는 모델. 너무 강한 모델은
팀 간 차이를 노이즈에 묻히게 합니다.

```bash
uv run arena curate sample                       # SWE-bench Verified 에서 후보 200개, datasets/candidates
uv run arena run vanilla --dataset candidates -n 16 --job-name base-1
uv run arena run vanilla --dataset candidates -n 16 --job-name base-2
uv run arena run vanilla --dataset candidates -n 16 --job-name base-3
uv run arena curate assemble --job base-1 --job base-2 --job base-3 --private-dir ~/arena-private
```

결과: `datasets/public`(50), `datasets/dev`(5), `~/arena-private`(100, 저장소 밖),
`docs/curation-report.md`(Private ID 없음). 모델을 바꾸면 처음부터 다시 합니다.

참조 행을 위해 확정 모델로 Public에서 바닐라를 한 번 더 돌리고 결과를 DB에 넣습니다.

```bash
uv run arena teams create baseline/opencode-vanilla --reference --no-with-proxy-key
uv run arena run vanilla --dataset public -n 16 --job-name ref-vanilla
```

## 리허설 (D-7 ~ D-5)

```bash
scripts/smoke/m2.sh            # 스타터 킷 번들로 dev 5문제, 격리 확인
scripts/smoke/m4.sh            # 잘못된 번들 6종, 하루 1회 제한
scripts/smoke/m5.sh            # 가짜 3팀 야간 배치
scripts/smoke/m6.sh            # 웹 페이지
```

## 팀 등록 (D-3)

```bash
uv run arena teams create team-alpha --dev-budget 30
```

출력의 `token`은 제출과 팀 페이지용, `proxy_key`는 팀이 로컬 opencode에 넣는 키입니다.
둘 다 팀에게만 전달합니다. 스타터 킷 저장소 주소와 함께 보내면 됩니다.

## 대회 기간 운영

프로세스 셋을 띄웁니다. systemd나 tmux 어느 쪽이든 됩니다.

```bash
uv run python -m worker.main dev                                    # dev 큐 즉시 소비
uv run uvicorn web.app:app --host 0.0.0.0 --port 8000              # 웹
# crontab: 0 23 * * *  cd /path/to/harness-arena && uv run python -m worker.main official
```

매일 아침 확인할 것:

- `/admin?admin=<ARENA_ADMIN_TOKEN>`에서 어젯밤 배치가 전부 `done`인지, `error` 열이 비었는지.
- 실패한 제출이 있으면 `uv run arena run summary <job>`으로 어느 문제에서 예외가 났는지 본 뒤
  `uv run python -m worker.main official <YYYY-MM-DD>`로 그 날짜 배치를 다시 돌립니다.
  이미 끝난 제출은 건너뜁니다.
- 팀 dev 예산: `uv run arena teams list`.

웹 페이지: `/` 리더보드(`/?kiosk=1`은 헤더 없는 강의실용, 60초 갱신), `/guide` 참가 안내,
`/team` 팀 페이지, `/trajectory/...` 궤적 뷰어(팀은 자기 것만, 운영진은 `?admin=` 로 전부).

## 최종 채점 (D9 저녁 ~ D10)

```bash
uv run arena final run --runs 2 --private-dir ~/arena-private     # 팀별 마지막 official 제출을 Private 에서 2회
uv run arena final score team-alpha 83.3 --notes "실패 분석 9, 인과 8, ..."   # 발표 점수 0~100
uv run arena final table                                          # data/final/final.md
```

Private 결과는 발표 전까지 웹에 나오지 않습니다. `final.md`를 발표 자료로 옮기세요.
상위 3팀은 번들 코드를 읽고 필요하면 한 번 더 돌려 재현을 확인한 뒤 확정합니다.

## 자주 겪는 문제

- **프록시 401**: `.env`의 프로바이더 키가 비었거나 `ARENA_UPSTREAM_MODEL` 접두어와 키 이름이 안 맞음.
  `uv run arena proxy logs`로 확인.
- **컨테이너가 프록시에 못 붙음**: `ARENA_PROXY_HOST`가 컨테이너에서 보이는 주소가 아님.
  VM에서는 내부 IP, Mac에서는 `host.docker.internal`. `scripts/smoke/probe_isolation.py`로 확인.
- **격리가 안 걸림(github.com이 열림)**: 커널에 nftables가 없어 Harbor가 조용히 allowlist를 끕니다.
  `probe_isolation.py`가 실패로 알려 줍니다.
- **번들 설치 단계에서 bun install 실패**: 팀 `package.json`의 의존성이 npm에 없거나 금지 목록.
  검증기가 먼저 거르지만, 통과했는데 실패하면 팀 페이지의 오류 열을 보세요.

## 비밀값

프로바이더 키는 `.env`에만 있고 프록시 컨테이너만 읽습니다. 팀은 가상 키만 받습니다.
`.env`, `proxy/litellm.config.yaml`, `data/`, `jobs/`, `datasets/private/`는 커밋되지 않습니다.
