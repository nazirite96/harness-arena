# ADR-0004: LiteLLM runs with its own Postgres container

- Date: 2026-09-07
- Status: Accepted

## Context
PRD §0.3 prefers SQLite. LiteLLM virtual keys, `max_budget` enforcement and
spend logs require `DATABASE_URL` (Postgres); there is no SQLite mode.

## Decision
`docker-compose.yml` runs `ghcr.io/berriai/litellm-database:v1.100.0` with a
`postgres:16` sidecar. The arena application itself still uses SQLite. The
Postgres instance is internal to the compose network and holds only proxy
state (keys, spend logs). Image tags are pinned in `versions.lock`.
