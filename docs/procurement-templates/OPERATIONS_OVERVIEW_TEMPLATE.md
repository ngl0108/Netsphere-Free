# NetSphere Operations Overview Draft

## 1. Runtime roles

### 1.1 Pro runtime

- role name: `pro-server`
- purpose: main operational runtime
- scope: NMS, topology, approval, cloud operations, observability

### 1.2 Intake runtime

- role name: `preview-intake`
- purpose: centralized receiver for sanitized Free contribution bundles
- scope: collector registration and masked bundle intake only

### 1.3 Collector validation runtime

- role name: `preview-collector-local`
- purpose: same-PC validation path for the Free collector workflow before Windows EXE release

## 2. Operator entry points

### 2.1 Pro server

- start:
- stop:
- logs:
- smoke:

### 2.2 Preview intake

- start:
- stop:
- logs:
- smoke:

### 2.3 Preview collector-local

- bootstrap:
- start:
- stop:
- logs:
- smoke:
- contribution flow validation:

## 3. Daily operator checks

### 3.1 Pro

- UI reachable
- API/docs reachable
- observability proxies reachable
- approval and notifications healthy

### 3.2 Intake

- bootstrap status reachable
- registration path healthy
- recent contribution persistence healthy

### 3.3 Collector validation

- bootstrap path healthy
- sanitize path healthy
- upload path succeeds against intake

## 4. Backup scope

### 4.1 Back up

- Pro database and configuration
- intake database and sanitized contribution storage
- role env files stored outside version control
- operator and support bundles that must be retained

### 4.2 Do not treat as routine backup targets

- collector-local disposable state
- transient Docker caches
- temporary smoke outputs unless needed for troubleshooting

## 5. Upgrade approach

### 5.1 Pre-upgrade checks

- env validation
- current runtime status
- backup completion
- previous approved version reference captured

### 5.2 Runtime rollout order

1. intake when intake schema or upload policy changed
2. Pro runtime
3. collector-local only when validating a new Free release

### 5.3 Post-upgrade validation

- role smoke checks
- release-check run
- collector-local contribution validation when Free packaging changed

## 6. Recovery approach

### 6.1 Pro runtime recovery

- restore database
- restore env and secrets
- restore license and evidence material
- validate core operations

### 6.2 Intake runtime recovery

- restore intake database
- restore sanitized contribution storage
- validate registration and upload path

### 6.3 Collector-local retest path

- rebuild local harness
- rerun contribution flow validation

## 7. Operational ownership

| Area | Typical owner | Notes |
| --- | --- | --- |
| Product administration | Customer admin / delivery team | settings, policy, credentials |
| Runtime operations | Infrastructure operator | start/stop/logs/health |
| Intake data handling | Intake operator / data custodian | sanitized bundle retention and access |
| Validation and signoff | Delivery / QA | smoke, release-check, collector-local validation |

## 8. Incident handling summary

- service unavailable
- degraded runtime
- intake upload failure
- collector validation failure
- approval or rollback regression

For each incident, define:

- initial response target
- workaround target
- service restoration target
- evidence to collect

## 9. Customer-provided completion fields

Fill these outside the repo in the final delivery package:

- named operating organization
- on-call contact path
- agreed maintenance window
- response and restoration SLA
