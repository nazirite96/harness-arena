# ADR-0001: Use Harbor 0.22 native network allowlist instead of Pier

- Date: 2026-09-07
- Status: Accepted

## Context
PRD §5.3 lists two isolation options and flags "Harbor blocks LLM calls under
`allow_internet=false`" as `[확인 필요]`. Inspection of `harbor==0.22.0` shows
`allow_internet` is deprecated and replaced by a phase-scoped policy:

- `[environment] network_mode = "allowlist"` + `allowed_hosts` — baseline at
  container start (agent install phase).
- `[agent] network_mode/allowed_hosts` — applied during `agent.run()` only.
- `[verifier] network_mode/allowed_hosts` — applied during verification.
- CLI `--allow-agent-host`, `--allow-environment-host` merge extra hosts.
- Enforcement on Docker: a `gost` sidecar with nftables (`harbor-docker-egress-control-sidecar`),
  the task container joins the sidecar's network namespace. Linux only.

## Decision
Use Harbor's native allowlist. `arena dataset build` rewrites each task's
`task.toml`: environment baseline = proxy + package registries; agent phase =
proxy only; verifier = baseline. Pier is not used.

## Consequences
- One fewer dependency; Harbor stays upstream.
- The AC "curl https://github.com fails during the agent phase, proxy succeeds"
  is verified by `scripts/smoke/m2.sh`.
- If the host kernel lacks `CONFIG_NFT_FIB_INET`, Harbor silently disables
  egress control; the smoke test must therefore assert the failure, not assume it.
