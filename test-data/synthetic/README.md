# Synthetic Test Data

This folder is reserved for test-only datasets and must not be used as production seed data.

## Structure

- `scenarios/normal.json`
- `scenarios/large_scale.json`
- `scenarios/failure.json`
- `scenarios/security_incident.json`
- `digital-twin/snmp.json`
- `digital-twin/ssh.json`
- `digital-twin/gnmi.json`
- `manifest.json`

## Regenerate

From repository root:

```bash
python Netsphere_Free_Backend/tools/generate_synthetic_fixtures.py --seed 20260219
```

Use a different `--seed` only when you intentionally update the baseline fixture set.
