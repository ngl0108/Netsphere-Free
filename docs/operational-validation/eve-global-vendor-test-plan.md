# EVE-NG Global Vendor Operational Test Plan

## 1. Goal

Validate NetSphere behavior for on-prem style workflows without physical devices by using EVE-NG virtual network OS images.

Coverage goals:

- Discovery and topology reflection
- Candidate queue and confidence handling
- Sync/parser stability by vendor OS style
- Change workflow (dry-run, approval, wave, rollback)
- Closed-loop and intent execution traces

## 2. Legal and licensing policy

Use only official vendor acquisition paths (trial, support portal, marketplace, vendor dev programs).

Do not use images with license restrictions that prohibit external use in EVE environments.

## 3. Recommended first-wave vendors

- Juniper: vQFX / vSRX / vMX trial paths
- Fortinet: FortiGate-VM trial/permanent trial mode
- Palo Alto: VM-Series trial
- F5: BIG-IP VE trial
- Nokia: SR Linux container image
- VyOS: rolling image
- MikroTik: CHR

Second-wave expansion:

- Arista cEOS/vEOS (entitled access)
- Cisco Nexus/CSR/ASAv (entitled trial/support access)
- Check Point CloudGuard (marketplace trial)
- Dell OS10-V (entitled support access)

## 4. EVE topology blueprint

Management plane:

- `172.16.100.0/24` (all nodes reachable from NetSphere)

Data plane pods:

1. Routing Core Pod (6-8 nodes)
   - OSPF + BGP + LLDP
2. Security Edge Pod (4-6 nodes)
   - Firewall policy and north-south inspection path
3. Multi-vendor Pod (4-6 nodes)
   - Alternate NOS behavior (container + VM mix)

Test-only utility nodes:

- 2 traffic generators
- 1 fault-injection node (delay/loss/flap simulation)

## 5. 30-day execution model

Week 1:

- Acquire images and boot baseline topology
- Register credentials and verify discovery reaches all pods

Week 2:

- Run repeated discovery and topology reflection checks
- Validate low-confidence candidate queue behavior

Week 3:

- Execute safe change scenarios with failure injection
- Verify rollback timing and approval-execution trace linkage

Week 4:

- Run closed-loop intent scenarios
- Execute 24h-72h soak for polling/event stability
- Export sign-off evidence

## 6. Mandatory test cases

1. Device identity accuracy by vendor OS family
2. Link reflection accuracy (LLDP/CDP/route-derived links)
3. Candidate queue split for low-confidence links
4. Parser robustness on partial/timeout/malformed outputs
5. Dry-run -> approval -> wave -> post-check execution chain
6. Post-check failure rollback and P95 rollback time
7. 401/403/session-expiry resilience under polling load
8. Closed-loop action gating and trace completeness

## 7. Acceptance gates

- Topology reflection regressions: 0 blocking defects
- Approval ID <-> Execution ID traceability: 100%
- Rollback P95 within policy target
- No persistent session/polling instability during soak
- Evidence reports generated and archived

## 8. Evidence files

- `docs/reports/kpi-readiness-30d-latest.json`
- `docs/reports/kpi-readiness-30d-latest.md`
- `docs/reports/northbound-soak-72h-latest.json`
- `docs/reports/northbound-soak-72h-latest.md`

## 9. Notes

This plan is for functional and operational behavior validation without physical hardware.
Before commercial rollout, run a final customer-environment acceptance pass with at least one real device per target vendor family.

