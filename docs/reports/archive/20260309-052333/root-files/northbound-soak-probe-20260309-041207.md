# Northbound 72h Soak Verification

- Generated (UTC): `2026-03-09 04:12:07`
- Run ID: `20260309-041157`
- Duration Seconds: `9`
- Overall Status: `pass`

## Summary

- Total Attempts: `3`
- Success Count: `3`
- Failure Count: `0`
- Success Rate: `100.0`%
- Attempts P95: `1`

## Thresholds

- min_success_rate_pct: `95.0`
- max_attempts_p95: `3`
- max_failed_24h: `5`
- min_signature_valid_rate_pct: `100.0`

## Per-Mode

| Mode | Attempts | Success | Fail | Success Rate | Attempts P95 |
|---|---:|---:|---:|---:|---:|
| `jira` | `1` | `1` | `0` | `100.0` | `1` |
| `servicenow` | `1` | `1` | `0` | `100.0` | `1` |
| `splunk` | `1` | `1` | `0` | `100.0` | `1` |
| `elastic` | `0` | `0` | `0` | `0.0` | `None` |

## Dashboard Northbound KPI

- status: `healthy`
- success_rate_pct: `99.25`
- p95_attempts: `1`
- failed_24h: `4`

## Local Receiver (Signature + Retry Probe)

- enabled: `True`
- total_requests: `3`
- signature_valid_rate_pct: `100.0`
- responses_5xx: `0`

## Gate Checks

| Check | Status | Value | Threshold |
|---|---|---:|---:|
| `northbound.success_rate_pct` | `pass` | `100.0` | `95.0` |
| `northbound.attempts_p95` | `pass` | `1.0` | `3.0` |
| `northbound.failed_24h` | `pass` | `4.0` | `5.0` |
| `receiver.signature_valid_rate_pct` | `pass` | `100.0` | `100.0` |
