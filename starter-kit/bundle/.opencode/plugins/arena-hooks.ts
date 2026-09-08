// 스타터 킷 예제 훅 3개. 참가자는 이 파일을 복사·수정해 자신의 하네스를 만든다.
//  1) 재현 스크립트를 실행하기 전에는 소스 편집을 막는다.
//  2) 위험한 셸 명령을 차단한다.
//  3) 세션이 멈췄는데(idle) 테스트를 한 번도 실행하지 않았다면 다시 프롬프트를 넣는다 (ralph loop 원리).
import type { Plugin } from "@opencode-ai/plugin"

const DANGEROUS = [/\brm\s+-rf\s+\/(\s|$)/, /\bgit\s+push\b/, /\bgit\s+reset\s+--hard\b/, /\bcurl\b|\bwget\b/, /\bpip\s+install\b/, /\bshutdown\b|\breboot\b/]

export const ArenaHooks: Plugin = async ({ client, directory }) => {
  let reproduced = false
  let testsRan = false
  let nudges = 0

  return {
    "tool.execute.before": async (input, output) => {
      const args: any = output.args ?? {}
      if (input.tool === "bash") {
        const cmd: string = String(args.command ?? "")
        if (DANGEROUS.some((re) => re.test(cmd))) {
          throw new Error(`[arena-hooks] 위험한 명령이 차단되었습니다: ${cmd.slice(0, 80)}`)
        }
        if (/\brepro|python\s+\S*repro|pytest|manage\.py\s+test|python\s+-m\s+(pytest|unittest)/.test(cmd)) reproduced = true
        if (/pytest|manage\.py\s+test|python\s+-m\s+(pytest|unittest)|tox\b/.test(cmd)) testsRan = true
      }
      if ((input.tool === "edit" || input.tool === "write") && !reproduced) {
        const file = String(args.filePath ?? args.path ?? "")
        const isScratch = /repro|scratch|\.tmp/.test(file)
        if (!isScratch) {
          throw new Error("[arena-hooks] 먼저 이슈를 재현하는 스크립트(repro.py 등)를 실행한 뒤 소스 파일을 편집하세요.")
        }
      }
    },

    "tool.execute.after": async (input) => {
      if (input.tool === "run_related_tests") testsRan = true
    },

    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      if (testsRan || nudges >= 2) return
      nudges += 1
      const sessionID = (event as any).properties?.sessionID
      if (!sessionID) return
      await client.session.prompt({
        path: { id: sessionID },
        body: {
          parts: [
            {
              type: "text",
              text: "[arena-hooks] 아직 테스트를 실행하지 않았습니다. `run_related_tests` 로 관련 테스트를 실행해 수정이 올바른지 확인한 뒤 종료하세요.",
            },
          ],
        },
      })
    },
  }
}
