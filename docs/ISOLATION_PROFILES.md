# Isolation Profiles

## 1. Purpose

`isolationProfiles` give users a stable, product-level isolation choice while keeping Kubernetes runtime details internal.

User-facing:

```yaml
isolation:
  profile: kata
```

Internal Pod result:

```yaml
spec:
  runtimeClassName: kata
```

## 2. MVP profiles

Required profiles:

```text
default
kata
```

Optional future profile:

```text
gvisor
```

## 3. Config structure

Example controller config:

```yaml
isolationProfiles:
  default:
    runtimeClassName: ""
    nodeSelector: {}
    tolerations: []
  kata:
    runtimeClassName: kata
    nodeSelector:
      agentcask.aidev.samsungds.net/kata: "true"
    tolerations:
      - key: agentcask.aidev.samsungds.net/kata
        operator: Equal
        value: "true"
        effect: NoSchedule
```

## 4. Profile behavior

### default

The controller omits:

```yaml
spec.runtimeClassName
```

The Pod uses the cluster default runtime, typically runc.

### kata

The controller sets:

```yaml
spec.runtimeClassName: kata
```

and applies configured node selectors/tolerations.

## 5. RuntimeClass validation

Before creating a Pod for a non-default profile, the controller should check:

```text
RuntimeClass/<runtimeClassName>
```

If it is missing:

```yaml
status:
  phase: Failed
  reason: RuntimeClassNotFound
```

## 6. kind testing note

kind usually does not provide real Kata isolation.

For local plumbing tests, a fake RuntimeClass may be created with name `kata` and a handler available in the kind node, or the kata-specific running Pod test may be skipped unless a real runtime is available.

Example for plumbing only:

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: kata
handler: runc
```

This validates that the controller maps `isolation.profile=kata` into `runtimeClassName: kata`. It does not validate VM isolation.

Real Kata validation must run on a cluster with Kata Containers installed and working.
