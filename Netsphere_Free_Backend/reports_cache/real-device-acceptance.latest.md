# Real Device Acceptance Plan

- Generated at: 2026-03-09T04:41:06.502419+00:00
- Source vendor matrix: 2026-03-09T04:14:46.855407+00:00
- Total device types: 49
- Wave 1 / 2 / 3: 28 / 21 / 0

## Usage

1. Reserve one representative device per `platform_family`.
2. Capture all commands in raw text for both populated and empty feature states.
3. Import device into NetSphere and execute the mandatory scenarios.
4. Mark the CSV checklist and archive raw outputs alongside the run report.

## Acceptance rows

| Wave | Device Type | Platform Family | Readiness | Scenarios |
|---|---|---|---|---|
| 1 | `alcatel_aos` | Alcatel OmniSwitch AOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `aruba_os` | Aruba AOS-Switch | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `cisco_nxos` | Cisco NX-OS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `cisco_wlc` | Cisco Wireless Controller | full | inventory_facts, discovery_import, wireless_summary, config_backup... |
| 1 | `coreedge_switch` | Domestic Switch NOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `dasan_nos` | Domestic Switch NOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `dell_os10` | Dell OS10 / Force10 | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `extreme_exos` | Extreme EXOS / NetIron | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `f5_ltm` | F5 BIG-IP / TMOS | full | inventory_facts, discovery_import, route_visibility, config_backup... |
| 1 | `fortinet` | Fortinet FortiGate | full | inventory_facts, discovery_import, route_visibility, path_trace... |
| 1 | `handream_sg` | Domestic Switch NOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `hp_comware` | H3C Comware | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `nokia_sros` | Nokia SR OS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `nst_switch` | Domestic Switch NOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `paloalto_panos` | Palo Alto PAN-OS | full | inventory_facts, discovery_import, route_visibility, path_trace... |
| 1 | `piolink_pas` | Domestic Switch NOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `soltech_switch` | Domestic Switch NOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `ubiquoss_l2` | Domestic Switch NOS | full | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `cisco_ios` | Cisco IOS / IOS XE | extended | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `arista_eos` | Arista EOS | extended | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `checkpoint_gaia` | Check Point Gaia | extended | inventory_facts, discovery_import, route_visibility, path_trace... |
| 1 | `cisco_ios_xe` | Cisco IOS / IOS XE | extended | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `huawei_vrp` | Huawei VRP / CloudEngine | extended | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `juniper_junos` | Juniper Junos | extended | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `arista` | Arista EOS | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `dell_force10` | Dell OS10 / Force10 | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `huawei` | Huawei VRP / CloudEngine | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 1 | `juniper` | Juniper Junos | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 2 | `cisco_xe` | Generic Network Device | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `dasan` | Domestic Switch NOS | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 2 | `extreme_netiron` | Extreme EXOS / NetIron | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 2 | `handream` | Domestic Switch NOS | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 2 | `hp_procurve` | Aruba AOS-Switch | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 2 | `linux` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_ahnlab` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_aircuve` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_axgate` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_genians` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_mlsoft` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_monitorapp` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_netman` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_nexg` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_nixtech` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_secui` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_sga` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_trinitysoft` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `linux_wins` | Linux-like Network OS | basic | inventory_facts, discovery_import, config_backup, approval_trace... |
| 2 | `ubiquoss` | Domestic Switch NOS | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
| 2 | `ubiquoss_l3` | Domestic Switch NOS | basic | inventory_facts, discovery_import, l2_topology_reflection, l3_topology_reflection... |
