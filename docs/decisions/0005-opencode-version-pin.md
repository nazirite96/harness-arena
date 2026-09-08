# ADR-0005: opencode pinned to 1.18.29 for development; re-pin at D-7

- Date: 2026-09-07
- Status: Accepted (provisional pin)

## Context
PRD §15 fixes the opencode version at the latest stable as of kickoff D-7.
`npm view opencode-ai` on 2026-09-07 reports 1.18.29 (published 2026-09-04),
with a near-daily release cadence. The locally installed 1.14.48 is stale.

## Decision
`versions.lock` pins `OPENCODE_VERSION=1.18.29` now so all milestones test
against one version. At D-7 the operator re-pins by editing `versions.lock`
and recording the new version in this ADR. Harbor installs opencode inside
each task container with `npm i -g opencode-ai@<version>`.
