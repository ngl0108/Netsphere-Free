param(
  [ValidateSet('all', 'pro', 'free')]
  [string]$Target = 'all'
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'Netsphere_Free_Frontend'
$reportsRoot = Join-Path $PSScriptRoot 'reports'
$summaryPath = Join-Path $reportsRoot 'functional-audit.latest.json'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'

function Invoke-PlaywrightAuditGroup {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Scope,
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string[]]$Specs,
    [Parameter(Mandatory = $true)]
    [hashtable]$EnvMap,
    [int]$Workers = 0,
    [int]$Retries = 2
  )

  $outputDir = "test-results\functional-audit-$Scope-$Name-$timestamp"
  $commandArgs = @(
    '.\node_modules\@playwright\test\cli.js',
    'test'
  ) + $Specs + @("--output=$outputDir")
  if ($Workers -gt 0) {
    $commandArgs += "--workers=$Workers"
  }

  Write-Host "[functional-audit] $Scope/$Name" -ForegroundColor Cyan
  foreach ($spec in $Specs) {
    Write-Host "  - $spec" -ForegroundColor DarkGray
  }

  $previousEnv = @{}
  try {
    $env:PW_SKIP_WEBSERVER = '1'
    foreach ($key in $EnvMap.Keys) {
      $previousEnv[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
      [Environment]::SetEnvironmentVariable($key, [string]$EnvMap[$key], 'Process')
    }

    $lastFailure = $null
    for ($attempt = 1; $attempt -le $Retries; $attempt += 1) {
      if ($attempt -gt 1) {
        Write-Host "  retry $attempt/$Retries for $Scope/$Name" -ForegroundColor Yellow
        Start-Sleep -Seconds (2 * $attempt)
      }

      $nodeOutput = & node @commandArgs 2>&1
      if ($nodeOutput) {
        $nodeOutput | ForEach-Object { Write-Host $_ }
      }
      if ($LASTEXITCODE -eq 0) {
        return [ordered]@{
          scope = $Scope
          name = $Name
          specs = $Specs
          output_dir = $outputDir
          status = 'passed'
          attempts = $attempt
          base_url = if ($EnvMap.ContainsKey('E2E_BASE_URL')) { $EnvMap['E2E_BASE_URL'] } elseif ($EnvMap.ContainsKey('PRO_AUDIT_BASE_URL')) { $EnvMap['PRO_AUDIT_BASE_URL'] } elseif ($EnvMap.ContainsKey('FREE_AUDIT_BASE_URL')) { $EnvMap['FREE_AUDIT_BASE_URL'] } else { '' }
        }
      }

      $lastFailure = "Playwright audit group failed: $Scope/$Name"
    }

    throw $lastFailure
  }
  finally {
    foreach ($key in $EnvMap.Keys) {
      [Environment]::SetEnvironmentVariable($key, $previousEnv[$key], 'Process')
    }
    Remove-Item Env:PW_SKIP_WEBSERVER -ErrorAction SilentlyContinue
  }
}

$auditGroups = @()
if ($Target -in @('all', 'pro')) {
  $auditGroups += @{
    scope = 'pro'
    name = 'route-matrix'
    specs = @('tests/e2e/functional-route-matrix-pro.spec.js')
    env = @{ PRO_AUDIT_BASE_URL = 'http://localhost' }
  }
  $auditGroups += @{
    scope = 'pro'
    name = 'functional-surfaces'
    specs = @('tests/e2e/functional-audit-pro.spec.js')
    env = @{ PRO_AUDIT_BASE_URL = 'http://localhost' }
  }
  $auditGroups += @{
    scope = 'pro'
    name = 'scenario-actions'
    specs = @(
      'tests/e2e/scenario-lab-pro-actions.spec.js',
      'tests/e2e/scenario-lab-pro-cloud-topology.spec.js'
    )
    env = @{ E2E_BASE_URL = 'http://localhost' }
  }
  $auditGroups += @{
    scope = 'pro'
    name = 'state-matrix'
    specs = @(
      'tests/e2e/config-template-deploy-guard.spec.js',
      'tests/e2e/compliance-report-automation.spec.js',
      'tests/e2e/operations-reports-states.spec.js'
    )
    env = @{ E2E_BASE_URL = 'http://localhost' }
    workers = 1
  }
}

if ($Target -in @('all', 'free')) {
  $auditGroups += @{
    scope = 'free'
    name = 'route-matrix'
    specs = @('tests/e2e/functional-route-matrix-free.spec.js')
    env = @{ FREE_AUDIT_BASE_URL = 'http://127.0.0.1:18080' }
  }
  $auditGroups += @{
    scope = 'free'
    name = 'functional-surfaces'
    specs = @('tests/e2e/functional-audit-free.spec.js')
    env = @{ FREE_AUDIT_BASE_URL = 'http://127.0.0.1:18080' }
  }
  $auditGroups += @{
    scope = 'free'
    name = 'scenario-actions'
    specs = @(
      'tests/e2e/scenario-lab-free-actions.spec.js',
      'tests/e2e/scenario-lab-free-topology-modes.spec.js'
    )
    env = @{ E2E_BASE_URL = 'http://127.0.0.1:18080' }
  }
  $auditGroups += @{
    scope = 'free'
    name = 'state-matrix'
    specs = @(
      'tests/e2e/free-intake-contribution.spec.js',
      'tests/e2e/free-route-guard.spec.js'
    )
    env = @{ E2E_BASE_URL = 'http://127.0.0.1:18080' }
    workers = 1
  }
}

$summary = [ordered]@{
  generated_at = (Get-Date).ToString('o')
  target = $Target
  groups = @()
}

Push-Location $frontendRoot
try {
  foreach ($group in $auditGroups) {
    $summary.groups += Invoke-PlaywrightAuditGroup -Scope $group.scope -Name $group.name -Specs $group.specs -EnvMap $group.env -Workers $group.workers
  }

  $summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryPath
  Get-Content $summaryPath
}
finally {
  Pop-Location
}
