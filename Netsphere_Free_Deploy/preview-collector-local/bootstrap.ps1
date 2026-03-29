$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $repoRoot
try {
  & powershell -ExecutionPolicy Bypass -File .\preview-installer\bootstrap-preview-collector-local.ps1
} finally {
  Pop-Location
}
