param(
  [switch]$Build
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$args = @(
  "compose",
  "-p", "netsphere-preview-collector",
  "-f", "docker-compose.preview-collector-local.yml",
  "up",
  "-d"
)
if ($Build) {
  $args += "--build"
}
Push-Location $repoRoot
try {
  & docker @args
} finally {
  Pop-Location
}
