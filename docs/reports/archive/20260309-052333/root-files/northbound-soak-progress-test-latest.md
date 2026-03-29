# Northbound 72h Soak Verification

- Generated (UTC): `2026-02-17 14:45:19`
- Run ID: `20260217-144459`
- Duration Seconds: `18`
- Overall Status: `pass`

## Summary

- Total Attempts: `4`
- Success Count: `4`
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
| `elastic` | `1` | `1` | `0` | `100.0` | `1` |

## Dashboard Northbound KPI

- status: `idle`
- success_rate_pct: `100.0`
- p95_attempts: `0`
- failed_24h: `0`

## Local Receiver (Signature + Retry Probe)

- enabled: `True`
- total_requests: `4`
- signature_valid_rate_pct: `100.0`
- responses_5xx: `0`

## Gate Checks

| Check | Status | Value | Threshold |
|---|---|---:|---:|
| `northbound.success_rate_pct` | `pass` | `100.0` | `95.0` |
| `northbound.attempts_p95` | `pass` | `1.0` | `3.0` |
| `northbound.failed_24h` | `pass` | `0.0` | `5.0` |
| `receiver.signature_valid_rate_pct` | `pass` | `100.0` | `100.0` |
