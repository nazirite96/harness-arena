"""LiteLLM proxy helpers: render config, health, virtual keys, spend."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

from arena.config import REPO_ROOT, Settings

TEMPLATE = REPO_ROOT / "proxy" / "litellm.config.template.yaml"
RENDERED = REPO_ROOT / "proxy" / "litellm.config.yaml"


def render_config(s: Settings) -> Path:
    values = {
        "ARENA_MODEL_ALIAS": s.model_alias,
        "ARENA_UPSTREAM_MODEL": s.upstream_model,
        "ARENA_UPSTREAM_KEY_ENV": s.upstream_key_env,
        "ARENA_MODEL_CONTEXT": s.get("ARENA_MODEL_CONTEXT", "200000"),
        "ARENA_MODEL_OUTPUT": s.get("ARENA_MODEL_OUTPUT", "32000"),
    }
    text = TEMPLATE.read_text()

    def sub(m: re.Match[str]) -> str:
        k = m.group(1)
        if k not in values:
            raise SystemExit(f"[proxy] 템플릿 변수 {k} 값이 없습니다.")
        return str(values[k])

    RENDERED.write_text(re.sub(r"\$\{([A-Z_]+)\}", sub, text))
    return RENDERED


def compose(*args: str) -> int:
    env_file = REPO_ROOT / ".env"
    cmd = ["docker", "compose", "--env-file", str(env_file), *args]
    return subprocess.call(cmd, cwd=REPO_ROOT)


class ProxyClient:
    """Thin admin client for the LiteLLM proxy (uses the master key)."""

    def __init__(self, s: Settings, base_url: str | None = None):
        self.s = s
        self.base = (base_url or s.proxy_url_local).rstrip("/")
        self.http = httpx.Client(
            base_url=self.base,
            headers={"Authorization": f"Bearer {s.master_key}"},
            timeout=30,
        )

    # ---- health --------------------------------------------------------
    def liveliness(self) -> bool:
        try:
            r = httpx.get(f"{self.base}/health/liveliness", timeout=5)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def models(self) -> list[str]:
        r = self.http.get("/v1/models")
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]

    # ---- keys ----------------------------------------------------------
    def create_key(
        self,
        *,
        alias: str,
        max_budget: float,
        team: str | None = None,
        run_id: str | None = None,
        duration: str | None = None,
        budget_duration: str | None = None,
    ) -> dict[str, Any]:
        tags = [f"team:{team}" if team else "team:none"]
        if run_id:
            tags.append(f"run:{run_id}")
        body: dict[str, Any] = {
            "key_alias": alias,
            "max_budget": max_budget,
            "models": [self.s.model_alias],
            "metadata": {"tags": tags, "team": team, "run_id": run_id},
        }
        if duration:
            body["duration"] = duration
        if budget_duration:
            body["budget_duration"] = budget_duration
        r = self.http.post("/key/generate", json=body)
        r.raise_for_status()
        return r.json()

    def delete_key(self, key: str) -> None:
        r = self.http.post("/key/delete", json={"keys": [key]})
        r.raise_for_status()

    def key_info(self, key: str) -> dict[str, Any]:
        r = self.http.get("/key/info", params={"key": key})
        r.raise_for_status()
        return r.json()

    def key_spend(self, key: str) -> float:
        info = self.key_info(key).get("info", {})
        return float(info.get("spend") or 0.0)

    def spend_logs(self, *, api_key: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if api_key:
            params["api_key"] = api_key
        r = self.http.get("/spend/logs", params=params)
        r.raise_for_status()
        data = r.json()
        return data[-limit:] if isinstance(data, list) else data

    # ---- smoke ---------------------------------------------------------
    def chat_once(self, key: str, prompt: str = "Reply with the single word: pong") -> dict[str, Any]:
        r = httpx.post(
            f"{self.base}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": self.s.model_alias,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 16,
            },
            timeout=60,
        )
        try:
            body = r.json()
        except json.JSONDecodeError:
            body = {"raw": r.text}
        return {"status": r.status_code, "body": body}
