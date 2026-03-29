# Preview Edition Plan

## Goal

Ship a `preview` edition from the same repository that is optimized for:

- attractive auto discovery trials
- attractive auto topology trials
- connected NMS experience
- safe raw-output contribution and parser improvement

The preview edition is not a reduced clone of the enterprise product. It is a controlled build profile with:

- the same discovery, topology, and NMS surfaces used by the main product
- read-mostly discovery and visibility workflows
- allowlisted raw-output capture
- local sanitization preview before upload
- sanitized contribution upload only
- blocked high-risk mutation paths
- optional split deployment roles for `collector_installed` and `intake_server`

## Consent model

Preview uses a two-part first-run consent model:

- product usage terms: required
- sanitized parser-contribution upload: optional

Implications:

- users must accept product terms before using the collector
- users may continue using discovery, topology, and connected NMS without enabling uploads
- upload remains disabled until the instance-level contribution opt-in is recorded
- every upload still requires per-bundle sanitized preview review and consent

## Edition model

- Repository: single codebase
- Runtime switch: `NETSPHERE_EDITION=preview`
- Default edition: `enterprise`
- Settings fallback:
  - `product_edition`
  - `preview_capture_enabled`
  - `preview_contribution_upload_enabled`
  - `preview_contribution_require_consent`
  - `preview_allow_device_capture`
  - `preview_collection_allowed_commands_json`
  - `preview_contribution_storage_dir`
  - `preview_local_embedded_execution`

Why a single repository:

- security fixes land once
- UI/API drift stays manageable
- packaging can diverge without code forks
- preview and enterprise stay feature-compatible where it matters

## Installed collector runtime option

Preview can run in two roles without forking the codebase:

- `collector_installed`
  - local discovery, topology, connected NMS, and contribution UI
  - embedded local task execution for discovery/topology
  - backend-served SPA for localhost usage
- `intake_server`
  - central sanitized contribution receiver

Recommended transport defaults:

- collector_installed: `remote_only`
- intake_server: `local_only`

## Preview-safe workflows

Allowed:

- inventory and topology visibility
- discovery and device browsing
- diagnosis and observability views
- automation hub navigation for preview-safe experiences
- read-only raw command capture from stored device credentials
- manual raw output paste
- sanitized preview review
- sanitized contribution upload

Blocked:

- config deployment
- destructive automation
- rollback execution
- privileged settings mutation
- external webhook delivery paths
- cloud/bootstrap/fabric/policy/ztp mutation flows

## Collection policy

Initial allowlist:

- `show version`
- `display version`
- `get system status`
- `show inventory`
- `show chassis hardware`
- `display device`
- `show interfaces brief`
- `show interfaces status`
- `show interfaces terse`
- `display interface brief`
- `show vlan`
- `display vlan`
- `show mac address-table`
- `display mac-address`
- `show lldp neighbors detail`
- `show cdp neighbors detail`
- `display lldp neighbor-information verbose`
- `show ip route summary`
- `show route summary`
- `display ip routing-table statistics`
- `show ospf neighbor`
- `show ip ospf neighbor`
- `display ospf peer`
- `show bgp summary`
- `show ip bgp summary`
- `display bgp peer`
- `show evpn summary`
- `show bgp evpn summary`
- `show vxlan vni`
- `show nve peers`
- `show system info`

Blocked command prefixes:

- `show running-config`
- `show startup-config`
- `show configuration`
- `display current-configuration`
- `display saved-configuration`
- `show full-configuration`
- `tmsh list`
- `show aaa`
- `show tacacs`
- `show radius`
- `show crypto`
- `show nat session`

## Sanitization policy

Sanitization runs before persistence.

Masked/tokenized by default:

- IPv4/IPv6 addresses
- MAC addresses
- hostnames
- serial numbers
- email addresses
- URLs/domains
- secret-bearing lines
- certificate/private-key blocks

Design rule:

- preserve topology/parser-relevant shape
- preserve interface names, protocol state, model names, OS versions
- keep replacements deterministic inside one contribution bundle

## Storage model

Stored data:

- sanitized bundle only
- sanitized metadata only
- no raw original persistence

Storage target:

- `Netsphere_Free_Backend/preview_contributions/`

Bundle content:

- contribution id
- submitted timestamp
- source
- consent flag
- device context without direct identifiers
- redaction summary
- sanitized command outputs
- optional operator notes

## UI flow

1. Complete first-run product terms acceptance
2. Optionally enable preview contribution upload
3. Open `Preview Contribution`
4. Choose `Device capture` or `Manual paste`
5. Select allowlisted commands or paste raw output
6. Review sanitized preview
7. Confirm consent for that bundle
8. Upload sanitized contribution

## Release intent

This edition is intended for:

- prototype field validation
- parser fixture growth
- vendor output diversity collection

It is not intended for:

- production change execution
- privileged automation
- full enterprise administration
