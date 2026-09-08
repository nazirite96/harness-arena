# ADR-0003: Expose the proxy to opencode as custom provider `arena`

- Date: 2026-09-07
- Status: Accepted

## Context
Harbor's builtin OpenCode agent only writes `provider.<id>.options.baseURL` for
`anthropic|google|openai`. Routing through opencode's builtin `openai` provider
would use `@ai-sdk/openai` (Responses API), which is the least mature path
through LiteLLM for non-OpenAI upstreams.

## Decision
Every run writes an `opencode.json` with a single custom provider:

```json
{"model": "arena/arena-model", "small_model": "arena/arena-model",
 "enabled_providers": ["arena"],
 "provider": {"arena": {"npm": "@ai-sdk/openai-compatible",
   "options": {"baseURL": "http://<proxy>:4000/v1", "apiKey": "{env:ARENA_API_KEY}"},
   "models": {"arena-model": {"tool_call": true, "limit": {...}}}}}}
```

`ARENA_API_KEY` is the per-run virtual key, passed via Harbor agent env. Team
bundles may not set `model`/`provider`; the adapter overwrites them (PRD §6.2).

## Consequences
- LiteLLM receives plain `/v1/chat/completions`; tool calls use the most-tested path.
- The model alias is the only model name participants ever see.
