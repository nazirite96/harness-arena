# PRD — 에이전트 만들기 대회 플랫폼 (가칭 Harness Arena)
- 문서 버전: 0.1 (2026-09-07)
- 상태: Draft — Claude Code 구현 착수용
- 작성: 박기웅 (모두의연구소) · 초안 정리 Claude
---
## 0. 이 문서를 읽는 Claude Code에게
1. 이 문서는 **대회 운영 플랫폼**의 요구사항이다. §13 마일스톤 순서대로 구현하고, 각 마일스톤의 수용 기준(AC)을 `scripts/smoke/` 아래 스모크 테스트로 증명한다.
2. 외부 도구(Harbor/Pier, opencode, LiteLLM, SWE-bench)의 CLI·API·폴더 규약은 빠르게 바뀐다. **코드를 쓰기 전에 현재 문서와 `--help`로 검증**하고, 확정된 버전을 `versions.lock`에 고정한다. 본문의 `[확인 필요]` 표시는 구현 시점에 반드시 검증한다.
3. 지루한 기술을 택한다: 단일 VM, docker compose, SQLite, cron. Kubernetes·메시지 브로커·마이크로서비스 금지.
4. 참가자용 문서·에러 메시지는 **한국어**, 코드·식별자·커밋 메시지는 영어.
5. **비공개(Private) 문제 목록과 프로바이더 API 키는 참가자에게 노출될 수 있는 어떤 경로(레포, 리더보드, 로그 링크, 에러 메시지)에도 절대 포함하지 않는다.** 테스트로 보장한다.
6. 결정이 필요한 항목은 §15의 기본값으로 진행하고, 기본값을 바꾼 경우 `docs/decisions/`에 ADR 한 장을 남긴다.
---
## 1. 배경과 한 줄 요약
KDT 비개발자 수강생이 팀 단위로 **opencode 설정 번들(에이전트·훅·커스텀 툴·지침)**을 만들어 제출하면, 서버가 **고정 모델·고정 opencode 버전**으로 SWE-bench Verified에서 선별한 문제를 자동 실행·채점하고, **캐글식 Public/Private 리더보드**로 순위를 매기는 1~2주 스프린트 대회 플랫폼.
왜 이 형태인가:
- 에이전트 루프·기본 도구는 검증된 opencode를 그대로 쓰고, 참가자는 **하네스 엔지니어링**(프롬프트, 서브에이전트 오케스트레이션, 훅, 커스텀 툴, 지침)에만 집중한다. 비개발자도 2주 안에 결과를 낼 수 있다.
- 배운 것이 곧 실무 코딩 에이전트 활용 능력이다. oh-my-opencode(OMO)가 참고 모델이자 교재다.
- 실행·채점은 Harbor(Terminal-Bench 팀의 에이전트 평가 프레임워크)가 담당한다. Harbor 레지스트리에 SWE-bench Verified가 있고, 설치형 에이전트 목록에 opencode가 있다. 운영진이 만들 것은 **어댑터·프록시·인테이크·리더보드**다.
---
## 2. 목표 / 비목표
### 목표
- **G1** 제출 → 검증 → 자동 실행 → 채점 → 리더보드 갱신이 사람 개입 없이 매일 돈다.
- **G2** 모든 팀이 동일 모델, 동일 예산 상한, 동일 opencode 버전에서 경쟁한다.
- **G3** 문제 셋이 하네스 변경에 민감하게 반응한다(베이스라인이 불안정하게 푸는 문제 중심으로 큐레이션).
- **G4** 참가자는 로컬 Docker 없이 에디터 + git + 로컬 opencode만으로 참여한다.
- **G5** 모든 실행의 궤적(trajectory)이 보존되고, 팀이 자기 궤적을 웹에서 읽을 수 있다.
### 비목표
- 범용 평가 플랫폼, 다중 대회 동시 운영, 결제·과금, 외부 공개 서비스 수준의 보안·가용성
- SWE-bench 이외 벤치마크(다음 회차에서 검토)
- 참가자별 모델 선택, 멀티모델 에이전트
---
## 3. 사용자
| 역할 | 인원 | 하는 일 |
|---|---|---|
| 참가자 | 3~4명 × 최대 10팀, 비개발자 | 번들 개발, dev 실행 요청, 하루 1회 공식 제출, 자기 궤적 확인, 최종 발표 |
| 운영진 | 1~2명 | 모델 선정, 큐레이션, 배치 감시, 규칙 위반 확인, 최종 채점 |
| 심사 | 운영진 + 멘토 | 발표(30%) 채점 |
---
## 4. 대회 규격
- **기간**: 10일 스프린트(기본). 1주 축약안은 §11.
- **벤치마크**: SWE-bench Verified 큐레이션 셋
  - Public 50 — 목록 공개, 일일 리더보드용
  - Private 100 — 비공개, 최종 채점용
  - Dev 5 — Public의 부분집합, 참가자 즉시 실행용
