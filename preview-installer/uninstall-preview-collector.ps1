param(
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$installRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stopScript = Join-Path $PSScriptRoot "stop-preview-collector.ps1"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "NetSphere Free.lnk"
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\NetSphere Free"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NetSphereFree"
$legacyDesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "NetSphere Preview.lnk"
$legacyStartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\NetSphere Preview"
$legacyUninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NetSpherePreview"

if (Test-Path $stopScript) {
  try {
    & $stopScript | Out-Null
  } catch {
  }
}

Remove-Item $desktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item $startMenuDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $uninstallKey -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $legacyDesktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item $legacyStartMenuDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $legacyUninstallKey -Recurse -Force -ErrorAction SilentlyContinue

$cleanupScript = @"
Start-Sleep -Seconds 2
if (Test-Path '$installRoot') {
  Remove-Item -LiteralPath '$installRoot' -Recurse -Force -ErrorAction SilentlyContinue
}
"@

Start-Process -FilePath "powershell.exe" -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy",
  "Bypass",
  "-Command",
  $cleanupScript
) -WindowStyle Hidden | Out-Null

if (-not $Quiet) {
  Write-Host "NetSphere Free uninstall has started."
  Write-Host "Installation directory cleanup will continue in the background."
}
