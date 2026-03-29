param(
  [string]$InstallDir = "",
  [switch]$Quiet,
  [switch]$NoLaunch,
  [switch]$SkipShellIntegration
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
  $InstallDir = Join-Path $env:LOCALAPPDATA "NetSphere Free"
}

$payloadZip = Join-Path $PSScriptRoot "payload.zip"
$expandRoot = Join-Path $env:TEMP "netsphere-preview-installer-expand"
$expandedPayloadDir = Join-Path $expandRoot "payload"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "NetSphere Free.lnk"
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\NetSphere Free"
$launchCmd = Join-Path $InstallDir "preview-installer\launch-preview-collector.cmd"
$openCmd = Join-Path $InstallDir "preview-installer\open-preview-ui.cmd"
$stopCmd = Join-Path $InstallDir "preview-installer\stop-preview-collector.cmd"
$uninstallCmd = Join-Path $InstallDir "preview-installer\uninstall-preview-collector.cmd"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NetSphereFree"
$legacyDesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "NetSphere Preview.lnk"
$legacyStartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\NetSphere Preview"
$legacyUninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\NetSpherePreview"

function New-Shortcut {
  param(
    [string]$ShortcutPath,
    [string]$TargetPath,
    [string]$WorkingDirectory,
    [string]$Description
  )

  $shell = New-Object -ComObject WScript.Shell
  $shortcut = $shell.CreateShortcut($ShortcutPath)
  $shortcut.TargetPath = $TargetPath
  $shortcut.WorkingDirectory = $WorkingDirectory
  $shortcut.Description = $Description
  $shortcut.Save()
}

if (-not (Test-Path $payloadZip)) {
  throw "Installer payload not found: $payloadZip"
}

if (Test-Path $expandRoot) {
  Remove-Item $expandRoot -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $expandedPayloadDir | Out-Null
Expand-Archive -Path $payloadZip -DestinationPath $expandedPayloadDir -Force

$existingStopScript = Join-Path $InstallDir "preview-installer\stop-preview-collector.ps1"
if (Test-Path $existingStopScript) {
  try {
    & $existingStopScript | Out-Null
  } catch {
  }
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path (Join-Path $expandedPayloadDir "*") -Destination $InstallDir -Recurse -Force

$installScript = Join-Path $InstallDir "preview-installer\install-preview-collector.ps1"
if (-not (Test-Path $installScript)) {
  throw "Installed collector scaffold script not found: $installScript"
}
& $installScript | Out-Null

if (-not $SkipShellIntegration) {
  Remove-Item $legacyDesktopShortcut -Force -ErrorAction SilentlyContinue
  Remove-Item $legacyStartMenuDir -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $legacyUninstallKey -Recurse -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
  New-Shortcut -ShortcutPath $desktopShortcut -TargetPath $launchCmd -WorkingDirectory $InstallDir -Description "Launch NetSphere Free"
  New-Shortcut -ShortcutPath (Join-Path $startMenuDir "NetSphere Free.lnk") -TargetPath $launchCmd -WorkingDirectory $InstallDir -Description "Launch NetSphere Free"
  New-Shortcut -ShortcutPath (Join-Path $startMenuDir "Open NetSphere Free UI.lnk") -TargetPath $openCmd -WorkingDirectory $InstallDir -Description "Open NetSphere Free UI"
  New-Shortcut -ShortcutPath (Join-Path $startMenuDir "Stop NetSphere Free.lnk") -TargetPath $stopCmd -WorkingDirectory $InstallDir -Description "Stop NetSphere Free"
  New-Shortcut -ShortcutPath (Join-Path $startMenuDir "Uninstall NetSphere Free.lnk") -TargetPath $uninstallCmd -WorkingDirectory $InstallDir -Description "Uninstall NetSphere Free"

  New-Item -Path $uninstallKey -Force | Out-Null
  Set-ItemProperty -Path $uninstallKey -Name "DisplayName" -Value "NetSphere Free"
  Set-ItemProperty -Path $uninstallKey -Name "DisplayVersion" -Value "2.5.0-free"
  Set-ItemProperty -Path $uninstallKey -Name "Publisher" -Value "NetSphere"
  Set-ItemProperty -Path $uninstallKey -Name "InstallLocation" -Value $InstallDir
  Set-ItemProperty -Path $uninstallKey -Name "UninstallString" -Value $uninstallCmd
  Set-ItemProperty -Path $uninstallKey -Name "DisplayIcon" -Value $launchCmd
  Set-ItemProperty -Path $uninstallKey -Name "NoModify" -Value 1 -Type DWord
  Set-ItemProperty -Path $uninstallKey -Name "NoRepair" -Value 1 -Type DWord
}

if (-not $Quiet) {
  Write-Host "NetSphere Free installed."
  Write-Host "Install dir: $InstallDir"
  Write-Host "Desktop shortcut created."
}

if (-not $NoLaunch -and (Test-Path $launchCmd)) {
  Start-Process -FilePath $launchCmd -WorkingDirectory $InstallDir | Out-Null
}
