# Vendor Parser Fixtures (No Real Device Required)

This dataset is for deterministic parser/driver replay without real devices.

## Why this exists

- Improve parser stability before field rollout.
- Catch regressions in vendor parsing behavior.
- Validate domestic vendor parsing logic with controlled CLI output samples.

## Structure

- `inventory/<device_type>/*.json`: inventory parser replay cases.
- `neighbors/<device_type>/*.json`: neighbor parser replay cases.
- `facts/<device_type>/*.json`: driver facts parsing cases.

## Fixture schema

```json
{
  "id": "inventory.cisco_ios_xe.chassis_basic",
  "fixture_group": "domestic_switch",
  "type": "inventory",
  "device_type": "cisco_ios_xe",
  "driver_mode": "manager",
  "commands": {
    "show inventory|textfsm": null,
    "show inventory": "..."
  },
  "expected": {
    "min_rows": 1,
    "parser_contains": "cisco_show_inventory",
    "contains_rows": [
      { "model_name": "C9300-48P" }
    ]
  }
}
```

Notes:
- `fixture_group` is optional. Use `domestic_switch` for Korea switch-focused suites.
- `fixture_group=global_switch` is used for global vendor switch/security appliance high fixtures.
- Use `*variant*` in `id` for parser stability replay cases
  (whitespace drift, column changes, missing fields).
- `driver_mode` is only used for `neighbors` and `facts`.
- `driver_mode=generic` forces `GenericDriver`.
- `commands` keys support `|textfsm` suffix.
- `expected` supports:
  - `min_rows`
  - `contains_rows`
  - `forbid_rows`
  - `required_protocols`
  - `parser_contains`
  - `driver_contains`
  - `facts_contains`

## Run benchmark

```bash
python Netsphere_Free_Backend/tools/run_vendor_parser_benchmark.py
```

Run domestic-switch-only suite:

```bash
python Netsphere_Free_Backend/tools/run_vendor_parser_benchmark.py --group domestic_switch
```

Run global-switch suite:

```bash
python Netsphere_Free_Backend/tools/run_vendor_parser_benchmark.py --group global_switch
```

Run variant-only replay guard:

```bash
cd Netsphere_Free_Backend
python -m pytest tests/synthetic/test_vendor_parser_replay_variants.py -q
```

Default report output:

`docs/reports/vendor-parser-benchmark.latest.json`
