# NetSphere Free Deploy

이 레포에서는 `preview-collector-local`만 사용합니다.

## 주요 스크립트

- `Netsphere_Free_Deploy/preview-collector-local/up.ps1`
- `Netsphere_Free_Deploy/preview-collector-local/down.ps1`
- `Netsphere_Free_Deploy/preview-collector-local/logs.ps1`
- `Netsphere_Free_Deploy/preview-collector-local/smoke.ps1`
- `Netsphere_Free_Deploy/preview-collector-local/validate-contribution-flow.ps1`

## 실행

```powershell
powershell -ExecutionPolicy Bypass -File .\Netsphere_Free_Deploy\preview-collector-local\up.ps1 -Build
```
