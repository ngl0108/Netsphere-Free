# Procurement Draft Templates

These templates are the repo-side starting point for B2G, customer delivery, and procurement packaging.

Use them as editable drafts before company-specific details, commercial terms, and formal evidence are attached.

Included templates:

- `PRODUCT_SPEC_TEMPLATE.md`
  - product specification draft
- `OPERATIONS_OVERVIEW_TEMPLATE.md`
  - deployment and runtime operations overview
- `MAINTENANCE_SUPPORT_TEMPLATE.md`
  - maintenance and support scope draft
- `SECURITY_ARCHITECTURE_TEMPLATE.md`
  - security structure and control explanation draft
- `DATA_HANDLING_TEMPLATE.md`
  - data collection, masking, storage, and retention explanation draft
- `DELIVERY_PACKAGE_CHECKLIST.md`
  - repo-side checklist for assembling the technical delivery package

Recommended usage:

1. Start from the current product/runtime facts in `Netsphere_Free_Deploy/README.md`, `ROLE_ENV_CHECKLIST.md`, and `RUNTIME_DATA_BOUNDARIES.md`.
2. Fill company-owned fields later outside the repo if they contain commercial or procurement-only details.
3. Keep the technical structure here aligned with the actual product and deployment behavior.

## What this folder is for

Use these templates when you need to turn the current product state into customer-facing or procurement-facing drafts without rewriting the technical baseline each time.

These templates are intended to capture:

- runtime role structure
- operational boundaries
- security and data handling structure
- maintenance and support scope
- product specification language

## What should stay outside the repo

Add the following later in your private working documents or the final proposal package:

- company legal information
- pricing and commercial terms
- customer name and bid number
- SLA commitments
- support contact details
- formal certification references

## Suggested fill order

1. `PRODUCT_SPEC_TEMPLATE.md`
2. `OPERATIONS_OVERVIEW_TEMPLATE.md`
3. `SECURITY_ARCHITECTURE_TEMPLATE.md`
4. `DATA_HANDLING_TEMPLATE.md`
5. `MAINTENANCE_SUPPORT_TEMPLATE.md`
6. `DELIVERY_PACKAGE_CHECKLIST.md`

## Repo-side source references

Use these repo documents as the factual source of truth while filling the drafts:

- `Netsphere_Free_Deploy/README.md`
- `INSTALL_UPGRADE_RECOVERY_RUNBOOK.md`
- `ROLE_ENV_CHECKLIST.md`
- `RUNTIME_DATA_BOUNDARIES.md`
- `PREVIEW_CONTRIBUTOR_GUIDE.md`
- `PRO_BASELINE_RUNBOOK.md`