- **지표**: 해결률 resolved % (Harbor verifier 통과 trial 비율). 동점 시 문제당 평균 비용이 낮은 팀 우위.
- **최종 점수** = 0.7 × Private 해결률(0~100) + 0.3 × 발표 점수(0~100)
  - Private는 2회 실행 평균. 예산 부족 시 1회로 축소하되 사전 공지.
- **참조 행**(순위 미포함, 항상 표시): `baseline/opencode-vanilla`, `reference/oh-my-opencode`
- **제출 제한**: 공식 제출 팀당 1일 1회(마감 22:00 KST). dev 실행은 팀 예산 내 무제한.
- **발표 채점 루브릭(30점)**: 실패 패턴 분석 10 · 변경→효과 인과를 궤적으로 증명 10 · 비용 효율·재현성 5 · 전달력 5
---
## 5. 시스템 아키텍처
### 5.1 컴포넌트
| # | 컴포넌트 | 구현 | 역할 |
|---|---|---|---|
| 1 | LLM 프록시 | LiteLLM (docker) | 고정 모델 단일 노출. 팀별 가상 키(dev 예산), 실행(run)별 임시 키(`max_budget`), 전 호출 로그 |
| 2 | 실행기 | Harbor 또는 Pier + `arena_harness.OpenCodeBundleAgent` | 태스크 컨테이너에 opencode 설치, 번들 주입, 실행, verifier 채점, trajectory 저장 |
| 3 | 데이터셋 | Harbor 로컬 데이터셋 | `datasets/public`, `datasets/dev` (공개 레포), `datasets/private` (비공개 저장소) |
| 4 | 인테이크 | 웹 폼 + CLI `arena submit` | 팀 토큰, git URL, commit SHA, 채널(dev / official) → 검증 → 큐 |
| 5 | 워커 | Python 프로세스 + cron | dev는 즉시 소비, official은 23:00 KST 배치 |
| 6 | 저장소 | SQLite + 파일시스템 | `teams, submissions, runs, trials` + Harbor job 디렉토리 |
| 7 | 리더보드 웹 | FastAPI + Jinja (+HTMX), 모바일 우선 | 공개 리더보드 / 팀 상세 / 궤적 뷰어 / 운영진 뷰 |
| 8 | 스타터 킷 | 번들 템플릿 + 문서 | §12 |
### 5.2 흐름 (official 채널)
```
팀 git push
 → 웹 폼/CLI 제출 (URL + SHA)
 → arena validate (실패 시 한국어 사유 반환, 큐 등록 안 함)
 → queue(official)
 → 23:00 KST 배치
     run별 임시 프록시 키 발급 (max_budget = 문제 수 × 문제당 상한)
     harbor run -p datasets/public \
       --agent-import-path arena_harness:OpenCodeBundleAgent \
       --ak bundle_repo=<url> --ak bundle_commit=<sha> \
       --ak run_id=<id> -n 16
     result.json / trajectory.json 파싱 → DB
     임시 키 폐기
 → 리더보드 갱신 (08:00 KST 전)
```
dev 채널은 동일 파이프라인을 `datasets/dev`로 즉시 실행하고, 완료 시 팀 상세 페이지에 결과·궤적 링크를 노출한다.
### 5.3 네트워크 격리 (핵심 안전장치)
- 태스크 컨테이너는 **프록시 호스트만** 접근 가능해야 한다. 설치 단계에서만 npm/pypi 레지스트리를 추가 허용.
- 구현 옵션
  - (a) Pier(Harbor 포크)의 에이전트별 network allowlist — Harbor는 `allow_internet=false`에서 LLM 호출까지 막기 때문에 순정 Harbor만으로는 부족하다 `[확인 필요: 현재 Harbor 버전]`
  - (b) GCP VM 이그레스 방화벽(프록시·레지스트리만 허용) + 컨테이너 네트워크 정책
