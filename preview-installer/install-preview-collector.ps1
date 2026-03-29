param(
  [string]$EnvTarget = ".env.preview.local"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceEnv = Join-Path $repoRoot ".env.preview.example"
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
      if ([string]::IsNullOrWhiteSpace($currentValue) -or $currentValue -like "CHANGE_ME_*") {
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
  throw "Missing preview env example: $sourceEnv"
}

if (-not (Test-Path $targetEnv)) {
  Copy-Item $sourceEnv $targetEnv
}

$generatedSecret = New-UrlSafeSecret
$generatedFieldKey = New-FernetLikeKey
Ensure-EnvValue -Path $targetEnv -Key "SECRET_KEY" -Value $generatedSecret
Ensure-EnvValue -Path $targetEnv -Key "FIELD_ENCRYPTION_KEY" -Value $generatedFieldKey

Write-Host ""
Write-Host "NetSphere Free scaffold is ready."
Write-Host "Env file: $targetEnv"
Write-Host "Data dir : $dataDir"
Write-Host "Run dir  : $runDir"
Write-Host "Initial admin setup is now completed from the local login screen."
if (-not (Test-Path (Join-Path $frontendDist "index.html"))) {
  Write-Warning "Frontend build not found at $frontendDist"
  Write-Host "Run frontend build before starting the collector."
}
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Edit $EnvTarget"
Write-Host "2. Build frontend: npm.cmd run build"
Write-Host "3. Start NetSphere Free: .\\preview-installer\\start-preview-collector.ps1"
Write-Host "4. Open the UI: .\\preview-installer\\open-preview-ui.ps1"
Write-Host ""
Write-Host "Recommended customer-facing flow:"
Write-Host "- Start NetSphere Free from the desktop or start menu shortcut"
Write-Host "- Let the launcher open the browser automatically"
Write-Host "- Avoid asking users to type a localhost URL unless troubleshooting"
