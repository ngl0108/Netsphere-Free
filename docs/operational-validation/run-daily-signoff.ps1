param(
  [string]$BaseUrl = "http://localhost:8000",
  [string]$Username = "admin",
  [string]$Password = "Password1!!@"
)

$ErrorActionPreference = "Stop"
$date = Get-Date -Format "yyyyMMdd"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dailyDir = "docs/reports/daily"
New-Item -ItemType Directory -Force -Path $dailyDir | Out-Null

# login
$loginBody = "username=$Username&password=$Password"
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $loginBody
$token = $login.access_token
if (-not $token -and $login.data) { $token = $login.data.access_token }
if (-not $token) { throw "Token not found" }
$headers = @{ Authorization = "Bearer $token" }

# kpi snapshot + readiness history
$snapshot = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/ops/kpi/readiness/snapshot?require_sample_minimums=true" -Headers $headers
$history = Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/v1/ops/kpi/readiness/history?days=30&limit=90" -Headers $headers

# export readiness report (latest)
python Netsphere_Free_Backend/tools/export_kpi_readiness_report.py `
  --base-url $BaseUrl `
  --token $token `
  --discovery-days 30 `
  --require-sample-minimums `
  --sample-min-discovery-jobs 30 `
  --sample-min-change-events 60 `
  --sample-min-northbound-deliveries 500 `
  --sample-min-autonomy-issues-created 20 `
  --sample-min-autonomy-actions-executed 20 `
  --latest-json-path docs/reports/kpi-readiness-30d-latest.json `
  --latest-md-path docs/reports/kpi-readiness-30d-latest.md | Out-Null

# docker logs daily
$backendLog = "$dailyDir/$date-backend.log"
$workerLog = "$dailyDir/$date-celery-worker.log"
$beatLog = "$dailyDir/$date-celery-beat.log"
docker compose logs --since 24h backend > $backendLog
docker compose logs --since 24h celery-worker > $workerLog
docker compose logs --since 24h celery-beat > $beatLog

# save daily summary json
$dailyJson = "$dailyDir/$date-daily-signoff-$stamp.json"
$payload = [ordered]@{
  generated_at = (Get-Date).ToString("o")
  base_url = $BaseUrl
  kpi_snapshot = $snapshot
  kpi_history = $history
  logs = [ordered]@{
    backend = $backendLog
    celery_worker = $workerLog
    celery_beat = $beatLog
  }
}
$payload | ConvertTo-Json -Depth 20 | Set-Content -Path $dailyJson -Encoding UTF8

Write-Output "DAILY_SIGNOFF_DONE"
Write-Output "DAILY_JSON=$dailyJson"
Write-Output "BACKEND_LOG=$backendLog"
Write-Output "WORKER_LOG=$workerLog"
Write-Output "BEAT_LOG=$beatLog"
