# NetSphere Data Handling Draft

## 1. Data handling scope

This document explains how NetSphere handles:

- operational runtime data
- discovery and topology data
- approval and evidence data
- Free masked contribution data

## 2. Role-by-role data boundaries

### 2.1 Pro server

Stored data examples:

- application database state
- topology and inventory state
- approval and evidence records
- observability references

Backup target:

- yes

### 2.2 Preview intake

Stored data examples:

- collector registration state
- sanitized contribution bundle metadata
- sanitized contribution bundle storage

Backup target:

- yes

### 2.3 Preview collector / Free collector

Local-only data examples:

- raw command output before sanitize preview
- local review state
- local bootstrap/runtime validation state

Routine backup target:

- no, unless troubleshooting requires preservation

## 3. Free contribution flow

### 3.1 Required control points

- opt-in required
- allowlisted read-only commands only
- local sanitize preview before upload
- per-bundle consent before upload
- masked bundle only

### 3.2 Delivery modes

- local only
- remote only
- dual write

### 3.3 Registration path

- collector self-registration
- registration state visibility in product UI
- upload only after registration and policy allow it

## 4. Explicit exclusions

NetSphere must clearly state that the following are not intended for Free contribution upload:

- full running or startup configurations
- secrets and credential material
- certificates and private keys
- blocked feature surfaces
- commands outside the allowlist

## 5. What stays local

- raw command output before sanitize preview
- device credentials and login secrets
- local review and per-bundle consent choice
- blocked command surfaces

## 6. What may be uploaded

- masked raw output after sanitize preview
- allowlisted read-only command results only
- optional operator notes that follow policy

## 7. What is never uploaded

- raw credentials
- private keys
- full forbidden configuration surfaces
- out-of-policy commands

## 8. Storage and retention

### 8.1 Pro

- retention policy:
- evidence retention:

### 8.2 Intake

- sanitized bundle retention policy:
- archive policy:
- deletion / purge policy:

### 8.3 Collector

- local cleanup policy:
- troubleshooting retention exception:

## 9. Transfer path

- local sanitize preview
- registration state check
- upload target resolution
- success/failure handling
- local-only vs remote-forwarded result explanation

## 10. Customer-facing explanation summary

Use this short explanation later in customer material:

- raw data is reviewed locally first
- only masked allowlisted output may be uploaded
- intake stores sanitized bundles rather than raw credentials
- upload remains optional and policy-controlled

## 11. Company-supplied completion fields

Finalize outside the repo:

- retention periods
- deletion request handling
- formal privacy contact
- contractual data handling clauses
