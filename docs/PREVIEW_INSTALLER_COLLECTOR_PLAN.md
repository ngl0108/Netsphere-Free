# Preview Installer Collector Plan

## Goal

Ship the preview collector as a Windows installer instead of a Docker runtime.

The installed collector must let the user:

- run auto discovery
- inspect auto topology
- use connected NMS read-only flows
- preview sanitized raw-output contribution
- upload masked parser-improvement bundles to the central intake

## Distribution model

- build a staged runtime from the current repository
- bundle a Windows Python runtime inside the installer
- ship the built frontend with the backend runtime
- install into `%LOCALAPPDATA%\NetSphere Preview Collector`
- launch the UI from a desktop shortcut

## Installed layout

- `Netsphere_Free_Backend/app`
- `Netsphere_Free_Frontend/dist`
- `preview-installer/*.ps1`
- `preview-installer/*.cmd`
- `runtime/python`
- `.env.preview.example`

## Runtime behavior

- role: `collector_installed`
- upload mode: `remote_only`
- local embedded execution: enabled
- integrated listeners: disabled by default
- raw originals: never persisted
- install scaffold generates an initial bootstrap admin credential file

## Installer outputs

- `dist/preview-installer-stage`
- `dist/preview-installer-package.zip`
- `dist/preview-installer-exe/NetSphere-Free-Setup.exe`

## Build steps

1. Build frontend assets.
2. Build installer stage with bundled Python runtime.
3. Wrap the stage into `payload.zip`.
4. Build the Windows setup executable with `IExpress`.
5. Smoke-test install, start, open UI, and uninstall.

## What remains outside the installer

- central intake server hosting
- intake token issuance
- parser triage and fixture promotion workflow