- `[확인 필요]` opencode가 시작 시 접근하는 외부 엔드포인트(models.dev 등 모델 메타데이터, 업데이트 체크)를 파악해 allowlist에 넣거나 캐시/비활성화 처리한다. 이걸 놓치면 격리 환경에서 opencode가 기동 실패한다.
- AC: 격리 환경에서 `curl https://github.com`은 실패하고 프록시 호출은 성공한다(스모크 테스트).
---
## 6. 제출 계약 (Submission Contract)
### 6.1 번들 구조
```
bundle/
  arena.yaml              team, main_agent, description   (필수)
  opencode.json           plugin 등록(로컬 파일만), instructions 등
  AGENTS.md               레포 루트(/testbed)에 복사되는 지침
  .opencode/agents/*.md   에이전트 정의(프롬프트·도구 권한). main_agent 필수 존재
  .opencode/plugin/*.ts   플러그인(훅·커스텀 툴)
  .opencode/tools/*.ts    커스텀 툴 (선택)
  .opencode/skills/**     스킬 (선택)
  package.json            플러그인 의존성 (선택)
```
`[확인 필요]` 폴더명(`agents`/`agent`, `plugin`/`plugins`)은 고정 opencode 버전의 공식 문서 기준으로 확정하고 검증기와 스타터 킷에 동일하게 반영한다.
`arena.yaml` 예:
```yaml
team: "team-name"
main_agent: "main"        # .opencode/agents/main.md 가 존재해야 함
description: "한 줄 설명"
```
### 6.2 운영진이 덮어쓰거나 거부하는 항목
| 항목 | 처리 |
|---|---|
| `model`, `provider` (opencode.json 및 각 agent frontmatter의 model) | 고정 모델 + LiteLLM 프록시(openai-compatible provider)로 **강제 덮어쓰기** |
| `permission` | 헤드리스 실행용 전부 allow로 덮어쓰기 |
| `plugin` 배열의 npm 패키지 참조 | **거부** — 로컬 파일 경로만 허용 |
| `package.json` 의존성 | 허용. 단 금지 목록(oh-my-opencode 및 파생, 기타 완성형 에이전트 플러그인) 포함 시 거부 |
| opencode 버전 | `OPENCODE_VERSION`으로 고정, 참가자 변경 불가 |
### 6.3 실행 절차
1. **설치 단계**(네트워크: 프록시 + 레지스트리)
   - opencode 고정 버전 설치
   - 번들을 opencode 글로벌 설정 디렉토리(`~/.config/opencode/`)에 복사 `[확인 필요: 프로젝트 `.opencode/` 대신 글로벌을 쓰는 것이 SWE-bench 레포 오염을 피하는 데 유리한지 검증]`
   - §6.2 오버라이드 적용
   - `bun install` 선행 실행으로 플러그인 의존성 캐시 (opencode는 시작 시 package.json 의존성을 bun으로 설치함)
   - `AGENTS.md`를 레포 루트(`/testbed`)에 복사 `[확인 필요: Harbor swebench 태스크의 레포 경로]`
2. **실행 단계**(네트워크: 프록시만)
   - `opencode run --agent <main_agent> "<instruction>"` `[확인 필요: 플래그 이름, 비대화식 종료 동작]`
   - 헤드리스, 사용자 입력 없이 종료까지 자동 진행
