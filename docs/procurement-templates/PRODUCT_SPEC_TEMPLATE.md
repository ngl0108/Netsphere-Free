# NetSphere Product Specification Draft

## 1. Document control

- Product name:
- Edition:
- Version:
- Draft date:
- Target customer / bid:
- Author / owner:

## 2. Product overview

### 2.1 Product summary

Describe NetSphere in one short paragraph as an operational network management and hybrid operations platform.

### 2.2 Delivery model

- on-premises package
- customer-managed runtime
- optional Free collector + centralized intake structure

### 2.3 Intended deployment target

- public institution
- enterprise data center
- branch / campus
- hybrid on-prem + cloud operations

## 3. Runtime role layout

### 3.1 Production role

- `pro-server`
  - main NMS, topology, approval, observability, cloud operations

### 3.2 Intake role

- `preview-intake`
  - centralized receiver for sanitized Free contribution bundles
  - no direct device access

### 3.3 Validation / collector role

- `preview-collector-local`
  - same-PC validation harness before Windows Free collector release
- Windows Free collector
  - customer-side installed collector runtime

## 4. Core capability scope

### 4.1 Discovery

- auto discovery
- seed-based discovery
- inventory population
- hint-driven fallback identification

### 4.2 Topology

- L2 / L3 / hybrid topology rendering
- cloud node rendering
- operator layout editing
- impact-mode filtering

### 4.3 Connected NMS

- device inventory
- device detail
- diagnosis
- notifications
- observability entry points

### 4.4 Change and control

- approval workflow
- rollback path
- evidence package
- cloud intent preview and impact review

### 4.5 Free masked contribution flow

- allowlisted read-only collection
- local sanitize preview
- opt-in upload only
- centralized intake delivery

## 5. Functional detail by domain

### 5.1 Network operations

- daily monitoring
- issue review
- topology-assisted drilldown

### 5.2 Cloud operations

- account onboarding
- validate / pipeline / scan
- change preview
- approval-gated change path

### 5.3 Security and compliance

- role-based access
- audit trail
- masked contribution control
- approval and evidence retention

## 6. User and role model

| Role | Primary responsibility | Typical access |
| --- | --- | --- |
| Viewer | inspection and evidence review | read-only paths |
| Operator | operational execution and approval review | guarded operational paths |
| Administrator | policy, credential, and runtime ownership | privileged configuration and approval policy ownership |

## 7. Deployment prerequisites

### 7.1 Infrastructure prerequisites

- supported operating system:
- container runtime:
- database/runtime prerequisites:
- storage prerequisites:

### 7.2 Network prerequisites

- internal operator access
- cloud API access if cloud features are used
- intake upload path if Free contribution is enabled

### 7.3 External dependency notes

- no mandatory vendor cloud dependency for the Pro core runtime
- optional cloud provider APIs
- optional centralized intake exposure for Free upload

## 8. Interfaces and integrations

- product UI
- REST API
- observability proxy endpoints
- cloud provider APIs
- northbound / webhook / external integration endpoints

## 9. Operational boundaries

### 9.1 Supported actions

- read-only discovery paths
- approval workflow
- guarded cloud preview and execution path
- evidence and audit retrieval

### 9.2 Approval-gated paths

- cloud change execution
- rollback-controlled flows
- privileged settings ownership

### 9.3 Explicit restrictions

- unsupported third-party runtime changes
- blocked Free edition feature surfaces
- raw secret upload exclusion

## 10. Data handling summary

- local-only data before sanitize preview
- masked bundle only for Free contribution upload
- intake stores sanitized contributions, not raw credentials
- role-specific backup boundaries

Reference:

- `RUNTIME_DATA_BOUNDARIES.md`
- `DATA_HANDLING_TEMPLATE.md`

## 11. Deliverables

- software package / container deployment bundle
- role-specific deploy scripts
- operator runbook
- installation / upgrade / recovery runbook
- validation checklist
- customer-facing product summary

## 12. Validation and acceptance

- role env validation
- role smoke validation
- collector-local Free contribution validation
- release-check report artifacts

## 13. Version and patch policy

- release type:
- patch cadence:
- compatibility statement:
- upgrade path:
- rollback expectation:

## 14. Customer-supplied fields to complete later

The following should be filled outside the repo when preparing the final procurement package:

- customer/bid name
- commercial license scope
- delivery quantity
- maintenance pricing
- company legal information
- formal support contacts
