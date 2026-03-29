# Real Device Acceptance Runbook

This runbook prepares the final physical-device acceptance pass that follows fixture, synthetic, and EVE validation.

## Goal

Validate that NetSphere behaves correctly against real hardware without changing the existing release evidence rules.

Primary outcomes:

- collect raw command evidence per vendor family
- prove discovery, topology, config, rollback, and diagnosis behavior
- record pass/fail status in a reusable checklist
- package artifacts for customer or internal sign-off

## Scope

Run this pass only for target vendor families that matter for commercial delivery.

Recommended first wave:

- Cisco IOS / IOS XE
- Cisco NX-OS
- Juniper Junos
- Arista EOS
- Huawei VRP / CloudEngine
- Dell OS10
- Fortinet FortiGate
- Palo Alto PAN-OS

Second wave:

- Aruba AOS-Switch / AOS-CX
- H3C Comware
- Nokia SR OS
- F5 BIG-IP
- Check Point Gaia
- domestic switch / security vendors used by target customers

## Generated checklist

Generate the latest acceptance plan and CSV checklist:

```bash
python Netsphere_Free_Backend/tools/export_real_device_acceptance_plan.py
```

Generated outputs:

- `docs/reports/real-device-acceptance.latest.json`
- `docs/reports/real-device-acceptance.latest.md`
- `docs/reports/real-device-acceptance-checklist.latest.csv`

## Required evidence per device

For each representative device:

1. raw CLI text, not screenshots
2. version / model / serial output
3. interface summary
4. neighbor detail
5. routing or forwarding evidence
6. running or current config
7. feature-on capture
8. feature-off or empty-state capture

When applicable, also collect:

- BGP / OSPF state
- VXLAN / EVPN / VNI state
- policy / NAT / session summary
- HA / stack / cluster state
- WLAN / AP summaries

## Mandatory scenarios

Network NOS:

- inventory and facts import
- discovery import
- L2 topology reflection
- L3 topology reflection
- path trace
- config backup
- dry-run deploy
- approval trace
- rollback
- diagnosis

Overlay-capable NOS:

- VXLAN overlay visibility
- BGP EVPN visibility

Security platforms:

- route visibility
- northbound event delivery

Wireless platforms:

- WLAN summary
- AP summary

## Execution order

1. generate the acceptance plan
2. select one representative device per platform family
3. collect raw outputs and store them under a vendor/date folder
4. import the device into NetSphere
5. execute mandatory scenarios from the CSV checklist
6. attach run IDs, exported reports, and failure notes
7. mark `acceptance_pass` only when all mandatory scenarios pass

## Pass criteria

- device facts and inventory are parsed correctly
- discovery completes without blocking parser errors
- expected topology/path views are visible when feature data exists
- config backup and dry-run succeed
- approval ID to execution ID trace is present
- rollback succeeds when policy allows rollback
- diagnosis output is structured and actionable
- raw evidence and checklist row are archived together

## Archive layout

Recommended per-device folder:

```text
acceptance/<date>/<vendor-family>/<hostname>/
  raw/
  exported/
  checklist-row.json
  notes.md
```

## Notes

- This runbook does not replace KPI readiness, synthetic validation, or northbound soak evidence.
- This is the final vendor-family proof layer before commercial rollout.