3. **출력**: 별도 산출물 없음. 종료 시점의 `/testbed` 상태로 Harbor verifier가 테스트를 실행한다.
### 6.4 제한
- 문제당 wall-clock 30분 `[확인 필요: Harbor agent timeout 설정 위치]`
- run당 예산 = 문제 수 × 문제당 상한(기본 $0.50, 베이스라인 측정 후 조정). run별 임시 키의 `max_budget`으로 강제
- 번들 크기 ≤ 5MB, 바이너리 파일 금지
### 6.5 검증기 `arena validate <path | url@sha>`
- 검사: 구조, `arena.yaml` 필수 필드, `main_agent` 파일 존재, 금지 키(§6.2), 금지 의존성, npm plugin 참조, 크기·바이너리
- 실패 시 항목별 한국어 메시지. 통과 시에만 큐 등록
- 참가자도 로컬에서 실행 가능(`pipx run` 또는 단일 스크립트)
---
## 7. 채점 · 리더보드
### 7.1 공개 리더보드
컬럼: 순위 · 팀 · Public 해결률 · Δ(직전 제출 대비) · 해결 수/50 · 평균 비용/문제 · 평균 시간/문제 · 제출 횟수 · 커밋(short SHA) · 갱신 시각
참조 행 2개는 상단 고정, 순위에서 제외.
### 7.2 팀 상세 (팀 토큰 필요)
- 제출 이력, 문제별 pass/fail 매트릭스(Public·Dev만), trial별 궤적 링크, 비용 추이
- dev 실행 결과는 완료 즉시 표시
### 7.3 궤적 뷰어
- Harbor `trajectory.json`(ATIF)을 채팅형으로 렌더: 단계별 모델 메시지, 툴 호출과 인자, 툴 출력, 토큰·비용
- 팀은 자기 궤적만, 운영진은 전체 열람
- `[확인 필요]` Pier의 뷰어(`pier view`)를 재사용할 수 있으면 자체 구현 최소화
### 7.4 비노출 원칙
Private 결과·Private 문제 ID는 최종 발표 전까지 어떤 페이지·API·로그 링크에도 노출하지 않는다.
### 7.5 운영진 점검 뷰
- 시스템 프롬프트·플러그인 소스와 금지 플러그인의 유사도 표시
- 번들 내 SWE-bench 인스턴스 ID 패턴(예 `django__django-12345`) 문자열 검색
- 격리 환경에서의 비정상 네트워크 시도 로그
---
## 8. 문제 셋 큐레이션 `arena curate`
목적: 바닐라 베이스라인이 **불안정하게** 푸는 문제를 중심으로 구성해, 훅 하나의 변화가 점수로 드러나게 한다.
1. **후보 풀**: SWE-bench Verified에서 난이도 라벨 `"<15 min fix"`, `"15 min - 1 hour"` `[확인 필요: HF 데이터셋의 difficulty 필드 문자열]` 중, 레포별 상한 20%로 200개 표본.
2. **베이스라인**: `baseline/opencode-vanilla` + 고정 모델로 200개 × 3회 → 문제별 해결 횟수 0 / 1~2 / 3.
3. **구성**
   - Public 50 = 불안정(1~2회) 30 + 미해결(0회) 12 + 안정(3회) 8
   - Private 100 = 불안정 60 + 미해결 25 + 안정 15
   - Dev 5 = Public 중 불안정 3 + 안정 2
   - Public과 Private는 겹치지 않으며 레포 분포를 균형 있게 유지
4. **산출물**: `datasets/{public,private,dev}/` (Harbor 로컬 데이터셋 형식) + 각 `task_ids.json`, 큐레이션 리포트 `docs/curation-report.md`(Private ID 제외). `datasets/private`는 별도 비공개 저장소.
5. **참조 실행**: 동일 셋에서 `reference/oh-my-opencode`(고정 모델, 단일 모델 설정) 3회 → 참조 행 데이터.
6. **모델 선정 기준**: 저가 티어 후보 2~3개 중 바닐라 베이스라인이 Public에서 30~50% 나오는 모델. 강한 모델은 팀 간 차이를 노이즈에 묻히게 하므로 피한다.
---
## 9. 모델 · 예산 정책
- 전 팀 동일 모델 1개. 번들 내 모든 에이전트 역할(메인·서브에이전트)도 같은 모델 — 멀티모델 불가.
- 팀 예산: dev 채널 총액 기본 $30/팀(조정 가능). official·final 실행은 운영진 예산.
- 예산 소진 시 dev 실행 거부 + 팀 상세에 잔액 표시.
- 프록시 로그(프롬프트·응답 포함)를 운영진이 대회 운영·교육 목적으로 열람한다는 점을 규칙에 명시.
---
## 10. 참가자 규칙 (초안, `docs/rules.md`로 발행)
1. 제출물은 §6 계약을 따르는 opencode 설정 번들만 인정한다.
2. 기존 에이전트 제품·플러그인(oh-my-opencode 포함)을 통째로 제출하는 것은 금지. 코드를 참고하거나 일부 차용하는 것은 허용하되 출처를 표기한다.
3. 번들을 만드는 데 Claude Code 등 코딩 에이전트를 쓰는 것은 자유다.
4. 인스턴스 ID·레포·이슈를 특정하는 힌트 하드코딩 금지. 외부 네트워크 접근 시도 금지.
5. 공식 제출은 하루 1회(22:00 KST 마감). 코드 프리즈 D9 18:00.
6. 최종 순위 = Private 70% + 발표 30%. 상위 3팀은 코드 리뷰·재현 확인 후 확정한다.
7. 위반 시 해당 제출 무효, 반복 시 실격.
---
## 11. 일정
**준비**
- D-14 모델 후보 2~3개로 바닐라 베이스라인 실행, 모델 확정
- D-10 큐레이션 완료, 참조 행 실행
- D-7 어댑터 스모크(템플릿 번들로 dev 5문제), opencode 버전 고정
- D-5 가짜 2팀으로 nightly 드라이런
- D-3 스타터 킷·규칙 공개, 팀 키 배포
**본 대회 (10일)**
- D1 킥오프: opencode 확장점 강의, OMO 훅 3개 코드 리딩, 스타터 킷으로 첫 dev 실행, 리더보드 오픈(참조 행 게시)
- D2~D4 반복 · 매일 공식 제출
- D5 중간 세션: 운영진이 전 팀 실패 유형을 집계해 공유
- D6~D8 반복
- D9 18:00 코드 프리즈 → 야간 Private 채점(2회)
- D10 결과 공개 · 발표 · 최종 순위
**1주 축약안**: 중간 세션 D3, 프리즈 D4 18:00, 발표 D5.
---
## 12. 스타터 킷 (`starter-kit/`)
- **번들 템플릿**
  - 메인 에이전트 1 + 탐색 서브에이전트 1
  - 예제 훅 3개: 재현 스크립트 실행 전 편집 차단 / 종료 직전 테스트 미실행이면 되돌리기(session.idle 재프롬프트 — ralph loop 원리) / 위험 명령 차단
  - 예제 커스텀 툴 1개: 이슈 관련 테스트만 실행
  - `AGENTS.md` 예시, `arena.yaml`
