# Free Public Repo Checklist

Use this checklist before pushing the Free repository to a public remote.

## Keep

- Free collector runtime
- Free frontend and backend
- same-PC collector validation scripts
- preview installer packaging assets that belong to Free distribution
- public-facing documentation for discovery, topology, connected NMS, and sanitized upload behavior

## Remove or review before every public push

- private keys, certificates, or signing material
- internal release runbooks meant only for Pro production operations
- tooling that issues licenses or generates signing keys
- documentation that exposes private infrastructure layout or internal-only hosting assumptions
- environment files with real secrets

## Current split status

- obvious Pro-only runbooks removed
- license issuing and key generation helpers removed
- generated test reports removed
- split runtime paths renamed to `Netsphere_Free_*`

## Still review manually

- docs for wording that assumes a private operator audience
- test-data for customer-specific values before publishing
- scenario-lab scripts for any cross-repo assumptions
