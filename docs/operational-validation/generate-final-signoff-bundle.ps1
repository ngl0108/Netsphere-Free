param(
  [string]$OutputDir = 'docs/reports/signoff-bundles',
  [int]$DailyLimit = 40
)

$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path '.').Path
$reportsDir = Join-Path $repo 'docs/reports'
$dailyDir = Join-Path $reportsDir 'daily'
$outDir = Join-Path $repo $OutputDir
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Get-LatestFile {
  param([string]$Dir, [string]$Pattern)
  if (-not (Test-Path $Dir)) { return $null }
  return Get-ChildItem -Path $Dir -File -Filter $Pattern -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bundleRoot = Join-Path $outDir ("signoff-bundle-$stamp")
$bundleReports = Join-Path $bundleRoot 'reports'
$bundleDaily = Join-Path $bundleReports 'daily'
New-Item -ItemType Directory -Force -Path $bundleDaily | Out-Null

$include = @()

$latestSoakJson = Get-LatestFile -Dir $reportsDir -Pattern 'northbound-soak-72h-latest.json'
$latestSoakMd   = Get-LatestFile -Dir $reportsDir -Pattern 'northbound-soak-72h-latest.md'
$latestKpiJson  = Get-LatestFile -Dir $reportsDir -Pattern 'kpi-readiness-30d-latest.json'
$latestKpiMd    = Get-LatestFile -Dir $reportsDir -Pattern 'kpi-readiness-30d-latest.md'
$latestSuiteJson = Get-LatestFile -Dir $dailyDir -Pattern '*-all-cloud-suite-*.json'
$latestSuiteMd   = Get-LatestFile -Dir $dailyDir -Pattern '*-all-cloud-suite-*.md'
$runState       = Get-LatestFile -Dir $reportsDir -Pattern 'northbound-soak-72h-run-state.json'
$progressLog    = Get-LatestFile -Dir (Join-Path $reportsDir 'soak') -Pattern 'northbound-soak-72h-progress.log'
$runLog         = Get-LatestFile -Dir (Join-Path $reportsDir 'soak') -Pattern 'northbound-soak-72h-run.log'

$coreFiles = @($latestSoakJson,$latestSoakMd,$latestKpiJson,$latestKpiMd,$latestSuiteJson,$latestSuiteMd,$runState,$progressLog,$runLog) |
  Where-Object { $null -ne $_ }

foreach ($f in $coreFiles) {
  $dest = Join-Path $bundleReports $f.Name
  Copy-Item -Path $f.FullName -Destination $dest -Force
  $include += $dest
}

if (Test-Path $dailyDir) {
  $dailyFiles = Get-ChildItem -Path $dailyDir -File |
    Where-Object { $_.Name -match 'daily-signoff-.*\\.json$' -or $_.Name -match '-backend\\.log$' -or $_.Name -match '-celery-worker\\.log$' -or $_.Name -match '-celery-beat\\.log$' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First $DailyLimit

  foreach ($f in $dailyFiles) {
    $dest = Join-Path $bundleDaily $f.Name
    Copy-Item -Path $f.FullName -Destination $dest -Force
    $include += $dest
  }
}

$manifestItems = @()
foreach ($p in $include | Sort-Object -Unique) {
  $fi = Get-Item $p
  $hash = (Get-FileHash -Path $p -Algorithm SHA256).Hash
  $manifestItems += [ordered]@{
    file = $fi.FullName.Replace($bundleRoot + [IO.Path]::DirectorySeparatorChar, '')
    size_bytes = [int64]$fi.Length
    last_write_time = $fi.LastWriteTime.ToString('o')
    sha256 = $hash
  }
}

$manifest = [ordered]@{
  generated_at = (Get-Date).ToString('o')
  bundle_root = $bundleRoot
  files_count = $manifestItems.Count
  files = $manifestItems
}

$manifestPath = Join-Path $bundleRoot 'manifest.json'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Path $manifestPath -Encoding UTF8

$summaryPath = Join-Path $bundleRoot 'SUMMARY.md'
$lines = @()
$lines += '# Final Signoff Bundle Summary'
$lines += ''
$lines += "- generated_at: $($manifest.generated_at)"
$lines += "- files_count: $($manifest.files_count)"
$lines += "- bundle_root: $bundleRoot"
$lines += ''
$lines += '## Included Core Files'
foreach ($f in @($latestSuiteMd,$latestSuiteJson,$latestSoakMd,$latestSoakJson,$latestKpiMd,$latestKpiJson,$runState,$progressLog,$runLog) | Where-Object { $_ -ne $null }) {
  $lines += "- $($f.Name)"
}
$lines += ''
$lines += '## Included Daily Files'
foreach ($f in (Get-ChildItem $bundleDaily -File | Sort-Object LastWriteTime -Descending)) {
  $lines += "- $($f.Name)"
}
$lines | Set-Content -Path $summaryPath -Encoding UTF8

$zipPath = Join-Path $outDir ("signoff-bundle-$stamp.zip")
if (Test-Path $zipPath) { Remove-Item -Path $zipPath -Force }
Compress-Archive -Path (Join-Path $bundleRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal

Write-Output "BUNDLE_DONE"
Write-Output "BUNDLE_DIR=$bundleRoot"
Write-Output "BUNDLE_ZIP=$zipPath"
Write-Output "MANIFEST=$manifestPath"
Write-Output "SUMMARY=$summaryPath"
