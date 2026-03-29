# NetSphere Functional Audit

This audit layer sits on top of Scenario Lab.

Scenario Lab answers:
- can FREE and PRO seed realistic lab data
- can representative operators log in
- do core discovery, topology, service, approval, and contribution flows stay alive

Functional Audit answers:
- do high-value routes open without redirect or crash
- do key buttons react correctly
- do empty or blocked states render the right message
- do FREE and PRO product-policy boundaries behave consistently

## Representative scenarios

- FREE: `free-enterprise-visibility`
- PRO: `pro-hybrid-operations`

These two scenarios were chosen because they exercise the broadest set of seeded assets while keeping audit runtime practical.

## Coverage matrix

### PRO route and action audit

- `/sites`
  - page loads
  - refresh and add-site surface visible
- `/logs`
  - search input works
  - empty-result state renders
- `/audit`
  - audit page loads
- `/wireless`
  - wireless page loads
- `/settings`
  - major tabs can be switched
  - save action returns success
- `/users`
  - add-user modal opens
- `/monitoring-profiles`
  - new-profile action works
  - required-field validation message renders
- `/discovery`
  - input validation works
  - live scan start request succeeds
  - progress panel renders
  - `View Results` opens the results panel and results table
- `/config`
  - merge snippet modal opens/closes
  - deploy modal opens/closes
  - live dry-run request succeeds or returns a handled warning/error state
  - change plan and rollback metadata render
- `/source-of-truth`
  - quick action opens state history
- `/state-history`
  - capture snapshot action works
- `/service-groups`
  - open-topology action works
- `/operations-reports`
  - review bundle download starts
  - operator package, release bundle, and compliance export download start
  - dashboard and notifications drilldown buttons work
  - open-approval action works
  - empty-state matrix renders cleanly
  - handled load error toast renders
  - handled bundle download error toast renders
- `/observability`
  - PRO operations panel visible
  - admin observability toggle visible
  - open-settings action works
- `/automation`
  - PRO automation panel visible
  - open-approval action works
- `/diagnosis`
  - evidence panel visible
- `/intent-templates`
  - use-template action works
  - cloud intent prefill, pre-check, and before/after compare are visible
- `/approval`
  - cloud pre-check, before/after compare, guardrails, and execution continuity render
  - device, topology, observability, topology-impact, and state-history drilldowns work
  - capture-state-history action records a new snapshot

### FREE route and policy audit

- allowed surfaces load without redirect or policy block
  - `/`
  - `/devices`
  - `/sites`
  - `/topology`
  - `/diagnosis`
  - `/notifications`
  - `/wireless`
  - `/discovery`
  - `/automation`
  - `/observability`
  - `/logs`
  - `/audit`
  - `/edition/compare`
  - `/preview/contribute`
- automation hub shows FREE experience panel
- observability admin toggle is hidden
- data-contribution navigation is hidden
- logs page empty-result state renders
- `/discovery`
  - input validation works
  - live scan start request succeeds
  - progress panel renders
  - `View Results` opens the results panel and results table
- `/preview/contribute`
  - administrator audit wording is visible
  - locked installation policy is visible
  - sanitized record detail opens
- blocked surfaces render policy-blocked state
  - `/config`
  - `/images`
  - `/visual-config`
  - `/policy`
  - `/ztp`
  - `/fabric`
  - `/compliance`
  - `/settings`
  - `/cloud/accounts`
  - `/cloud/intents`
  - `/preventive-checks`
  - `/monitoring-profiles`
  - `/source-of-truth`
  - `/state-history`
  - `/intent-templates`
  - `/service-groups`
  - `/operations-reports`
  - `/users`
  - `/approval`

## How to run

Sync runtime and reseed if backend or frontend behavior changed:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\sync-scenario-runtime.ps1 -Target all
powershell -ExecutionPolicy Bypass -File .\scenario-lab\seed-pro-scenario.ps1 -Scenario pro-hybrid-operations
powershell -ExecutionPolicy Bypass -File .\scenario-lab\seed-free-scenario.ps1 -Scenario free-enterprise-visibility
```

Run the functional audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-functional-audit.ps1
```

This live audit runner executes:
- `functional-route-matrix-pro.spec.js`
- `functional-audit-pro.spec.js`
- `scenario-lab-pro-actions.spec.js`
- `config-template-deploy-guard.spec.js`
- `compliance-report-automation.spec.js`
- `operations-reports-states.spec.js`
- `functional-route-matrix-free.spec.js`
- `functional-audit-free.spec.js`
- `scenario-lab-free-actions.spec.js`
- `free-intake-contribution.spec.js`
- `free-route-guard.spec.js`

It uses the real runtimes directly:
- PRO: `http://localhost`
- FREE collector-local: `http://127.0.0.1:18080`

## Notes

- This audit is not a replacement for scenario-wide matrix E2E.
- This audit intentionally targets representative routes and actions rather than every possible button in the product.
- If a new route is added, it should be listed here and either attached to this audit or explicitly covered elsewhere.
