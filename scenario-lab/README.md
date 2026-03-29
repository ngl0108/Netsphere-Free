# NetSphere Scenario Lab

Scenario Lab is a dedicated workspace for repeatable FREE and PRO validation without real hardware.

It includes:
- scenario manifests for branch, enterprise, datacenter, and hybrid topologies
- seeding scripts for PRO and FREE runtimes
- shared smoke and contribution validation runners
- live Playwright E2E checks against seeded scenario accounts

## Layout

- `scenarios/free/`
  - FREE scenario manifests
- `scenarios/pro/`
  - PRO scenario manifests
- `reports/`
  - latest seeding, suite, and E2E summaries
- `seed-free-scenario.ps1`
  - seed a FREE scenario into `collector-local`
- `seed-pro-scenario.ps1`
  - seed a PRO scenario into the PRO backend
- `seed-all-scenarios.ps1`
  - seed every FREE and/or PRO scenario in one pass
- `sync-scenario-runtime.ps1`
  - rebuild runtime containers so scenario seeders use the latest local backend code
- `run-scenario-suite.ps1`
  - seed representative FREE and PRO scenarios, then run smoke and contribution validation
- `run-scenario-e2e.ps1`
  - run live Playwright scenario login and verification against PRO and FREE
- `run-functional-audit.ps1`
  - run the official live functionality audit against seeded PRO and FREE runtimes
- `FUNCTIONAL-AUDIT.md`
  - explains which routes and actions the functional audit covers

## Seeded Accounts

Each scenario creates dedicated lab users with the `lab_<scenario>_...` prefix so they do not collide with your normal runtime accounts.

- default password: `Password1!!@`

## Included Scenarios

FREE:
- `free-branch-poc`
- `free-enterprise-visibility`
- `free-hybrid-visibility`

PRO:
- `pro-branch-operations`
- `pro-enterprise-operations`
- `pro-datacenter-fabric`
- `pro-hybrid-operations`

## Common Commands

Seed one PRO scenario:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\seed-pro-scenario.ps1 -Scenario pro-enterprise-operations
```

Seed one FREE scenario:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\seed-free-scenario.ps1 -Scenario free-hybrid-visibility
```

Run the shared scenario suite:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-scenario-suite.ps1
```

Sync runtimes before seeding or E2E after backend code changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\sync-scenario-runtime.ps1 -Target all
```

Seed every scenario:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\seed-all-scenarios.ps1 -Target all
```

Run live scenario E2E:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-scenario-e2e.ps1
```

Run the representative functional audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\scenario-lab\run-functional-audit.ps1
```

This runner covers:
- PRO route matrix
- PRO representative button/action audit
- PRO scenario-lab action flow audit
- FREE route matrix
- FREE representative policy/block/audit-state checks
- FREE scenario-lab action flow audit

## Result Files

- `scenario-lab/reports/pro-*.latest.json`
- `scenario-lab/reports/free-*.latest.json`
- `scenario-lab/reports/scenario-suite.latest.json`
- `scenario-lab/reports/scenario-e2e.latest.json`
- `scenario-lab/reports/functional-audit.latest.json`

## Notes

- The seeder only cleans up data that it created for the same scenario slug.
- Existing non-lab accounts and real runtime data are left alone.
- Re-seeding the same scenario is supported and is part of the intended workflow.
- If you changed backend scenario seeding logic, run `sync-scenario-runtime.ps1` before re-seeding so the running containers pick up the latest code.
