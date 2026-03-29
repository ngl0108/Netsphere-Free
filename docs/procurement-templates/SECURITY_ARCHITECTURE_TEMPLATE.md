# NetSphere Security Architecture Draft

## 1. Security model summary

- runtime separation by role
- role-based access
- approval-gated operational changes
- audit and evidence retention
- masked Free contribution policy

## 2. Runtime role boundaries

### 2.1 Pro operational boundary

- owns operational control
- owns approvals, observability, evidence, and cloud control paths

### 2.2 Intake data boundary

- receives sanitized Free contribution bundles only
- does not require direct customer device access

### 2.3 Collector boundary

- local discovery and local sanitize preview
- raw output remains local until the operator explicitly approves upload

## 3. Authentication and authorization

### 3.1 Authentication

- initial administrator bootstrap
- authenticated UI/API access
- optional MFA / OTP controls where enabled

### 3.2 Authorization

- Viewer
- Operator
- Administrator

State clearly which pages and actions are:

- read-only
- operator-enabled
- administrator-owned

## 4. Data protection

### 4.1 Secrets handling

- role env files stored outside version control
- secret and encryption values supplied per environment
- privileged secret settings restricted to administrator ownership

### 4.2 Contribution data handling

- allowlisted read-only commands only
- local sanitize preview before upload
- masked bundle only
- remote intake receives sanitized content rather than raw credentials

### 4.3 Stored data categories

- Pro operational state
- intake registration and sanitized contribution state
- disposable collector-local validation state

## 5. Network exposure

### 5.1 Pro endpoints

- main product UI/API
- observability proxy paths

### 5.2 Intake endpoints

- collector registration
- sanitized upload endpoint

### 5.3 Collector endpoints

- local-only validation endpoint
- installed Free collector local UI/runtime endpoint

## 6. Logging, audit, and evidence

- audit log coverage for privileged changes
- approval and rollback evidence trail
- operator package and support bundle outputs
- deployment and destructive action review path

## 7. Security controls

- read-only vs change-enabled guardrails
- approval requirements before execution
- cloud execution readiness controls
- role banners and ownership boundaries in UI
- runtime role separation in deployment

## 8. Backup and recovery security notes

- backed-up roles:
  - Pro
  - intake
- non-routine backup:
  - collector-local validation state
- restore only to approved target environments

## 9. Incident response inputs

When preparing the final customer package, define:

- incident intake path
- required evidence
- privileged log handling process
- notification and escalation rules

## 10. Company-supplied completion fields

Finalize outside the repo:

- formal security contact
- vulnerability disclosure path
- patch advisory policy
- external certification references
