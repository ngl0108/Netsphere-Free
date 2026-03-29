# Release Gate Runbook

## Purpose
Lock release quality by requiring one final CI check (`Release Gate`) before merge/release.

## Workflow
- File: `.github/workflows/ci-release-gate.yml`
- Required jobs:
  - `Secret Scan`
  - `Dependency Lock Integrity`
  - `SBOM Generate`
  - `Backend Security Scan`
  - `Backend Operational Tests`
  - `Frontend Build`
  - `Frontend Security Scan`
  - `Frontend Ops E2E`
- Final gate:
  - `Release Gate` fails if any required job is not `success`.

## Branch Protection (GitHub)
Set branch protection for `main` and require status check:
- `Release Gate`

This ensures merge is blocked when any mandatory API/build/E2E/security check fails.

## Deployment policy

- No direct deployment from non-tag commits.
- Release/deploy job must depend on successful `Release Gate`.
- If `Release Gate` fails, deployment is blocked by policy (no manual bypass for normal flow).

Validation helper:

```bash
python Netsphere_Free_Backend/tools/verify_branch_protection.py \
  --repo <owner>/<repo> \
  --branch main \
  --required-check "Release Gate" \
  --require-strict \
  --require-admin-enforced
```

## Local Verification
```bash
cd Netsphere_Free_Frontend
npm run contract:api
npm run i18n:audit:strict
npm run build
npm run e2e:ops
```

## Packaging operator handoff docs

```bash
python Netsphere_Free_Backend/tools/package_runbooks.py
```
