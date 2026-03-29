param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\_common.ps1")

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = Join-Path $repoRoot ".env.preview.collector-local"

Assert-RequiredEnvValues -Path $envPath -RequiredKeys @(
  "PREVIEW_DEPLOYMENT_ROLE",
  "PREVIEW_UPLOAD_TARGET_MODE",
  "PREVIEW_REMOTE_UPLOAD_URL",
  "SECRET_KEY",
  "FIELD_ENCRYPTION_KEY"
)

$frontendDist = Join-Path $repoRoot "Netsphere_Free_Frontend\dist\index.html"
if (-not (Test-Path $frontendDist)) {
  throw "Missing frontend build artifact: $frontendDist"
}
Write-Host "Frontend build artifact found." -ForegroundColor Green
