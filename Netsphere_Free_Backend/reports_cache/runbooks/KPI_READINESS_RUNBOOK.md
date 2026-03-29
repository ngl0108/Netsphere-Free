# KPI Readiness Runbook

This runbook verifies whether the 90-day plan KPI gates are met using measured data.

## Endpoint

- `GET /api/v1/ops/kpi/readiness`
- `POST /api/v1/ops/kpi/readiness/snapshot` (manual snapshot persist)
- `GET /api/v1/ops/kpi/readiness/history` (30-day trend evidence)

## What it evaluates

- Plug & Scan:
  - first map `P50` / `P95`
  - auto reflection rate
  - false positive rate
- Change engine:
  - success/failure rate
  - rollback `P95`
  - approval trace coverage
- Autonomy:
  - auto action rate
  - operator intervention rate
  - optional MTTD/MTTR improvement vs baseline
- Northbound:
  - delivery success rate
  - attempts `P95`
  - failed deliveries (24h)

## Example

```bash
curl -s "http://localhost:8000/api/v1/ops/kpi/readiness?discovery_days=30&autonomy_mttd_baseline_seconds=300&autonomy_mttr_baseline_seconds=180" \
  -H "Authorization: Bearer <token>"
```

## Strong evidence mode (sample minimums)

Use sample minimum gates when you want to prove KPI targets with enough measured volume.

```bash
curl -s "http://localhost:8000/api/v1/ops/kpi/readiness?discovery_days=30&require_sample_minimums=true&sample_min_discovery_jobs=10&sample_min_change_events=50&sample_min_northbound_deliveries=20&sample_min_autonomy_issues_created=10&sample_min_autonomy_actions_executed=10" \
  -H "Authorization: Bearer <token>"
```

When `require_sample_minimums=true`, readiness fails if sample totals are below thresholds even when KPI values look good.

Default strong-evidence sample minimums used by snapshot/report automation:

- discovery jobs: `30`
- change events: `60`
- northbound deliveries: `500`
- autonomy issues created: `20`
- autonomy actions executed: `20`

## Export evidence report (JSON + Markdown)

```bash
python Netsphere_Free_Backend/tools/export_kpi_readiness_report.py \
  --base-url http://localhost:8000 \
  --token "<token>" \
  --discovery-days 30 \
  --require-sample-minimums \
  --sample-min-discovery-jobs 10 \
  --sample-min-change-events 50 \
  --sample-min-northbound-deliveries 20 \
  --sample-min-autonomy-issues-created 10 \
  --sample-min-autonomy-actions-executed 10 \
  --latest-json-path docs/reports/kpi-readiness-30d-latest.json \
  --latest-md-path docs/reports/kpi-readiness-30d-latest.md \
  --fail-on-unhealthy
```

## Persist snapshots (manual + scheduled)

Manual snapshot:

```bash
curl -X POST "http://localhost:8000/api/v1/ops/kpi/readiness/snapshot?require_sample_minimums=true" \
  -H "Authorization: Bearer <admin-token>"
```

30-day history:

```bash
curl -s "http://localhost:8000/api/v1/ops/kpi/readiness/history?days=30&limit=90" \
  -H "Authorization: Bearer <token>"
```

Daily Celery snapshot is enabled by default (`04:15`):

- `ops_kpi_snapshot_enabled=true`
- `ops_kpi_snapshot_require_sample_minimums=true`
- `ops_kpi_snapshot_site_id=` (empty means global)
- `ops_kpi_snapshot_discovery_days=30`
- `ops_kpi_snapshot_discovery_limit=300`
- `ops_kpi_snapshot_sample_min_discovery_jobs=30`
- `ops_kpi_snapshot_sample_min_change_events=60`
- `ops_kpi_snapshot_sample_min_northbound_deliveries=500`
- `ops_kpi_snapshot_sample_min_autonomy_issues_created=20`
- `ops_kpi_snapshot_sample_min_autonomy_actions_executed=20`

History output now includes:

- snapshot coverage across the requested day range
- latest vs previous snapshot delta
- top failing checks across stored snapshots
- latest snapshot sample coverage ratios

## Result interpretation

- `readiness.status=healthy`: required checks all pass.
- `readiness.status=warning|critical`: one or more required checks fail.
- `readiness.status=insufficient_data`: no hard fail but required checks contain unknown metrics.

## Operational note

Set realistic baselines for `autonomy_mttd_baseline_seconds` / `autonomy_mttr_baseline_seconds` when evaluating improvement goals.
