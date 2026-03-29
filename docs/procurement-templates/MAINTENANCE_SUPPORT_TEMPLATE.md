# NetSphere Maintenance and Support Draft

## 1. Support scope

### 1.1 Included scope

- installation support
- upgrade support
- runtime troubleshooting
- audit/evidence review support
- guided rollback and recovery support
- collector-local validation guidance before Free release packaging

### 1.2 Covered runtime roles

- `pro-server`
- `preview-intake`
- `preview-collector-local` for validation only

## 2. Incident classes

| Class | Example | Typical severity |
| --- | --- | --- |
| Service unavailable | Pro UI/API not reachable | High |
| Partial degradation | topology, approval, or observability partially degraded | Medium |
| Intake upload failure | Free contribution registration/upload path failing | Medium |
| Upgrade failure | post-upgrade regression or failed restart | High |
| Approval or rollback issue | guarded change flow not working as expected | High |
| Validation failure | collector-local validation path fails before release | Medium |

## 3. Response model

Fill later with company-specific SLA values:

- initial response target:
- workaround target:
- service restoration target:
- formal escalation target:

## 4. Customer cooperation prerequisites

- relevant role logs
- screenshots or screen recording for UI regressions
- release-check report artifacts if available
- support bundle and operator package when requested
- current version, role, and environment summary

## 5. Standard support workflow

1. confirm affected runtime role
2. confirm recent version or config change
3. collect smoke and role health evidence
4. collect targeted logs and bundles
5. decide workaround, rollback, or hotfix path
6. record root cause and prevention action

## 6. Exclusions

- unsupported third-party runtime modifications
- custom code changes outside the agreed delivery scope
- infrastructure components not covered by the agreed deployment architecture
- customer-side policy deviations that bypass the documented role structure

## 7. Maintenance windows

### 7.1 Planned maintenance

- notice lead time:
- expected operator actions:
- expected post-maintenance validation:

### 7.2 Emergency maintenance

- emergency trigger:
- communication path:
- recovery-first principle:

## 8. Patch communication

- security patch notice:
- functional patch notice:
- upgrade notes delivery:
- rollback advisory when relevant:

## 9. Customer-facing deliverables during support

- incident acknowledgement
- workaround or rollback instruction
- recovery confirmation
- final incident summary

## 10. Company-supplied completion fields

These should be finalized outside the repo:

- named support contact
- response SLA
- maintenance hours
- escalation chain
- warranty / maintenance term
