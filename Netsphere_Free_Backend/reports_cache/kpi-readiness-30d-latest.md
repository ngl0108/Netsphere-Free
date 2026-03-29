# KPI Readiness Evidence

- Generated (UTC): `2026-03-09 04:13:35`
- Readiness Status: `healthy`
- Required Checks: `18`
- Pass / Fail / Unknown: `18` / `0` / `0`

## Scope

- site_id: `-`
- discovery_days: `30`
- discovery_limit: `300`
- require_sample_minimums: `True`

## Query Params

- discovery_days: `30`
- discovery_limit: `300`
- require_sample_minimums: `True`
- sample_min_autonomy_actions_executed: `20`
- sample_min_autonomy_issues_created: `20`
- sample_min_change_events: `60`
- sample_min_discovery_jobs: `30`
- sample_min_northbound_deliveries: `500`

## Sample Evidence

| Metric | Observed | Threshold |
|---|---:|---:|
| `autonomy_actions_executed` | `20` | `20` |
| `autonomy_issues_created` | `20` | `20` |
| `change_events` | `100` | `60` |
| `discovery_jobs` | `30` | `30` |
| `northbound_deliveries` | `538` | `500` |

## Sample Coverage Ratios

| Metric | Observed | Threshold | Coverage % | Met |
|---|---:|---:|---:|---|
| `autonomy_actions_executed` | `20` | `20` | `100.00` | `True` |
| `autonomy_issues_created` | `20` | `20` | `100.00` | `True` |
| `change_events` | `100` | `60` | `166.67` | `True` |
| `discovery_jobs` | `30` | `30` | `100.00` | `True` |
| `northbound_deliveries` | `538` | `500` | `107.60` | `True` |

## Check Results

| Check ID | Status | Value | Threshold | Required | Source |
|---|---|---:|---:|---|---|
| `plug_scan.first_map_p50_seconds` | `pass` | `22.00` | `300` | `True` | `discovery.kpi.summary` |
| `plug_scan.first_map_p95_seconds` | `pass` | `24` | `900` | `True` | `discovery.kpi.summary` |
| `plug_scan.auto_reflection_rate_pct` | `pass` | `95.00` | `75.00` | `True` | `discovery.kpi.summary` |
| `plug_scan.false_positive_rate_pct` | `pass` | `5.56` | `10.00` | `True` | `discovery.kpi.summary` |
| `change.success_rate_pct` | `pass` | `99.00` | `98.00` | `True` | `sdn.dashboard.stats.change_kpi` |
| `change.failure_rate_pct` | `pass` | `1.00` | `1.00` | `True` | `sdn.dashboard.stats.change_kpi` |
| `change.rollback_p95_ms` | `pass` | `1200` | `180000` | `True` | `sdn.dashboard.stats.change_kpi` |
| `change.trace_coverage_pct` | `pass` | `100.00` | `100.00` | `True` | `sdn.dashboard.stats.change_kpi` |
| `autonomy.auto_action_rate_pct` | `pass` | `75.00` | `60.00` | `True` | `sdn.dashboard.stats.autonomy_kpi` |
| `autonomy.operator_intervention_rate_pct` | `pass` | `25.00` | `40.00` | `True` | `sdn.dashboard.stats.autonomy_kpi` |
| `autonomy.mttd_improvement_pct` | `unknown` | `-` | `30.00` | `False` | `sdn.dashboard.stats.autonomy_kpi` |
| `autonomy.mttr_improvement_pct` | `unknown` | `-` | `40.00` | `False` | `sdn.dashboard.stats.autonomy_kpi` |
| `northbound.success_rate_pct` | `pass` | `99.26` | `95.00` | `True` | `sdn.dashboard.stats.northbound_kpi` |
| `northbound.p95_attempts` | `pass` | `1` | `3` | `True` | `sdn.dashboard.stats.northbound_kpi` |
| `northbound.failed_24h` | `pass` | `4` | `5` | `True` | `sdn.dashboard.stats.northbound_kpi` |
| `sample.discovery.jobs_count` | `pass` | `30` | `30` | `True` | `ops.kpi.readiness.sample_gate` |
| `sample.change.events` | `pass` | `100` | `60` | `True` | `ops.kpi.readiness.sample_gate` |
| `sample.northbound.deliveries` | `pass` | `538` | `500` | `True` | `ops.kpi.readiness.sample_gate` |
| `sample.autonomy.issues_created` | `pass` | `20` | `20` | `True` | `ops.kpi.readiness.sample_gate` |
| `sample.autonomy.actions_executed` | `pass` | `20` | `20` | `True` | `ops.kpi.readiness.sample_gate` |

## Snapshot History

- Snapshot Count: `0`
- Coverage Days: `0` / `30`
- Coverage %: `0.00`
- Missing Days: `30`
- Status Transitions: `0`
- Current Streak: `-` x `0` snapshots

## Latest vs Previous Snapshot

- No previous snapshot available.

## Top Failing Checks (History)

- No failing checks in snapshot history.

## Top Unknown Checks (History)

- No unknown checks in snapshot history.

## Latest Snapshot Sample Coverage

- No latest snapshot sample coverage available.
