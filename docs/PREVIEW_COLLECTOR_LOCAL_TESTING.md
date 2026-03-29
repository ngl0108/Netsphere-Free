# Preview Collector Local Testing

## Goal

Run a Docker-based local `collector_installed` role on the same PC so the Free upload flow can be tested before distributing the Windows installer.

Primary operator entry point:

- `Netsphere_Free_Deploy/preview-collector-local`

This does **not** replace full EXE testing. It is a fast same-machine validation path for:

- preview onboarding
- local sanitize preview
- self-registration
- remote upload to the intake server
- Free route gating

## What it starts

- one backend container in `collector_installed` mode
- SQLite state under `preview-installer/data`
- built frontend served directly by the backend

The intake server remains separate and should already be running on the host.

## 1. Bootstrap the local collector env

```powershell
.\Netsphere_Free_Deploy\preview-collector-local\bootstrap.ps1
```

This creates `.env.preview.collector-local` from the example and fills in local secrets if they are still placeholders.

## 2. Review the env file

Key values:

- `PREVIEW_DEPLOYMENT_ROLE=collector_installed`
- `PREVIEW_UPLOAD_TARGET_MODE=remote_only`
- `PREVIEW_REMOTE_UPLOAD_URL=http://host.docker.internal:8015/api/v1/preview/contributions`
- `PREVIEW_SELF_REGISTRATION_ENABLED=true`

## 3. Build the frontend

```powershell
npm.cmd run build
```

## 4. Start the collector-local container

```powershell
.\Netsphere_Free_Deploy\preview-collector-local\up.ps1 -Build
```

Open:

- `http://127.0.0.1:18080`

Docker Desktop project name:

- `netsphere-preview-collector`

## 5. What to test

1. one-time local administrator creation
2. product terms acceptance
3. discovery / topology / diagnosis surface loads
4. contribution opt-in stays optional
5. manual paste sanitize preview works
6. self-registration succeeds
7. sanitized upload succeeds

## 6. Server-side confirmation

After upload, check the intake host storage:

- `Netsphere_Free_Backend/preview_contributions`

Expected:

- a new `preview-*.json` file appears
- only sanitized values are stored

## 7. Stop and clean up

```powershell
.\Netsphere_Free_Deploy\preview-collector-local\down.ps1
```

Logs:

```powershell
.\Netsphere_Free_Deploy\preview-collector-local\logs.ps1
```

If you want a clean collector state for another pass, remove the local SQLite file under:

- `preview-installer/data`

## What this validates

- the Free role itself
- sanitize-before-upload behavior
- remote intake enrollment
- remote sanitized bundle upload

## What this does not fully validate

- the EXE installer shell experience
- Windows desktop/start-menu shortcuts
- uninstall behavior
- real customer-PC environmental differences
