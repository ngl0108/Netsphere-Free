param(
  [string]$EnvFile = ".env.preview.local",
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

function Set-DotEnvVariables {
  param([string]$Path)
  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) { return }
    [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
  }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendRoot = Join-Path $repoRoot "Netsphere_Free_Backend"
$frontendDist = Join-Path $repoRoot "Netsphere_Free_Frontend\dist"
$dataDir = Join-Path $repoRoot "preview-installer\data"
$runDir = Join-Path $repoRoot "preview-installer\run"
$pidFile = Join-Path $runDir "collector.pid"
$stdoutLog = Join-Path $runDir "collector.stdout.log"
$stderrLog = Join-Path $runDir "collector.stderr.log"
$envPath = Join-Path $repoRoot $EnvFile

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

if (-not (Test-Path $envPath)) {
  throw "Missing env file: $envPath"
}

if (-not (Test-Path (Join-Path $frontendDist "index.html"))) {
  throw "Frontend build not found: $frontendDist"
}

if (Test-Path $pidFile) {
  $existingPid = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($existingPid) {
    $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
      Write-Host "NetSphere Free is already running (PID $existingPid)."
      exit 0
    }
  }
}

Set-DotEnvVariables -Path $envPath
[string]$deploymentRole = if ([string]::IsNullOrWhiteSpace($env:PREVIEW_DEPLOYMENT_ROLE)) { "collector_installed" } else { $env:PREVIEW_DEPLOYMENT_ROLE }
[string]$uploadTargetMode = if ([string]::IsNullOrWhiteSpace($env:PREVIEW_UPLOAD_TARGET_MODE)) { "remote_only" } else { $env:PREVIEW_UPLOAD_TARGET_MODE }
[string]$localEmbeddedExecution = if ([string]::IsNullOrWhiteSpace($env:PREVIEW_LOCAL_EMBEDDED_EXECUTION)) { "true" } else { $env:PREVIEW_LOCAL_EMBEDDED_EXECUTION }
[string]$disableIntegratedServers = if ([string]::IsNullOrWhiteSpace($env:PREVIEW_DISABLE_INTEGRATED_SERVERS)) { "true" } else { $env:PREVIEW_DISABLE_INTEGRATED_SERVERS }
[string]$databaseUrl = $env:DATABASE_URL
if ([string]::IsNullOrWhiteSpace($databaseUrl) -or $databaseUrl -like "sqlite:///./preview-installer/*") {
  $dbPath = (Join-Path $dataDir "netsphere-preview.db").Replace("\", "/")
  $databaseUrl = "sqlite:///$dbPath"
}
[System.Environment]::SetEnvironmentVariable("NETSPHERE_EDITION", "preview", "Process")
[System.Environment]::SetEnvironmentVariable("PREVIEW_DEPLOYMENT_ROLE", $deploymentRole, "Process")
[System.Environment]::SetEnvironmentVariable("PREVIEW_UPLOAD_TARGET_MODE", $uploadTargetMode, "Process")
[System.Environment]::SetEnvironmentVariable("PREVIEW_LOCAL_EMBEDDED_EXECUTION", $localEmbeddedExecution, "Process")
[System.Environment]::SetEnvironmentVariable("PREVIEW_DISABLE_INTEGRATED_SERVERS", $disableIntegratedServers, "Process")
[System.Environment]::SetEnvironmentVariable("DATABASE_URL", $databaseUrl, "Process")
[System.Environment]::SetEnvironmentVariable("PYTHONPATH", $backendRoot, "Process")
[System.Environment]::SetEnvironmentVariable("NETSPHERE_SERVE_FRONTEND_STATIC", "true", "Process")
[System.Environment]::SetEnvironmentVariable("NETSPHERE_FRONTEND_DIST_DIR", $frontendDist, "Process")
[System.Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "Process")

$pythonExecutable = $null
$bundledPythonHome = Join-Path $repoRoot "runtime\python"
$bundledPython = Join-Path $bundledPythonHome "python.exe"
if (Test-Path $bundledPython) {
  $pythonExecutable = $bundledPython
  [System.Environment]::SetEnvironmentVariable("PYTHONHOME", $bundledPythonHome, "Process")
  $pathParts = @(
    $bundledPythonHome,
    (Join-Path $bundledPythonHome "DLLs"),
    [System.Environment]::GetEnvironmentVariable("PATH", "Process")
  ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
  [System.Environment]::SetEnvironmentVariable("PATH", ($pathParts -join ";"), "Process")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonExecutable = (Get-Command python).Source
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  $pythonExecutable = (& py -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
}

if (-not $pythonExecutable) {
  throw "Python runtime was not found. Install Python before starting NetSphere Free."
}

$args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
$process = Start-Process -FilePath $pythonExecutable -ArgumentList $args -WorkingDirectory $repoRoot -PassThru -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
Start-Sleep -Seconds 3
$running = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
if (-not $running) {
  $stderrTail = ""
  if (Test-Path $stderrLog) {
    $stderrTail = (Get-Content $stderrLog -Tail 40 -ErrorAction SilentlyContinue | Out-String)
  }
  throw "NetSphere Free failed to stay running.`n$stderrTail"
}
Set-Content -Path $pidFile -Value $process.Id -Encoding ascii

Write-Host "NetSphere Free started."
Write-Host "PID     : $($process.Id)"
Write-Host "UI      : http://127.0.0.1:$Port"
Write-Host "API Docs: http://127.0.0.1:$Port/docs"
