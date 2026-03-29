# Reports Retention

`docs/reports` keeps only the current evidence files that are meant to be read directly.

## Keep at the root

- `*-latest.json`
- `*-latest.md`
- `northbound-soak-72h-run-state.json`
- `northbound-soak-probe.progress.log`
- `real-device-acceptance-checklist.latest.csv`
- `vendor-parser-benchmark.latest.json`

## Archive policy

- Timestamped historical exports move to `docs/reports/archive/<timestamp>/root-files/`
- Completed validation folders such as `daily`, `soak`, and `signoff-bundles` move to `docs/reports/archive/<timestamp>/legacy-dirs/`
- The cleanup tool is `Netsphere_Free_Backend/tools/cleanup_generated_reports.py`

## Intention

The root report folder should stay readable for operators and sales packaging, while old signoff artifacts remain preserved for traceability.
