param(
  [int]$Tail = 120
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $repoRoot
try {
  & docker compose -p netsphere-preview-collector -f docker-compose.preview-collector-local.yml logs --tail=$Tail
} finally {
  Pop-Location
}
