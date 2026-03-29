# Vendor Support Policy (Release)

This document defines the shipping support policy used by UI/API guardrails.

## Support tiers

### 1) Official support
- Scope: fully validated vendor/device-type matrix rows (`readiness=full`).
- Feature scope:
  - `Discovery`: allowed
  - `Sync`: allowed
  - `ZTP`: allowed
  - `Config`: allowed
  - `Rollback`: allowed (strategy required)

### 2) Limited support
- Scope: matrix rows with partial validation (`readiness=extended/basic/partial`).
- Feature scope:
  - `Discovery`: allowed
  - `Sync`: allowed
  - `ZTP`: allowed
  - `Config`: allowed
  - `Rollback`: allowed only when rollback strategy is supported
- Notes:
  - Per-vendor/per-version overrides can narrow features.
  - Capability profile `read_only=true` forces read-only fallback.

### 3) Unsupported
- Scope: device types not covered by support matrix or explicitly blocked by policy.
- Feature scope:
  - `Discovery`: allowed (read-only collection)
  - `Sync`: allowed (read-only collection)
  - `ZTP`: blocked
  - `Config`: blocked
  - `Rollback`: blocked
- Fallback mode:
  - `read_only_manual_approval`

## Runtime enforcement points

- `Device create/update`: support profile evaluated and stored in `device.variables.support_policy`.
- `Discovery approve`: support profile evaluated for newly created devices.
- `ZTP register/approve/provisioning`:
  - unsupported `ztp` feature is blocked.
  - fallback message returned for manual handling.
- `Sync` endpoint:
  - blocked when `sync` feature is disabled by policy.
- Change execution paths (`config/fabric/compliance/visual-config/template deploy`):
  - blocked when `config` is disabled.
  - `rollback_on_failure` blocked when `rollback` is disabled.

## Rollback strategy compatibility

- Supported examples:
  - Juniper/Junos: `native_junos_rollback`
  - Cisco/Arista/Huawei/Fortinet/PaloAlto/Nokia/Extreme/Dell/major domestic switch vendors:
    `snapshot_replace_rollback`
- Unsupported:
  - host OS families (`linux*`, `windows*`)
  - unknown/generic device types
- Rule:
  - If strategy is unsupported, rollback is blocked regardless of tier.

## Policy configuration key

- System setting key: `vendor_support_policy_json`
- Normalization/validation is enforced on settings update.
- Recommended workflow:
  1. Generate matrix from replay fixtures.
  2. Review tier mapping and override rules.
  3. Apply setting via API.
  4. Verify block/fallback behavior through API tests.

## Related artifacts

- Matrix source: `docs/reports/vendor-support-matrix.latest.json`
- Matrix report (markdown): `docs/reports/vendor-support-matrix.latest.md`
- Replay fixtures: `test-data/vendor-fixtures/`
- Replay tests:
  - `Netsphere_Free_Backend/tests/synthetic/test_vendor_parser_benchmark.py`
  - `Netsphere_Free_Backend/tests/synthetic/test_vendor_parser_replay_variants.py`

## Feature gate grade table (fixed)

| Grade | Discovery/Inventory | Sync | ZTP | Config Deploy | Rollback |
|---|---|---|---|---|---|
| Official | Allow | Allow | Allow | Allow | Allow |
| Limited | Allow | Allow | Allow with caution | Allow with caution | Conditional (strategy required) |
| Unsupported | Read-only only | Read-only only | Block | Block | Block |

## Vendor/OS enforcement baseline

| Device class | Support default | Notes |
|---|---|---|
| Major network NOS (Cisco/Arista/Juniper/Fortinet/PaloAlto/Nokia/Extreme/Dell + supported domestic switch NOS) | Official/Limited by matrix row | Exact grade decided by `vendor_support_policy_json` row (`vendor + os + version`). |
| Generic/unknown network device | Limited | Discovery/Sync read-heavy; write paths require explicit allow. |
| Host OS (`linux*`, `windows*`) | Unsupported for network-change | Read-only collection only. |

## Mandatory block / fallback criteria

- `DEVICE_SUPPORT_BLOCKED` is returned when:
  - feature is not allowed by support matrix grade, or
  - requested rollback is unsupported for target vendor/os/version.
- `rollback_on_failure=true` must return `409` when any target lacks rollback strategy support.
- Unsupported write operations must fall back to:
  - `read_only_manual_approval`
  - manual approval queue with clear operator hint.

## Governance rules

- Every matrix row must declare:
  - `vendor`, `os_family`, `version_pattern`, `readiness`
  - per-feature booleans (`discovery/sync/ztp/config/rollback`)
  - fallback mode (`read_only_manual_approval` or stricter)
- New vendor onboarding is blocked from write paths until:
  - replay fixture coverage is added
  - parser confidence threshold is met
  - rollback strategy mapping exists
