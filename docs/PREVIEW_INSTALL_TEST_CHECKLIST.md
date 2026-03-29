# NetSphere Free Install Test Checklist

This checklist is the practical acceptance flow for the current Windows Free build.

Primary installer:

- `dist/preview-installer-exe/NetSphere-Free-Setup.exe`

## 1. Server readiness

Before you touch the installer, confirm the services that NetSphere Free depends on are already running.

Required checks:

1. Main API responds:
   - `http://127.0.0.1:8000`
2. NetSphere Cloud upload service responds:
   - `http://127.0.0.1:8015`
3. Public bootstrap endpoint responds:
   - `https://netsphereapp.com/api/v1/auth/bootstrap/status`

Expected result:

- all three return `200`

## 2. Install the Free client

1. Run `NetSphere-Free-Setup.exe`.
2. Finish the installer without errors.
3. Launch `NetSphere Free` from the desktop or start menu shortcut.
4. Confirm the browser opens the local UI.

Expected result:

- install succeeds
- shortcut starts the app
- local UI loads in the browser

## 3. First-run onboarding

1. Confirm the login page shows the one-time initial administrator form.
2. Create the first local administrator.
3. Sign in.
4. Accept the product terms.
5. Leave contribution upload disabled for the first pass.

Expected result:

- first admin creation succeeds
- sign-in succeeds
- terms acceptance succeeds
- product remains usable without contribution opt-in

## 4. Core Free surface check

Open each of these pages once and confirm the page renders without blocking messages:

1. `Discovery`
2. `Topology`
3. `Devices`
4. `Diagnosis`
5. `Notifications`
6. `Observability`
7. `Data Contribution`

Expected result:

- Free-allowed pages load normally
- no Pro-only policy block appears on these pages

## 5. Auto Discovery flow

1. Open `Discovery`.
2. Enter a seed IP or CIDR that is safe for the test environment.
3. Start a scan.
4. Watch the job state until completion or a handled failure state.

Check:

- scan request is accepted
- loading/progress states are understandable
- failure text is readable if the target is unavailable
- successful output can be reviewed from the results area

## 6. Auto Topology flow

1. Open `Topology`.
2. Confirm the topology canvas loads.
3. Click a node if one is present.
4. Confirm the node context panel opens.
5. Use one of the context actions if available:
   - open device
   - open observability
   - open Grafana

Expected result:

- map renders
- node context is readable
- topology remains part of the same NMS workflow

## 7. Basic NMS / diagnosis flow

1. Open `Devices` and review the list.
2. Open a device detail page if a device exists.
3. Open `Diagnosis`.
4. Open `Notifications`.
5. Open `Observability`.

Expected result:

- device list and detail are readable
- diagnosis loads
- notifications load
- observability loads

## 8. Local sanitization test

1. Open `Data Contribution`.
2. Choose `Manual paste`.
3. Select `show version`.
4. Paste the sample below:

```text
hostname edge-sw-01
Mgmt IP: 10.10.1.12
SN: FDO1234ABCD
Contact: admin@example.com
snmp community public-secret
```

5. Build the sanitized preview.

Expected result:

- the preview does not contain the original hostname
- the preview does not contain the original IP
- the preview does not contain the original serial
- the preview does not contain the original email
- the preview does not contain the original secret

Typical masked values:

- `HOST_001`
- `IP_001`
- `SERIAL_001`
- `EMAIL_001`
- `<REDACTED_SECRET>`

## 9. Upload block test

Keep contribution upload disabled and try to upload.

Expected result:

- upload is blocked
- the rest of the product remains usable

## 10. Contribution opt-in and upload test

1. Enable optional contribution upload.
2. Allow self-registration to complete automatically.
3. Confirm the consent checkbox is required per bundle.
4. Upload the sanitized bundle.

Expected result:

- registration completes without manual token entry
- upload succeeds only after explicit opt-in and consent
- success feedback appears in the UI

## 11. Server-side verification

On the host server:

1. Open `Netsphere_Free_Backend/preview_contributions`.
2. Confirm a new `preview-*.json` file exists.
3. Inspect the stored JSON.

Expected result:

- only sanitized data is stored
- original hostname is not stored
- original IP is not stored
- original serial is not stored
- original email is not stored
- original secret is not stored

## 12. Free / Pro boundary test

Try opening Pro-only routes directly:

- `/settings`
- `/approval`
- `/cloud/accounts`

Expected result:

- blocked Pro surfaces show a policy message in Free
- allowed Free surfaces continue to work normally

## 13. Pass criteria

NetSphere Free is acceptable for installer testing when all of the following are true:

- install succeeds
- first-run onboarding succeeds
- discovery, topology, and core NMS surfaces load
- the product remains usable without contribution opt-in
- local sanitization works
- contribution upload succeeds only after opt-in and explicit consent
- the cloud upload service stores sanitized data only
- Pro-only routes remain blocked in Free
