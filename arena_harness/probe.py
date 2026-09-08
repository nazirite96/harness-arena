"""NetworkProbeAgent: verifies the agent-phase egress policy without an LLM.

Runs inside the task container during agent.run(): attempts to reach the proxy
(must succeed) and a public host (must fail). Writes /logs/agent/probe.json.
Used by scripts/smoke/probe_isolation.py (ADR-0001 acceptance).
"""

from __future__ import annotations

import json
import shlex
from typing import Any, override

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class NetworkProbeAgent(BaseInstalledAgent):
    def __init__(self, *args: Any, proxy_url: str, blocked_url: str = "https://github.com", **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.proxy_url = proxy_url
        self.blocked_url = blocked_url

    @staticmethod
    @override
    def name() -> str:
        return "arena-network-probe"

    @override
    def version(self) -> str:
        return "0"

    @override
    async def install(self, environment: BaseEnvironment) -> None:
        await self.ensure_system_dependencies(environment, ("curl",))

    @override
    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        def probe(url: str) -> str:
            return f"curl -sS -o /dev/null -m 15 -w '%{{http_code}}' {shlex.quote(url)} 2>/dev/null || true"

        cmd = (
            f"P=$({probe(self.proxy_url)}); B=$({probe(self.blocked_url)}); "
            f"printf '{{\"proxy\": \"%s\", \"blocked\": \"%s\"}}' \"$P\" \"$B\" | tee /logs/agent/probe.json"
        )
        result = await environment.exec(command=cmd)
        (self.logs_dir / "probe-stdout.txt").write_text(result.stdout or "")
        context.metadata = {"probe": json.loads(result.stdout.strip() or "{}")}
