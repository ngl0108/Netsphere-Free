# Northbound 72h Soak Verification

- Generated (UTC): `2026-02-28 08:11:54`
- Run ID: `20260228-080941`
- Duration Seconds: `108`
- Overall Status: `fail`

## Summary

- Total Attempts: `4`
- Success Count: `0`
- Failure Count: `4`
- Success Rate: `0.0`%
- Attempts P95: `None`

## Thresholds

- min_success_rate_pct: `95.0`
- max_attempts_p95: `3`
- max_failed_24h: `5`
- min_signature_valid_rate_pct: `100.0`

## Per-Mode

| Mode | Attempts | Success | Fail | Success Rate | Attempts P95 |
|---|---:|---:|---:|---:|---:|
| `jira` | `1` | `0` | `1` | `0.0` | `None` |
| `servicenow` | `1` | `0` | `1` | `0.0` | `None` |
| `splunk` | `1` | `0` | `1` | `0.0` | `None` |
| `elastic` | `1` | `0` | `1` | `0.0` | `None` |

## Dashboard Northbound KPI

- status: `idle`
- success_rate_pct: `100.0`
- p95_attempts: `0`
- failed_24h: `0`

## Local Receiver (Signature + Retry Probe)

- enabled: `True`
- total_requests: `0`
- signature_valid_rate_pct: `0.0`
- responses_5xx: `0`

## Gate Checks

| Check | Status | Value | Threshold |
|---|---|---:|---:|
| `northbound.success_rate_pct` | `fail` | `0.0` | `95.0` |
| `northbound.attempts_p95` | `pass` | `0.0` | `3.0` |
| `northbound.failed_24h` | `pass` | `0.0` | `5.0` |
| `receiver.signature_valid_rate_pct` | `fail` | `0.0` | `100.0` |