- **참가자 README(한국어)**: 로컬 opencode 설치 → 프록시 키 설정 → 로컬 TUI에서 번들 동작 확인 → `arena validate` → dev 실행 요청 → 공식 제출 → 궤적 읽는 법. **비개발자가 30분 내 완료 가능**해야 한다.
- 규칙 문서, FAQ, 채점 설명, 자주 나오는 실패 패턴 목록
---
## 13. 마일스톤 · 수용 기준 (구현 순서)
| M | 범위 | 수용 기준 (스모크 테스트로 증명) |
|---|---|---|
| **M0** 스캐폴드·환경 | uv 프로젝트, docker compose(proxy), Harbor/Pier 설치, opencode 고정 설치 스크립트, `versions.lock`, `.env.example` | 프록시 경유 `-a opencode`로 SWE-bench Verified 1문제 실행 성공, `trajectory.json`·`result.json` 생성 |
| **M1** 프록시 | 팀 키 발급/폐기 CLI, run별 임시 키(`max_budget`), spend 조회, 태그(team/run) | 예산 초과 시 요청 거부, 로그에 team·run 태그 기록 |
| **M2** 어댑터 `OpenCodeBundleAgent` | 번들 클론·복사·오버라이드·`bun install` 선행·`main_agent` 실행 | 템플릿 번들로 dev 5문제 완주, 모델 강제가 프록시 로그로 검증됨, 격리 환경에서 프록시 외 접속 실패 |
| **M3** 큐레이션 CLI | §8 전체 | 산출물 생성, `datasets/private` ID가 공개 경로에 없음을 테스트로 보장 |
| **M4** 인테이크·검증기·DB | 웹 폼, `arena submit`, `arena validate`, 스키마 | 잘못된 번들 6종에 한국어 오류, 1일 1회 제한 동작 |
| **M5** 워커·스케줄러 | 큐 소비, nightly cron, 재시도, 결과 파싱 | 가짜 3팀 nightly 배치 완주(≤4h, n=16), 실패 trial 1회 재시도, DB 반영 |
| **M6** 리더보드·팀 상세·궤적 뷰어 | §7 | 모바일에서 열람, 참조 행 표시, 팀은 자기 궤적만 열람 |
| **M7** 스타터 킷·문서 | §12 | 비개발자 1명이 README만으로 로컬 TUI 실행 성공(운영진 관찰 테스트) |
| **M8** 리허설·최종 채점 | `arena final --runs 2`, 발표 점수 입력, 최종 표 | 드라이런 후 최종 순위표 생성 |
---
## 14. 비기능 요구사항
- 동시 실행 16(기본). 야간 배치 10팀 × 50문제 ≤ 4시간. 부족하면 Daytona/Modal 등 클라우드 샌드박스 환경 옵션 추가.
- 궤적·로그 보존: 대회 종료 후 30일.
- 재현성: 모든 run에 opencode 버전, 모델, 번들 커밋, 데이터셋 해시, 프록시 설정 해시 기록.
- 장애: 배치 실패 시 운영진 알림(Slack 웹훅, 선택), 재실행은 명령 1줄.
- 비용 가시성: 팀별·일별 지출 대시보드(운영진).
- 보안: 프로바이더 키는 프록시 서버에만 존재. 참가자는 가상 키만 받는다. 시크릿은 커밋 금지(`.env.example`만).
---
## 15. 결정 필요 항목과 기본값
| 항목 | 기본값 | 비고 |
|---|---|---|
| 고정 모델 | 미정 → M0 이후 베이스라인으로 결정 | 저가 티어, Public 30~50% |
| Harbor vs Pier | 격리 allowlist가 필요하면 Pier, 아니면 Harbor + VM 방화벽 | M0에서 격리 방식 검증 후 확정 |
| opencode 버전 | 킥오프 D-7 기준 최신 안정판 고정 | 이후 변경 금지 |
| 팀 수 | 10 | |
| 제출 채널 | 웹 폼 + CLI | Slack 봇은 선택 |
| Private 실행 횟수 | 2 | 예산 부족 시 1 |
| 문제당 비용 상한 | $0.50 | 베이스라인 후 조정 |
| 문제당 시간 상한 | 30분 | |
| 클라우드 샌드박스 | 미사용(로컬 Docker) | 최종 채점 병렬 필요 시 도입 |
| 리더보드 호스팅 | 동일 VM, 팀 페이지는 토큰 | |
---
## 16. 레포 구조 제안
```
harness-arena/
  pyproject.toml  versions.lock  .env.example  docker-compose.yml
  arena/              CLI (typer): validate, submit, curate, run, final, keys
  arena_harness/      Harbor 에이전트 어댑터 (OpenCodeBundleAgent)
  worker/             큐 소비자, 스케줄러
  web/                FastAPI 리더보드 · 팀 상세 · 궤적 뷰어 · 운영진 뷰
  datasets/           public/  dev/   (private/ 는 별도 비공개 저장소)
  starter-kit/        번들 템플릿 + 참가자 문서
  docs/               rules.md  runbook.md  curation-report.md  decisions/
  scripts/smoke/      마일스톤별 스모크 테스트
```
---
## 17. 참고 (구현 시 최신 버전으로 재확인)
- Harbor 문서·레지스트리: https://harborframework.com/docs/evals · https://registry.harborframework.com/
- Harbor 커스텀 에이전트(설치형): https://www.tbench.ai/docs/agent-introduction
- Pier (Harbor 포크, 네트워크 allowlist): https://pypi.org/project/datacurve-pier
- harbor-agents — Claude Code에 스킬 폴더를 `--ak`로 주입하는 어댑터 패턴(우리 어댑터의 참고 구현): https://pypi.org/project/harbor-agents/
- opencode 플러그인 문서: https://opencode.ai/docs/plugins/
- SWE-bench Verified (HF): https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified
- LiteLLM 가상 키·예산: https://docs.litellm.ai/docs/proxy/virtual_keys
- oh-my-opencode: https://github.com/code-yeongyu/oh-my-opencode
---
## 18. 용어
- **번들**: 팀이 제출하는 opencode 설정 묶음(§6.1)
- **run**: 하나의 제출을 하나의 데이터셋에서 실행한 단위. 임시 키 1개, 비용 합산 1개
- **trial**: run 안의 문제 1개 실행. pass/fail, 비용, 시간, 궤적을 가짐
- **Public / Private / Dev**: §4의 세 문제 셋
- **참조 행**: 순위에 들지 않는 비교 기준(바닐라 opencode, OMO)
- **불안정 문제**: 바닐라 베이스라인이 3회 중 1~2회만 푸는 문제. 하네스 개선이 점수로 가장 잘 드러난다
---
## 변경 이력
- 0.1 (2026-09-07) 초안. 설계 대화 정리: 캐글식 Public/Private → 에이전트 제출형 → opencode 번들(OMO 방식)로 수렴
