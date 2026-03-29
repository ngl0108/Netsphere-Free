# NetSphere Preview Collector Local

This is the official same-PC test path for the Free collector role.

Use this before shipping or updating the Windows Free installer when you do not have a second test PC.

What it validates:

- first-run bootstrap
- login and terms acceptance
- preview policy and route gating
- local sanitization
- contribution opt-in
- self-registration
- remote upload to the intake server

What it does not fully replace:

- EXE install wizard shell behavior
- shortcut creation
- uninstall behavior

## Required prerequisites

- intake server already running
- frontend build available

## Commands

Bootstrap local env:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\bootstrap.ps1
```

Validate env:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\check-env.ps1
```

Start:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\up.ps1
```

Open:

- `http://localhost:18080`

The `up.ps1` script opens the browser automatically when the UI becomes ready.
Treat the URL as a fallback for troubleshooting, not as the primary customer instruction.

Recommended operator instruction:

- "Run NetSphere Free"
- "The browser will open automatically"

If you prefer not to auto-open the browser, use:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\up.ps1 -NoOpenBrowser
```

Stop:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\down.ps1
```

Logs:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\logs.ps1
```

Smoke:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\smoke.ps1
```

Contribution flow validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\validate-contribution-flow.ps1
```

This runs the same-PC Free collector path through:

- bootstrap status check
- login
- contribution opt-in
- sanitize preview
- remote upload
- intake storage confirmation

It also proves that:

- raw output is reviewed locally before upload
- the masked bundle is forwarded to the intake role in `remote_only` mode
- the intake role persists a new sanitized contribution record
