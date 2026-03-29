# Runtime Data Boundaries

## Purpose

This document explains which parts of the Free repository own runtime data and what should be treated as disposable versus retained.

## Free repository runtime boundary

| Component | Primary purpose | Runtime data | Backup required | Notes |
| --- | --- | --- | --- | --- |
| `preview-collector-local` | same-PC Free collector validation harness | local SQLite state, local preview runtime data, test bootstrap state | No for routine operations | treat as disposable unless debugging a collector issue |
| `preview upload configuration` | local upload configuration used by the Free collector | local env values and installer/runtime settings | Yes when reused | do not commit secrets or organization-specific endpoints |

## Owns

- local collector runtime state
- local preview installer runtime folders used for Free validation
- local sanitize preview state
- upload configuration for sanitized bundle forwarding

## Recommended backup targets

- `.env.preview.collector-local` only when it contains reusable non-secret operator defaults
- installer/runtime notes needed to reproduce a packaging issue

## Do not treat as routine backup targets

- disposable collector-local SQLite state
- transient Docker cache
- generated local test logs
- generated scenario-lab report files

## Storage location summary

- local SQLite under the preview installer data path
- local runtime folders used by the collector-local harness
- role env file: `.env.preview.collector-local`
- local sanitized preview artifacts reviewed before upload

## Operator rule of thumb

- If the data exists only to validate a Free collector build on one PC, treat it as disposable.
- If the data captures reusable runtime configuration for future Free packaging or validation, preserve it outside source control.
