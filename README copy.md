# agentcask MVP Documentation Pack

This pack describes the MVP implementation target for **agentcask**.

The MVP provides a Kubernetes-native agent session platform with:

- `cask-api`: REST API + WebSocket terminal gateway + minimal model proxy
- `cask-controller`: Kubernetes custom controller
- `AgentSession` CRD under `agentcask.aidev.samsungds.net`
- per-session Agent Pods
- optional runtime isolation through `isolationProfiles`
- `caskctl`: CLI client for creating, listing, connecting to, and deleting sessions
- kind-based local integration testing
- strict model/API key non-exposure rules

## Read order for implementation agents

1. `AGENTS.md`
2. `PRD.md`
3. `docs/ARCHITECTURE.md`
4. `docs/API_SPEC.md`
5. `docs/CRD_SPEC.md`
6. `docs/SECURITY_MODEL.md`
7. `docs/IMPLEMENTATION_PLAN.md`
8. `docs/TEST_PLAN.md`
9. `prompts/OPENCODE_MVP_TASK.md`

## MVP scope

The MVP intentionally excludes:

- Web portal UI
- multi-cluster scheduling
- billing/chargeback
- Vault/SPIFFE/ExternalSecrets integration
- full model gateway productization
- production-grade audit log pipeline
- real Kata validation inside kind

The MVP must still include a secure path for model access: real model/API keys must never be placed in user-facing CRDs, API responses, Agent Pods, terminal output, or session logs.
