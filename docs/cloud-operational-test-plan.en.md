# Cloud Operational Test Plan (Free-Tier, No On-Prem)

## 1. Scope

- Plan window: 2026-02-27 to 2026-03-31
- Controller: NetSphere v2.5.x
- Environment constraints:
  - No on-prem devices
  - AWS/GCP/Azure free-tier accounts available
- Sign-off targets:
  - 72h northbound soak evidence
  - 30-day KPI measured evidence (MTTD/MTTR/auto-action and core KPI gates)
  - ITSM/SIEM connector staging-to-production certification runbook sign-off

## 2. Test Topology Blueprint

Use one "always-on" node and one "ephemeral" node per cloud to create stable + churn signals.

| Provider | Site ID | Region | Network | Always-On Node | Ephemeral Node |
|---|---|---|---|---|---|
| AWS | aws_hq | us-east-1 | VPC 10.10.0.0/16, 2 subnets | aws-core-1 | aws-edge-ephemeral |
| GCP | gcp_hq | us-central1 | VPC 10.20.0.0/16, 2 subnets | gcp-core-1 | gcp-edge-ephemeral |
| Azure | azr_hq | eastus | VNet 10.30.0.0/16, 2 subnets | azr-core-1 | azr-edge-ephemeral |

Tag convention (all providers):

- `nm_site` (aws_hq/gcp_hq/azr_hq)
- `nm_role` (core/edge)
- `nm_env` (staging)
- `nm_owner` (team or user)
- `nm_trace_id` (run id)
- `nm_test_ttl` (yyyy-mm-dd)

## 3. Cloud Resource Build Guide

### AWS

1. Create VPC, 2 subnets, route table, security group baseline.
2. Create `aws-core-1` as always-on VM.
3. Create `aws-edge-ephemeral` and schedule start/stop.
4. Avoid costly resources by default: NAT Gateway, managed VPN, excess public IPv4.

### GCP

1. Create custom VPC, 2 subnets, firewall baseline.
2. Keep `gcp-core-1` always-on in Always Free eligible region.
3. Use `gcp-edge-ephemeral` only in test windows.
4. Apply budget alerts and network egress guardrails.

### Azure

1. Create resource group, VNet, 2 subnets, NSG baseline.
2. Keep `azr-core-1` always-on.
3. Use `azr-edge-ephemeral` only in test windows.
4. Enable cost budget alerts and shut down idle resources.

## 4. NetSphere Integration Setup

1. Register 3 cloud accounts in Cloud Accounts page.
2. Verify account preflight checks pass.
3. Run cloud discovery pipeline.
4. Verify topology filters:
   - Provider
   - Account
   - Region
5. Confirm normalized resources appear:
   - Network (VPC/VNet/Subnet)
   - Compute (VM)
   - Security and route entities where supported

## 5. Test Scenarios

### A. Discovery + Topology Reflection

1. Trigger discovery per provider and global run.
2. Validate first map generation time and reflection completeness.
3. Toggle ephemeral nodes (on/off) 2-3 times/day.
4. Confirm topology updates without duplicates.

Expected evidence:

- Discovery jobs and durations
- Topology node/link diffs
- Candidate queue deltas

### B. Dedup + Low-Confidence Candidate Queue

1. Create intentionally similar naming/tag patterns across providers.
2. Introduce incomplete metadata on selected resources.
3. Confirm low-confidence items are queued (not auto-promoted).
4. Approve/reject candidates and verify topology reflection behavior.

Expected evidence:

- Candidate queue trend
- False-positive ratio
- Approval trace linkage

### C. Cloud Bootstrap + Safe Change Engine

1. Run dry-run for bootstrap templates.
2. Run wave rollout across one node per cloud.
3. Inject one controlled failure (invalid bootstrap payload on ephemeral node).
4. Verify post-check failure triggers rollback.

Expected evidence:

- Execution logs with dry-run/wave/rollback
- Approval ID <-> Execution ID trace
- Rollback latency (P95)

