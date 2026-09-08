// 예제 커스텀 툴: 이슈와 관련된 테스트만 골라 실행한다 (전체 스위트는 너무 느리다).
// 파일명이 툴 이름이 된다: run_related_tests
import { tool } from "@opencode-ai/plugin"

export default tool({
  description:
    "이슈와 관련된 테스트만 실행합니다. Django 저장소면 `tests/runtests.py <label>`, 그 외는 `pytest <paths> -x -q` 를 사용합니다. 반드시 수정 후 호출하세요.",
  args: {
    targets: tool.schema
      .array(tool.schema.string())
      .describe("테스트 파일 경로 또는 Django 테스트 라벨 (예: ['tests/i18n/tests.py'] 또는 ['i18n'])"),
    timeoutSec: tool.schema.number().optional().describe("타임아웃 초 (기본 600)"),
  },
  async execute(args, context) {
    const cwd = context.directory
    const timeout = (args.timeoutSec ?? 600) * 1000
    const isDjango = await Bun.file(`${cwd}/tests/runtests.py`).exists()
    const cmd = isDjango
      ? ["python", "tests/runtests.py", "--parallel", "1", ...args.targets.map((t) => t.replace(/^tests\//, "").replace(/\.py$/, "").replace(/\//g, "."))]
      : ["python", "-m", "pytest", "-x", "-q", "--no-header", ...args.targets]
    const proc = Bun.spawn(cmd, { cwd, stdout: "pipe", stderr: "pipe" })
    const timer = setTimeout(() => proc.kill(), timeout)
    const [out, err] = await Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text()])
    const code = await proc.exited
    clearTimeout(timer)
    const tail = (s: string) => s.split("\n").slice(-60).join("\n")
    return `$ ${cmd.join(" ")}\nexit=${code}\n--- stdout ---\n${tail(out)}\n--- stderr ---\n${tail(err)}`
  },
})
