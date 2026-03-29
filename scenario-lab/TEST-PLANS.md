# Scenario Lab Test Plans

This workspace keeps repeatable scenario manifests and seeding scripts for large-scale validation without real hardware.

## Free Plans

### `free-branch-poc`
- Goal: prove Free discovery, topology, and 50-node managed policy in a small branch footprint.
- Validate:
  - first-run wizard and locked contribution policy
  - discovery and topology visibility
  - managed vs discovered-only behavior
  - sanitized upload and intake storage

### `free-enterprise-visibility`
- Goal: validate HQ plus branches inventory visibility with Free node caps.
- Validate:
  - site hierarchy
  - managed slot allocation
  - device detail and topology legend
  - audit-safe contribution flow

### `free-hybrid-visibility`
- Goal: validate Free visibility across on-prem and cloud without full operations scope.
- Validate:
  - cloud account/resource visibility
  - hybrid service groups
  - discovered-only behavior on larger estates
  - contribution policy and collector-local upload path

## Pro Plans

### `pro-branch-operations`
- Goal: validate branch operations workflows end to end.
- Validate:
  - actions, notifications, approvals, reports
  - preventive checks
  - state history

### `pro-enterprise-operations`
- Goal: validate enterprise campus operations with service groups and SoT coverage.
- Validate:
  - monitoring profile assignment
  - source of truth summary
  - service impact and operations review bundle

### `pro-datacenter-fabric`
- Goal: validate spine-leaf data center topology and continuity workflows.
- Validate:
  - datacenter topology richness
  - service group health
  - approval and evidence context

### `pro-hybrid-operations`
- Goal: validate the full hybrid platform story.
- Validate:
  - intent templates
  - pre-check and before/after compare
  - service impact across on-prem and cloud
  - state history and operations review bundle

## Recommended Repeatable Runs

### Free
```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\seed-free-scenario.ps1 -Scenario free-enterprise-visibility
```

### Pro
```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\seed-pro-scenario.ps1 -Scenario pro-enterprise-operations
```

### Full suite
```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-scenario-suite.ps1
```

### Live scenario E2E
```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-scenario-e2e.ps1
```

### Live scenario E2E by target
```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-scenario-e2e.ps1 -Target pro
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-scenario-e2e.ps1 -Target free
```
