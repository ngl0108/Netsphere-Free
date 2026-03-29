# Synthetic Validation Playbook (No Real Device Data)

This playbook runs deterministic validation using only synthetic fixtures.

## 1) Generate fixture baseline

```bash
python Netsphere_Free_Backend/tools/generate_synthetic_fixtures.py --seed 20260219
```

Output goes to `test-data/synthetic/`.

## 2) Validate digital twin adapters

```bash
cd Netsphere_Free_Backend
python -m pytest tests/synthetic/test_digital_twin_mock_adapter.py -q
```

Cases covered per vendor:
- `normal`
- `timeout`
- `partial`
- `malformed`

Protocols covered:
- SNMP
- SSH
- gNMI

## 3) Run contract gate

```bash
cd Netsphere_Free_Backend
python tools/run_contract_gate.py
```

This executes:
- backend OpenAPI snapshot contract
- frontend API contract (`services.js` vs OpenAPI snapshot)

## 3.5) Run vendor parser benchmark (no real device required)

```bash
cd Netsphere_Free_Backend
python tools/run_vendor_parser_benchmark.py
```

This replays deterministic vendor CLI fixtures from `test-data/vendor-fixtures/` and
produces a report at:

`docs/reports/vendor-parser-benchmark.latest.json`

Covered fixture categories:
- inventory parser replay
- neighbor parser replay
- driver facts replay (including domestic vendor drivers)
- parser robustness variants (whitespace/column drift/missing fields)

Domestic switch focused benchmark:

```bash
cd Netsphere_Free_Backend
python tools/run_vendor_parser_benchmark.py --group domestic_switch
```

Global switch focused benchmark:

```bash
cd Netsphere_Free_Backend
python tools/run_vendor_parser_benchmark.py --group global_switch
```

Variant-only replay smoke (CI fixed):

```bash
cd Netsphere_Free_Backend
python -m pytest tests/synthetic/test_vendor_parser_replay_variants.py -q
```

Export vendor support matrix (JSON + Markdown):

```bash
cd Netsphere_Free_Backend
python tools/export_vendor_support_matrix.py
```

Outputs:
- `docs/reports/vendor-support-matrix.latest.json`
- `docs/reports/vendor-support-matrix.latest.md`

API access (for UI/ops checks):

`GET /api/v1/settings/vendor-support-matrix?refresh=true`

Generate baseline fixtures for all supported device types:

```bash
cd Netsphere_Free_Backend
python tools/generate_vendor_baseline_fixtures.py
```

This fills missing vendor coverage using deterministic generic facts fixtures.

Support policy + parser quality unit checks:

```bash
cd Netsphere_Free_Backend
python -m pytest tests/test_device_support_policy_service.py tests/test_parser_quality_service.py tests/test_pre_check_template_resolution.py -q
```

## 4) Run frontend operational E2E (synthetic included)

```bash
cd Netsphere_Free_Frontend
npm.cmd run e2e:ops
```

Includes synthetic resilience scenarios:
- 403 failure -> retry -> success
- rollback action from visual config history

## 5) Run deterministic fuzzer

```bash
cd Netsphere_Free_Backend
python -m pytest tests/synthetic/test_capability_profile_fuzz.py -q
```

Focus:
- malformed/garbled policy payloads
- normalization stability and invariant checks

## 6) Run validation matrix

```bash
cd Netsphere_Free_Backend
python tools/run_synthetic_validation_matrix.py --profile ci --fail-on-unhealthy
```

Outputs:
- `docs/reports/synthetic-validation-matrix.latest.json`
- `docs/reports/synthetic-validation-matrix.latest.md`

Profiles:
- `ci`: short smoke for release gate and prebuild checks
- `local`: broader local soak profile across all synthetic scenarios
- `release`: longer soak profile for pre-release sign-off

Optional scenario override:

```bash
python tools/run_synthetic_validation_matrix.py --profile ci --scenarios failure,large_scale --duration-scale 0.5
```

Expanded fixture scenarios now include:
- `rollback_wave`
- `hybrid_cloud`
- `wireless_edge`

Digital twin vendor styles now include:
- `cisco`, `arista`, `juniper`
- `fortinet`, `paloalto`, `f5`
- `nokia`, `vyos`, `mikrotik`

The matrix checks:
- synthetic fixture manifest integrity
- required synthetic scenario coverage, expanded focus areas, and scale floors
- digital twin vendor breadth and protocol/case consistency
- soak stability across the selected scenarios
- EVE-NG vendor plan coverage and evidence checklist

## 7) Run soak simulation

```bash
cd Netsphere_Free_Backend
python tools/run_synthetic_soak.py --scenario failure --duration-sec 60 --tick-ms 100 --fail-on-unhealthy
```

Available soak scenarios:
- `normal`
- `failure`
- `security_incident`
- `rollback_wave`
- `hybrid_cloud`
- `wireless_edge`
- `large_scale`

CI smoke profile:

```bash
python tools/run_synthetic_soak.py --scenario failure --duration-sec 5 --tick-ms 10 --fail-on-unhealthy
```

## One-command local gate

```bash
cd Netsphere_Free_Backend
python tools/run_local_quality_gate.py --skip-e2e
```

Remove `--skip-e2e` for full pre-release run.

Use a heavier synthetic profile when needed:

```bash
python tools/run_local_quality_gate.py --synthetic-profile local --skip-e2e
```

## Build flow integration (recommended)

`npm.cmd run build` now includes an automatic prebuild gate.

```bash
cd Netsphere_Free_Frontend
npm.cmd run build
```

The prebuild hook runs:
1. local quality gate (`--skip-e2e --skip-build`)
2. then Vite build

If Python/backend gate script is not present (for isolated frontend build contexts),
the prebuild gate is skipped safely.

For full release gate (includes E2E), run:

```bash
cd Netsphere_Free_Frontend
npm.cmd run build:release
npm.cmd run build
```

Repo root Windows shortcuts:

```bash
build_guarded.bat
build_release_guarded.bat
```

If your shell environment reports `spawn EPERM` from repo root wrappers, run the
same commands directly from `Netsphere_Free_Frontend` instead.
