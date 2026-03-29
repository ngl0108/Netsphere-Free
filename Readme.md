# NetSphere Free

This repository contains the public Free edition workspace for NetSphere.

Included in this repository:

- `Netsphere_Free_Backend/`
- `Netsphere_Free_Frontend/`
- `Netsphere_Free_Deploy/preview-collector-local/`
- `preview-installer/`
- `docker-compose.preview-collector-local.yml`
- `scenario-lab/`

Primary use cases:

- Auto Discovery
- Auto Topology
- Connected NMS
- same-PC collector validation before packaging the Windows installer

Start the local Free runtime:

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\up.ps1 -Build
```

Open:

- `http://127.0.0.1:18080`

Notes:

- This repository is intended to stay public.
- Pro-only deployment assets, private licensing helpers, and internal-only release material should not be added here.
- When a shared feature is stabilized in Pro and is meant to exist in Free, port it intentionally instead of copying the whole Pro stack.
