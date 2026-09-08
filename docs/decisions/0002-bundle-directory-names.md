# ADR-0002: Bundle uses plural opencode directory names

- Date: 2026-09-07
- Status: Accepted

## Context
PRD §6.1 mixes `.opencode/agents/` with `.opencode/plugin/`. opencode docs
(1.18.x) name the canonical directories in the plural — `agents/`, `plugins/`,
`tools/`, `skills/`, `commands/` — and accept singular forms only for backwards
compatibility. The compiled binary references both.

## Decision
The submission contract, validator and starter kit use plural names only:
`.opencode/agents/*.md`, `.opencode/plugins/*.ts`, `.opencode/tools/*.ts`,
`.opencode/skills/**`. Singular directories are rejected by `arena validate`
with a Korean hint to rename.
