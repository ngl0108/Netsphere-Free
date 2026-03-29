# Auto Discovery + Auto Topology Runbook

## Scope
- Plug & Scan flow for `Auto Discovery` and `Auto Topology`
- Policy-based auto-approval
- Low-confidence candidate queue operations
- KPI and trend operations for daily use

## 1. Required Settings (Production Baseline)
- `auto_discovery_enabled=true`
- `auto_discovery_mode=seed` (for Plug & Scan)
- `auto_discovery_refresh_topology=true`
- `topology_candidate_low_confidence_threshold=0.7`
- `auto_approve_enabled=true`
- `auto_approve_min_vendor_confidence=0.8`
- `auto_approve_require_snmp_reachable=true`
- `auto_approve_block_severities=error`
- Optional:
  - `auto_approve_trigger_topology=true`
  - `auto_approve_trigger_sync=true`
  - `auto_approve_trigger_monitoring=true`
  - Ops alert thresholds:
    - `ops_alerts_min_auto_reflection_pct=70`
    - `ops_alerts_max_false_positive_pct=20`
    - `ops_alerts_max_low_confidence_rate_pct=30`
    - `ops_alerts_max_candidate_backlog=100`
    - `ops_alerts_max_stale_backlog_24h=20`

## 2. Runtime Behavior
- Discovery completes
- Auto-approve runs in policy mode (`approve-all?policy=true`)
- Approval output contains:
  - `approved_count`
  - `skipped_count`
  - `skip_breakdown` (reason counts)
  - `policy` (effective policy values)
- Topology candidate queue continues to track low-confidence links

## 3. Skip Reasons (Policy Mode)
- `low_vendor_confidence`
- `snmp_unreachable`
- `blocked_issue_severity`
- `low_confidence_link`
- `approve_exception`

## 4. Operator Workflow
- Discovery page:
  - Check KPI window (`7d/30d`) and `Site` filter
  - Check `Operational Alerts` status (`healthy/warning/critical`)
  - Review `Auto-Approve Execution` card after Plug & Scan
  - Review queue metrics:
    - `Candidate Backlog`
    - `Queue Processed (24h)`
    - Trend (`daily` for 7d, `weekly` for 30d)
- Topology page:
  - Open `Candidate Links`
  - Filter by `Low Confidence`, `Site`, `Trend 7d/30d`
  - Promote/Ignore queue items

## 5. E2E Verification Checklist
- API tests:
  - `tests/api/test_discovery_kpi_alerts_api.py`
  - `tests/api/test_discovery_approve_all_policy_api.py`
  - `tests/api/test_discovery_kpi_api.py`
  - `tests/api/test_topology_candidates_summary_api.py`
  - `tests/api/test_topology_candidates_summary_trend_api.py`
  - `tests/api/test_plug_scan_e2e_flow_api.py`
- Build and runtime:
  - `npm run build` (frontend)
  - `npm run e2e` (frontend smoke, Playwright)
  - `docker compose build backend frontend`
  - `docker compose up -d --force-recreate backend frontend`
  - `docker compose logs --tail=120 backend`
  - `docker compose logs --tail=120 frontend`

## 6. 30-Day Quality Gate (Done Criteria)
- Core chain:
  - Discovery dispatch is Celery-based in standard server deployments
  - Preview installed collector may use embedded local dispatch for `/scan`, `/crawl`, and topology refresh
  - Approval chain enforces idempotency key for topology/sync dispatch
- Required API tests:
  - `tests/api/test_discovery_dispatch_api.py`
  - `tests/api/test_discovery_approve_all_dispatch_chain_api.py`
  - `tests/api/test_plug_scan_auth_regression_api.py`
  - `tests/test_discovery_dispatch.py`
  - `tests/test_topology_dispatch.py`
  - `tests/test_device_sync_batch.py`
  - `tests/test_auto_discovery_scheduler_dispatch.py`
- Runtime checks:
  - `docker compose build backend celery-worker celery-beat`
  - `docker compose up -d backend celery-worker celery-beat`
  - `docker compose logs --tail=200 backend celery-worker celery-beat`
  - Verify no startup import errors and no auth regression in normal operator/viewer flow
## 7. Incident Notes
- Ops alert API:
  - `GET /api/v1/discovery/kpi/alerts`
  - Filters: `days`, `site_id`
  - Threshold params:
    - `min_auto_reflection_pct`
    - `max_false_positive_pct`
    - `max_low_confidence_rate_pct`
    - `max_candidate_backlog`
    - `max_stale_backlog_24h`
- If auto-approve skips spike:
  - Inspect `skip_breakdown`
  - Validate threshold/severity settings
  - Review candidate queue by reason and site
- If topology lags:
  - Confirm `auto_discovery_refresh_topology=true`
  - Check worker status and queue health
