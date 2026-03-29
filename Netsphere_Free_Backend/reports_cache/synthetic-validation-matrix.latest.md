# Synthetic Validation Matrix

- Generated at: 2026-03-22T20:56:47.091822+00:00
- Profile: ci
- Overall: PASS

## Scenario catalog

| Scenario | Devices | Links | Events | Critical | Warning | Info | Focus | Protocols |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| failure | 64 | 96 | 12 | 1 | 11 | 0 | failure, retry, recovery | bgp, cdp, lldp |
| hybrid_cloud | 54 | 78 | 22 | 0 | 1 | 21 | hybrid, cloud, bgp | bgp, cloud, lldp |
| large_scale | 260 | 468 | 60 | 0 | 0 | 60 | scale, throughput, topology | bgp, fdb, lldp |
| normal | 24 | 33 | 20 | 0 | 0 | 20 | baseline, inventory, topology | cdp, fdb, lldp |
| rollback_wave | 48 | 72 | 32 | 1 | 4 | 27 | change, rollback, approval | bgp, lacp, lldp |
| security_incident | 72 | 100 | 16 | 16 | 0 | 0 | security, policy, isolation | fdb, lldp, vxlan |
| wireless_edge | 36 | 46 | 13 | 0 | 1 | 12 | wireless, edge, telemetry | capwap, fdb, lldp |

- Required scenarios: normal, large_scale, failure, security_incident
- Missing required scenarios: none
- Expanded scenarios: rollback_wave, hybrid_cloud, wireless_edge
- Missing expanded scenarios: none
- Focus areas: approval, baseline, bgp, change, cloud, edge, failure, hybrid, inventory, isolation, policy, recovery, retry, rollback, scale, security, telemetry, throughput, topology, wireless
- Protocols: bgp, capwap, cdp, cloud, fdb, lacp, lldp, vxlan
- Total devices: 558
- Total links: 893
- Total events: 175

## Soak matrix

| Scenario | Duration(s) | Tick(ms) | Processed | Dup ratio | Forced logout | Max queue | Throughput eps | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| failure | 5 | 10 | 425 | 0.087059 | 0 | 440 | 85.0 | PASS |
| security_incident | 5 | 10 | 372 | 0.086022 | 0 | 298 | 74.4 | PASS |
| rollback_wave | 5 | 10 | 418 | 0.074163 | 0 | 414 | 83.6 | PASS |
| large_scale | 5 | 5 | 747 | 0.082999 | 0 | 758 | 149.4 | PASS |

## EVE plan coverage

- Digital twin vendors: arista, cisco, f5, fortinet, juniper, mikrotik, nokia, paloalto, vyos
- First-wave vendors: Juniper, Fortinet, Palo Alto, F5, Nokia, VyOS, MikroTik
- Second-wave vendors: Arista cEOS/vEOS (entitled access), Cisco Nexus/CSR/ASAv (entitled trial/support access), Check Point CloudGuard (marketplace trial), Dell OS10-V (entitled support access)
- Mandatory cases: 8
- Acceptance gates: 5
- Evidence files: 4

## Gate checks

### manifest

- manifest_file_exists: PASS
- manifest_has_entries: PASS
- manifest_hashes_match: PASS
- digital_twin_protocols_present: PASS
- digital_twin_vendor_floor: PASS
- digital_twin_case_consistency: PASS

### scenario_catalog

- required_scenarios_present: PASS
- expanded_scenarios_present: PASS
- scenario_count_floor: PASS
- normal_has_only_info_events: PASS
- failure_has_critical_signal: PASS
- security_incident_has_critical_burst: PASS
- large_scale_meets_floor: PASS
- expanded_focus_areas_present: PASS
- rollback_wave_has_rollback_signal: PASS
- hybrid_cloud_has_hybrid_signal: PASS
- wireless_edge_has_wireless_signal: PASS

### soak_matrix

- runs_executed: PASS
- all_runs_healthy: PASS
- large_scale_has_high_volume: PASS

### eve_plan

- required_first_wave_vendors_present: PASS
- first_wave_vendor_count_floor: PASS
- mandatory_case_count_floor: PASS
- acceptance_gate_count_floor: PASS
- evidence_file_count_floor: PASS
