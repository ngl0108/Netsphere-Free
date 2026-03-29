# NetSphere Delivery Package Checklist

## Purpose

Use this checklist when you are turning the repo-side technical drafts into a customer delivery or procurement package.

This file is still repo-side and should remain technical. Add customer-specific commercial or legal content outside the repo.

## 1. Product baseline

- product name and edition confirmed
- release version confirmed
- delivery scope confirmed
- runtime roles confirmed
  - `pro-server`
  - `preview-intake`
  - `preview-collector-local` validation path

## 2. Technical draft set

- `PRODUCT_SPEC_TEMPLATE.md`
- `OPERATIONS_OVERVIEW_TEMPLATE.md`
- `SECURITY_ARCHITECTURE_TEMPLATE.md`
- `DATA_HANDLING_TEMPLATE.md`
- `MAINTENANCE_SUPPORT_TEMPLATE.md`

## 3. Runtime and operations references

- `Netsphere_Free_Deploy/README.md`
- `ROLE_ENV_CHECKLIST.md`
- `RUNTIME_DATA_BOUNDARIES.md`
- `INSTALL_UPGRADE_RECOVERY_RUNBOOK.md`

## 4. Validation artifacts

- latest role smoke result
- latest `release-check` result
- collector-local contribution validation result
- operator package or support bundle when required

## 5. To complete outside the repo

- customer name and bid number
- pricing and commercial scope
- maintenance/SLA commitments
- named support contacts
- company legal and certification references

## 6. Final package rule

Do not let the technical baseline in the customer package diverge from the actual product behavior, runtime role layout, or validation process described in this repository.
