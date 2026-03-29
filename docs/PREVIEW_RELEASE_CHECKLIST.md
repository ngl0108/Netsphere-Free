# NetSphere Free Release Checklist

## Secrets and internal data

Remove from preview build inputs:

- development API keys
- JWT secrets not intended for release
- license signing private keys
- webhook secrets
- test admin accounts and seed credentials
- SMTP tokens and connector tokens
- cloud access keys
- DB connection strings meant for internal environments
- SSH private keys
- internal URLs, office IPs, internal hostnames, internal email addresses
- sample data containing real customer information

Rule:

- do not mask these into the build
- exclude them from the build entirely

## Preview runtime settings

- set `NETSPHERE_EDITION=preview`
- choose `preview_deployment_role`
  - `collector_installed`
  - `intake_server`
- choose `preview_upload_target_mode`
  - `local_only`
  - `remote_only`
  - `dual_write`
- for installed collector:
  - set `preview_local_embedded_execution=true`
  - set `NETSPHERE_SERVE_FRONTEND_STATIC=true`
  - point `NETSPHERE_FRONTEND_DIST_DIR` at the built frontend
- enable `preview_capture_enabled`
- enable `preview_contribution_upload_enabled`
- keep `preview_contribution_opt_in_required=true`
- initialize `preview_contribution_participation=unset` for new installs
- keep `preview_contribution_require_consent=true`
- keep `preview_allow_device_capture=true`
- review `preview_collection_allowed_commands_json`
- if using intake_server:
  - set `preview_accept_remote_uploads=true`
- if using collector_installed remote upload:
  - set `preview_remote_upload_url`
  - keep `preview_self_registration_enabled=true`
  - leave `preview_remote_upload_client_id` blank in public builds
  - leave `preview_remote_upload_token` blank in public builds
- keep `ALLOW_DEV_LICENSE_FALLBACK=false` for all public preview builds

## Upload policy

- raw originals must not be persisted
- uploads must store sanitized outputs only
- product terms acceptance must be separate from upload opt-in
- upload opt-in must remain optional for product usage
- users must see preview before upload
- consent must be explicit
- uploaded bundle must include redaction summary
- intake credentials must be unique per install or per customer and support revocation
- public collector builds must not embed a shared static upload token

## Functional validation

- run `npm.cmd run e2e:free`
- login works
- first local administrator is created from the one-time bootstrap form or local bootstrap endpoint
- discovery works and remains aligned with the enterprise discovery flow
- topology works and remains aligned with the enterprise topology flow
- connected NMS flows work through inventory, device detail, diagnosis, notifications, and observability
- automation hub opens as a preview-safe experience hub
- device detail works
- preview contribution page loads
- first-run wizard shows required terms acceptance and optional contribution choice
- device capture runs only allowlisted commands
- manual paste sanitization works
- upload remains disabled until optional contribution opt-in is enabled
- upload stores sanitized bundle only
- blocked mutation routes return preview policy error

## What to spot-check manually

- no secrets shown in Settings export paths
- preview sidebar hides blocked admin surfaces
- config, policy, approval, fabric, cloud mutation pages are blocked in preview
- automation hub is visible, but network-changing automation execution is blocked in preview
- recent contribution list shows sanitized metadata only

## Distribution note

Label the package as:

- `NetSphere Free`
- `Parser Improvement Program`
- `Sanitized Raw Output Contribution`

Avoid marketing it as full enterprise GA.

Do not distribute the old Docker runtime bundle to customers.

## Installer distribution

- build `dist/preview-installer-stage`
- build `dist/preview-installer-exe/NetSphere-Free-Setup.exe`
- test install on a clean Windows account
- confirm desktop shortcut launches the collector
- confirm uninstall entry appears under current-user installed apps
- confirm no plaintext admin credential file is created on first install
- confirm upload opt-in triggers automatic collector registration when remote intake is configured
