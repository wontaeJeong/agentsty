# Roadmap

## Phase 0: foundation

- Define product and architecture docs.
- Create uv workspace structure.
- Establish shared typed contracts.
- Bootstrap API and proxy apps.
- Add lint, typecheck, tests, pre-commit, and CI.

## MVP phase

- Implement control-plane run/session/job services.
- Add a local-development sandbox backend with explicit limits and lifecycle handling.
- Add local metadata and artifact storage adapters.
- Add a minimal proxy pathway for model-provider access.
- Add authenticated internal usage flow.

## Hardening phase

- Replace development stubs with hardened runtime adapters.
- Enforce deny-by-default network restrictions in the real sandbox runtime.
- Add stronger secret-resolution flow and proxy policy enforcement.
- Add structured audit events and traceable artifact lineage.
- Add admission checks, timeouts, quotas, and cleanup guarantees.

## Extensibility phase

- Add multiple agent backend implementations behind the shared agent protocol.
- Add multiple storage backends, including object storage.
- Add richer workspace models such as copied or ephemeral per-run workspaces.
- Add contract test suites for all adapters.
- Add stronger policy modeling for tool, network, and artifact capabilities.

## Operational maturity phase

- Add observability, alerting, and audit review workflows.
- Add admin tools for policy and tenant management.
- Add retention policies for logs and artifacts.
- Add deployment automation and environment promotion workflows.
- Add incident response playbooks for sandbox and proxy events.
