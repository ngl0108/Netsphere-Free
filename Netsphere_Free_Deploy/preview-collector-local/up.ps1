param(
  [switch]$Build,
  [switch]$NoOpenBrowser
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$uiUrl = "http://localhost:18080"
$healthUrl = "$uiUrl/api/v1/auth/bootstrap/status"
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

function Wait-CollectorReady {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [int]$TimeoutSeconds = 60
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 5
      if ($response.StatusCode -eq 200) {
        return $true
      }
    } catch {
    }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)

  return $false
}

Push-Location $repoRoot
try {
  & docker @args
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose exited with code $LASTEXITCODE"
  }
} finally {
  Pop-Location
}

if (Wait-CollectorReady -Url $healthUrl) {
  Write-Host "NetSphere Free is ready." -ForegroundColor Green
  Write-Host "UI: $uiUrl" -ForegroundColor Green
  if (-not $NoOpenBrowser) {
    Start-Process $uiUrl | Out-Null
    Write-Host "Opened NetSphere Free in your default browser." -ForegroundColor Green
  }
} else {
  Write-Warning "NetSphere Free started, but the UI did not become ready within the expected time."
  Write-Host "Try opening $uiUrl manually after a few more seconds."
}
