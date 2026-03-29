param()

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $repoRoot "preview-installer\run\collector.pid"

if (-not (Test-Path $pidFile)) {
  Write-Host "NetSphere Free is not running."
  exit 0
}

$collectorPid = Get-Content $pidFile -ErrorAction SilentlyContinue
if ($collectorPid) {
  $process = Get-Process -Id $collectorPid -ErrorAction SilentlyContinue
  if ($process) {
    Stop-Process -Id $collectorPid -Force
    Write-Host "Stopped NetSphere Free PID $collectorPid."
  } else {
    Write-Host "The stored NetSphere Free PID no longer exists."
  }
}

Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
