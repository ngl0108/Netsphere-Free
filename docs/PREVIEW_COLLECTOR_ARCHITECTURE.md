# Preview Collector Architecture

## Goal

Use the same product codebase in two operational roles:

- `collector_installed`
- `intake_server`

The installed collector runs near the customer network and performs discovery, topology, connected NMS, and sanitized raw-output contribution.

The intake server runs on the NetSphere side and receives masked bundles for parser improvement.

## Deployment roles

### Installed collector

- runs the preview UI and local preview backend
- scans the customer network from the local workstation or jump host
- uses embedded local execution for discovery, crawl, and topology refresh
- serves the built frontend directly from the backend runtime
- sanitizes raw output locally before upload
- self-registers with the remote intake after the user explicitly opts in to masked contribution upload
- stores the issued `collector_id + intake_token` locally in encrypted system settings
- forwards sanitized bundles to the remote intake with the issued collector credentials

### Intake server

- runs the central preview backend
- accepts remote collector uploads
- stores sanitized bundles only
- does not need direct access to customer devices

## Upload model

The collector uses the same `/api/v1/preview/contributions` path as the standalone preview flow.

Upload target modes:

- `local_only`
- `remote_only`
- `dual_write`

Recommended defaults:

- installed collector: `remote_only`
- intake server: `local_only`

The collector must separate:

- required product terms acceptance
- optional contribution upload opt-in

This keeps discovery, topology, and connected NMS available even when contribution upload stays disabled.

## Security model

- raw originals are never persisted
- the collector sanitizes before upload
- the collector keeps upload disabled until optional contribution opt-in is recorded
- the collector does not ship with a static shared intake token
- the collector auto-enrolls only after the user opts in to masked uploads
- the intake accepts uploads only when `preview_accept_remote_uploads=true`
- the intake can allow self-registration when `preview_self_registration_enabled=true`
- the intake requires both `X-Preview-Collector-Id` and `X-Preview-Intake-Token`
- the intake stores only hashed registration tokens and supports rotation/revocation per collector
- discovery, topology, inventory, and diagnosis stay on the same codebase as enterprise
- preview blocks config deploy, rollback, policy push, and privileged secret mutation

## Installer-oriented runtime files

- `.env.preview.example`
- `preview-installer/bootstrap-install.ps1`
- `preview-installer/bootstrap-install.cmd`
- `preview-installer/install-preview-collector.ps1`
- `preview-installer/launch-preview-collector.cmd`
- `preview-installer/open-preview-ui.ps1`
- `preview-installer/open-preview-ui.cmd`
- `preview-installer/start-preview-collector.ps1`
- `preview-installer/start-preview-collector.cmd`
- `preview-installer/stop-preview-collector.ps1`
- `preview-installer/stop-preview-collector.cmd`
- `preview-installer/uninstall-preview-collector.ps1`
- `preview-installer/uninstall-preview-collector.cmd`

## Installer outputs

- `dist/preview-installer-stage`
- `dist/preview-installer-exe/NetSphere-Free-Setup.exe`

## Recommended rollout

1. Stand up the intake server first.
2. Publish the intake HTTPS URL in the collector build.
3. Build and distribute the Windows setup executable.
4. Let users run discovery, topology, and connected NMS locally.
5. When users opt in, let the collector self-register and receive a per-install `collector_id + intake_token`.
6. Receive sanitized bundles centrally and feed them into parser improvement.
