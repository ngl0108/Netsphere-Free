param(
  [string]$EnvTarget = ".env.preview.collector-local"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceEnv = Join-Path $repoRoot ".env.preview.collector-local.example"
$targetEnv = Join-Path $repoRoot $EnvTarget
$dataDir = Join-Path $repoRoot "preview-installer\data"
$runDir = Join-Path $repoRoot "preview-installer\run"
$frontendDist = Join-Path $repoRoot "Netsphere_Free_Frontend\dist"

function New-UrlSafeSecret {
  param([int]$ByteCount = 48)
  $bytes = New-Object byte[] $ByteCount
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return ([Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")).TrimEnd("=")
}

function New-FernetLikeKey {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return ([Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_"))
}

function Ensure-EnvValue {
  param(
    [string]$Path,
    [string]$Key,
    [string]$Value
  )

  $pattern = "^(?i)$([regex]::Escape($Key))=.*$"
  $content = @()
  if (Test-Path $Path) {
    $content = Get-Content $Path
  }

  $updated = $false
  for ($i = 0; $i -lt $content.Count; $i++) {
    if ($content[$i] -match $pattern) {
      $currentValue = ($content[$i] -split "=", 2)[1]
      if ([string]::IsNullOrWhiteSpace($currentValue) -or $currentValue -like "CHANGE_ME*") {
        $content[$i] = "$Key=$Value"
      }
      $updated = $true
      break
    }
  }

  if (-not $updated) {
    $content += "$Key=$Value"
  }

  Set-Content -Path $Path -Value $content -Encoding utf8
}

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

if (-not (Test-Path $sourceEnv)) {
  throw "Missing collector-local env example: $sourceEnv"
}

if (-not (Test-Path $targetEnv)) {
  Copy-Item $sourceEnv $targetEnv
}

Ensure-EnvValue -Path $targetEnv -Key "SECRET_KEY" -Value (New-UrlSafeSecret)
Ensure-EnvValue -Path $targetEnv -Key "FIELD_ENCRYPTION_KEY" -Value (New-FernetLikeKey)

Write-Host ""
Write-Host "Preview collector-local test scaffold is ready."
Write-Host "Env file : $targetEnv"
Write-Host "Data dir : $dataDir"
Write-Host "Run dir  : $runDir"
if (-not (Test-Path (Join-Path $frontendDist "index.html"))) {
  Write-Warning "Frontend build not found at $frontendDist"
  Write-Host "Run npm.cmd run build before starting the collector-local container."
}
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Review $EnvTarget"
Write-Host "2. docker compose -f docker-compose.preview-collector-local.yml up -d --build"
Write-Host "3. Open http://127.0.0.1:18080"
