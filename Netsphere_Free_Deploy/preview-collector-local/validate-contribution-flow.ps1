param(
  [string]$Username = "admin",
  [string]$Password = "Password1!!@"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "..\_common.ps1")

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$collectorBase = "http://localhost:18080/api/v1"
$intakeStorage = Join-Path $repoRoot "Netsphere_Free_Backend\preview_contributions"
$sampleRaw = @"
hostname edge-sw-01
Mgmt IP: 10.10.1.10
SN: FDO1234ABCD
Contact: admin@example.com
snmp community public-secret
"@

function Get-PreviewFileCount {
  if (-not (Test-Path $intakeStorage)) {
    return 0
  }
  return @((Get-ChildItem -Recurse -Filter "preview-*.json" $intakeStorage)).Count
}

function Unwrap-ApiData {
  param(
    [Parameter(Mandatory = $true)]
    $Response
  )

  if ($null -eq $Response) {
    return $null
  }

  if ($null -ne $Response.data) {
    return $Response.data
  }

  return $Response
}

function Ensure-CollectorInitialAdmin {
  $status = Invoke-RestMethod -Method Get -Uri "$collectorBase/auth/bootstrap/status"
  if (-not $status.initial_admin_required) {
    Write-Host "Collector-local initial admin already exists." -ForegroundColor Yellow
    return
  }

  $python = @"
import json
import urllib.request

payload = {
  "username": "$Username",
  "password": "$Password",
  "full_name": "Collector Local Admin",
  "email": "collector-local@example.com",
}

req = urllib.request.Request(
  "http://127.0.0.1:8000/api/v1/auth/bootstrap/initial-admin",
  data=json.dumps(payload).encode("utf-8"),
  headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=15) as resp:
  print(resp.read().decode("utf-8"))
"@

  Push-Location $repoRoot
  try {
    docker compose -p netsphere-preview-collector -f docker-compose.preview-collector-local.yml exec -T collector-local python -c $python | Out-Null
  } finally {
    Pop-Location
  }
  Write-Host "Collector-local initial admin created." -ForegroundColor Green
}

function Get-AuthHeaders {
  $body = "username=$([uri]::EscapeDataString($Username))&password=$([uri]::EscapeDataString($Password))"
  $response = Invoke-RestMethod -Method Post -Uri "$collectorBase/auth/login" -ContentType "application/x-www-form-urlencoded" -Body $body
  $data = Unwrap-ApiData -Response $response
  if (-not $data.access_token) {
    throw "Login did not return an access token."
  }
  return @{ Authorization = "Bearer $($data.access_token)" }
}

function Get-PreviewPolicy {
  param(
    [Parameter(Mandatory = $true)]
    [hashtable]$Headers
  )

  return (Unwrap-ApiData -Response (Invoke-RestMethod -Method Get -Uri "$collectorBase/preview/policy" -Headers $Headers))
}

function Invoke-CollectorContributionFlow {
  $headers = Get-AuthHeaders
  $policy = Get-PreviewPolicy -Headers $headers

  if (-not $policy.upload_decision_recorded) {
    $consent = Unwrap-ApiData -Response (Invoke-RestMethod -Method Post -Uri "$collectorBase/preview/consent/contribution" -Headers $headers -ContentType "application/json" -Body (@{
      enabled = $true
      source = "first_run_wizard"
    } | ConvertTo-Json))

    if ($consent.state -ne "enabled") {
      throw "Contribution consent did not become enabled."
    }

    Write-Host "Collector-local contribution policy recorded during first-run flow." -ForegroundColor Green
    $policy = Get-PreviewPolicy -Headers $headers
  } elseif (-not $policy.upload_enabled) {
    throw "Contribution policy is locked disabled for this installation. Reset or reinstall collector-local to validate remote upload."
  } else {
    Write-Host "Collector-local contribution policy already enabled and locked for this installation." -ForegroundColor Yellow
  }

  if (-not $policy.upload_enabled) {
    throw "Contribution upload is not enabled."
  }

  $sanitize = Unwrap-ApiData -Response (Invoke-RestMethod -Method Post -Uri "$collectorBase/preview/sanitize" -Headers $headers -ContentType "application/json" -Body (@{
    entries = @(
      @{
        command = "show version"
        raw_output = $sampleRaw
      }
    )
    host_candidates = @("edge-sw-01")
  } | ConvertTo-Json -Depth 5))

  $entry = $sanitize.entries[0]
  if (-not $entry.sanitized_output) {
    throw "Sanitize did not return sanitized output."
  }

  $beforeCount = Get-PreviewFileCount

  $upload = Unwrap-ApiData -Response (Invoke-RestMethod -Method Post -Uri "$collectorBase/preview/contributions" -Headers $headers -ContentType "application/json" -Body (@{
    source = "collector_local_smoke"
    consent_confirmed = $true
    notes = "collector-local smoke"
    collector_context = @{
      deployment_role = "collector_installed"
    }
    entries = @(
      @{
        command = "show version"
        sanitized_output = $entry.sanitized_output
      }
    )
  } | ConvertTo-Json -Depth 6))

  $afterCount = Get-PreviewFileCount
  if ($afterCount -le $beforeCount) {
    throw "Intake storage did not receive a new preview contribution file."
  }

  if (-not $upload.delivery.remote_forwarded) {
    throw "Collector-local upload did not forward to intake."
  }

  if ($upload.delivery.local_saved) {
    throw "Collector-local should not save local contribution files in remote_only mode."
  }

  Write-Host "Collector-local contribution flow passed." -ForegroundColor Green
  Write-Host ("New intake file count: {0} -> {1}" -f $beforeCount, $afterCount) -ForegroundColor Green
}

Assert-HttpStatus -Url "$collectorBase/auth/bootstrap/status" -Label "collector-local bootstrap status"
Assert-HttpStatus -Url "http://127.0.0.1:8015/api/v1/auth/bootstrap/status" -Label "preview intake bootstrap status"

Ensure-CollectorInitialAdmin
Invoke-CollectorContributionFlow
