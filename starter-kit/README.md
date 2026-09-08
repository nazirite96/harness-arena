# 참가자 가이드 (30분 안에 첫 실행까지)

여러분이 만드는 것은 **opencode 설정 번들**입니다: 에이전트 프롬프트, 훅(플러그인), 커스텀 툴, 지침(AGENTS.md).
모델·버전·권한은 운영진이 고정합니다. 여러분은 *하네스*만 바꿉니다.

## 0. 받은 것 확인
운영진에게서 두 가지를 받았는지 확인하세요.
- **팀 토큰** `tm_…` — 제출과 팀 페이지 열람용
- **프록시 키** `sk-…` — 로컬 opencode 가 대회 모델을 쓰기 위한 키 (팀 dev 예산 $30 에서 차감)

## 1. opencode 설치 (고정 버전)
```bash
npm install -g opencode-ai@1.18.29
opencode --version
```

## 2. 번들 템플릿 복사 + 프록시 연결
```bash
git clone <운영진이 준 starter-kit 주소> my-bundle && cd my-bundle
```
`bundle/` 폴더가 여러분의 번들입니다. 로컬에서 대회 모델로 시험하려면 **번들 밖의 개인 설정**
`~/.config/opencode/opencode.json` 에 프록시 프로바이더를 추가하세요 (번들에는 넣지 않습니다. 넣으면 검증에서 거부됩니다).
```json
{
  "model": "arena/arena-model",
  "provider": {
    "arena": {
      "npm": "@ai-sdk/openai-compatible",
      "options": { "baseURL": "http://<운영진 프록시 주소>:4000/v1", "apiKey": "{env:ARENA_API_KEY}" },
      "models": { "arena-model": { "name": "arena-model", "tool_call": true, "limit": { "context": 200000, "output": 32000 } } }
    }
  }
}
```
```bash
export ARENA_API_KEY=sk-…      # 받은 프록시 키
```

## 3. 로컬에서 번들 동작 확인
SWE-bench 문제와 비슷한 아무 파이썬 저장소에서 실행해 봅니다.
```bash
cd /path/to/some-python-repo
cp -r /path/to/my-bundle/bundle/.opencode .   # 번들의 에이전트·훅·툴을 이 프로젝트에 적용
cp /path/to/my-bundle/bundle/AGENTS.md .
opencode --agent main                          # TUI 에서 main 에이전트로 대화
```
헤드리스(대회와 같은 방식)로 실행:
```bash
opencode run --agent main "README 에 오타가 있는지 확인하고 고쳐줘"
```
훅이 동작하면 재현 전 편집이 막히는 메시지 `[arena-hooks] …` 를 볼 수 있습니다.

## 4. 번들 구조 (제출 계약)
```
bundle/
  arena.yaml                team, main_agent, description  (필수)
  opencode.json             instructions, agent 비활성화 등 (model/provider/permission 금지)
  AGENTS.md                 저장소 루트(/testbed)에 복사되는 지침
  .opencode/agents/*.md     에이전트 정의. main_agent 파일 필수
  .opencode/plugins/*.ts    훅·커스텀 툴 플러그인
  .opencode/tools/*.ts      커스텀 툴 (파일명 = 툴 이름)
  .opencode/skills/**       스킬 (선택)
  package.json              플러그인 의존성 (선택, 완성형 에이전트 플러그인 금지)
```
- 폴더 이름은 복수형(`agents/`, `plugins/`, `tools/`)만 인정됩니다.
- 5MB 이하, 바이너리 파일 금지, npm 플러그인 참조 금지, 문제 ID 하드코딩 금지.

## 5. 검증
```bash
uvx --from git+<운영진 레포> arena validate ./bundle     # 또는 운영진이 준 arena 실행파일
```
한국어로 항목별 오류가 나옵니다. `[통과]` 가 나와야 제출됩니다.

## 6. dev 실행 요청 (즉시, 5문제, 팀 예산 차감)
```bash
git add -A && git commit -m "hooks: block edit before repro" && git push
export ARENA_TEAM_TOKEN=tm_…
arena submit https://github.com/<team>/<repo>.git $(git rev-parse HEAD) --channel dev
```
또는 팀 페이지(`/team/<토큰>`)의 폼에 URL 과 커밋 SHA 를 넣습니다. 완료되면 팀 페이지에 문제별 결과와 궤적 링크가 뜹니다.

## 7. 공식 제출 (하루 1회, 22:00 KST 마감)
```bash
arena submit https://github.com/<team>/<repo>.git <sha> --channel official
```
23:00 배치에서 Public 50문제를 돌리고 아침 리더보드에 반영됩니다.

## 8. 궤적 읽는 법
팀 페이지 → 실행 → 셀 클릭. 단계마다 모델 메시지, 툴 호출(인자), 툴 출력, 토큰·비용이 보입니다.
살펴볼 것: 재현 없이 편집했는가 · 테스트를 실행했는가 · 같은 명령을 반복하는가(doom loop) · 어디서 예산·시간을 다 썼는가.
발표 채점의 핵심은 "어떤 훅/프롬프트 변경이 어떤 궤적 변화를 만들었는가"를 보여주는 것입니다.

## 자주 나오는 실패 패턴
1. 재현 없이 추측으로 수정 → 관련 없는 파일 변경, 테스트 실패
2. 전체 테스트 스위트 실행 → 시간 초과(30분)
3. 서브에이전트에게 편집을 맡김 → 컨텍스트 유실
4. 종료 전 테스트 미실행 → `session.idle` 훅으로 재프롬프트
5. `pip install` 시도 → 네트워크 차단으로 실패, 시간 낭비

## 규칙·채점
[docs/rules.md](../docs/rules.md) 를 읽으세요. 최종 = Private 해결률 70% + 발표 30%.