### D. Intent + Closed-Loop

1. Apply `cloud_policy` intents in simulation mode first.
2. Introduce policy drift (tag/rule violation).
3. Verify closed-loop evaluates action and respects approval gate policy.
4. Confirm action/notification traces are generated.

Expected evidence:

- Intent validate/simulate/apply results
- Drift detection logs
- Auto-action vs operator intervention counts

### E. Northbound ITSM/SIEM 72h Soak

1. Run soak with connector mode rotation:
   - jira
   - servicenow
   - splunk
   - elastic
2. Enforce signature validation in local receiver or staging endpoint.
3. Keep periodic failure injection to verify retry/backoff behavior.

Expected evidence:

- 72h success rate
- attempts P95
- failed_24h
- signature valid rate

## 6. Operational Commands

### 6.1 72h Soak

```bash
python Netsphere_Free_Backend/tools/run_northbound_soak_verification.py \
  --base-url http://localhost:8000 \
  --login-username "<admin>" \
  --login-password "<password>" \
  --duration-hours 72 \
  --interval-seconds 120 \
  --modes jira,servicenow,splunk,elastic \
  --use-local-receiver \
  --local-receiver-host host.docker.internal \
  --local-receiver-port 18080 \
  --local-receiver-fail-every 10 \
  --local-receiver-enforce-signature \
  --webhook-secret "soak-secret" \
  --min-success-rate-pct 95 \
  --max-attempts-p95 3 \
  --max-failed-24h 5 \
  --min-signature-valid-rate-pct 100 \
  --latest-json-path docs/reports/northbound-soak-72h-latest.json \
  --latest-md-path docs/reports/northbound-soak-72h-latest.md \
  --fail-on-threshold
```

### 6.2 30-day KPI Readiness

```bash
python Netsphere_Free_Backend/tools/export_kpi_readiness_report.py \
  --base-url http://localhost:8000 \
  --token "<token>" \
  --discovery-days 30 \
  --require-sample-minimums \
  --sample-min-discovery-jobs 30 \
  --sample-min-change-events 60 \
  --sample-min-northbound-deliveries 500 \
  --sample-min-autonomy-issues-created 20 \
  --sample-min-autonomy-actions-executed 20 \
  --latest-json-path docs/reports/kpi-readiness-30d-latest.json \
  --latest-md-path docs/reports/kpi-readiness-30d-latest.md \
  --fail-on-unhealthy
```

## 7. Acceptance Gates

### Soak gates

1. `success_rate_pct >= 95`
2. `attempts_p95 <= 3`
3. `failed_24h <= 5`
4. `signature_valid_rate_pct >= 100`

### KPI gates

1. Plug and Scan:
   - first map P50 within target
   - auto reflection rate within target
   - false positive rate within target
2. Safe change:
   - change success rate within target
   - rollback P95 within target
3. Intent/autonomy:
   - measurable MTTD/MTTR trend improvement
   - auto-action and intervention rates captured with sufficient sample sizes

## 8. Cost and Safety Guardrails

1. Enforce budgets and alerts in each cloud (50/80/95 percent thresholds).
2. Auto-stop ephemeral VMs outside test windows.
3. Mandatory TTL tag on all test resources.
4. Daily cleanup of orphan resources (public IP, disk, snapshot, load balancer).
5. No production secret material in test payloads.

## 9. Output Artifacts

- `docs/reports/northbound-soak-72h-latest.json`
- `docs/reports/northbound-soak-72h-latest.md`
- `docs/reports/kpi-readiness-30d-latest.json`
- `docs/reports/kpi-readiness-30d-latest.md`
- Daily execution log and incident notes

## 10. Exit Criteria

Plan is signed off only when:

1. 72h soak report passes thresholds.
2. 30-day KPI readiness report reaches accepted status with sample minimums met.
3. Connector certification runbook checklist is completed and approved.
