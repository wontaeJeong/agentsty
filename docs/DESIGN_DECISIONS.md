# MVP Design Decisions

## Decision 1: CLI-first, no portal

The MVP provides `caskctl` and `cask-api`, not a Web portal.

Reason:

- faster MVP
- simpler UX for developer users
- avoids building frontend before core platform is validated

## Decision 2: cask-api includes terminal gateway

The MVP does not split terminal gateway into a separate service.

Reason:

- fewer deployable components
- simpler auth/session ownership checks
- easier local/kind testing

## Decision 3: Agent Pods are not exposed

No per-session Ingress by default.

Reason:

- reduces attack surface
- keeps user access through `cask-api`
- centralizes auth/audit/terminal connection policy

## Decision 4: isolationProfiles over runtimeClassName

Users select `isolation.profile`; controller maps it to runtime settings.

Reason:

- stable product API
- cluster-specific RuntimeClass names stay internal
- prevents arbitrary runtime selection

## Decision 5: model proxy pattern for API key safety

Only internal `cask-model-proxy` holds upstream model/API keys.

Reason:

- Agent Pods are untrusted
- terminal users can inspect environment/files
- real keys inside Pod would leak easily
- keeping the proxy internal lets `cask-api` remain the only externally exposed runtime component without also holding upstream credentials
