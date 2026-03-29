$ErrorActionPreference = "Stop"

function Get-NetSphereRepoRoot {
  param(
    [string]$ScriptRoot
  )
  return (Resolve-Path (Join-Path $ScriptRoot "..")).Path
}

function Read-KeyValueEnvFile {
  param(
    [string]$Path
  )
  if (-not (Test-Path $Path)) {
    throw "Missing env file: $Path"
  }

  $result = @{}
  foreach ($line in Get-Content $Path) {
    $rawLine = ""
    if ($null -ne $line) {
      $rawLine = [string]$line
    }
    $trimmed = $rawLine.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
    if ($trimmed.StartsWith("#")) { continue }
    $idx = $trimmed.IndexOf("=")
    if ($idx -lt 1) { continue }
    $key = $trimmed.Substring(0, $idx).Trim()
    $value = $trimmed.Substring($idx + 1).Trim()
    $result[$key] = $value
  }
  return $result
}

function Assert-RequiredEnvValues {
  param(
    [string]$Path,
    [string[]]$RequiredKeys,
    [string[]]$PlaceholderPatterns = @("CHANGE_ME_", "replace-with", "your-domain.example")
  )

  $envMap = Read-KeyValueEnvFile -Path $Path
  $issues = New-Object System.Collections.Generic.List[string]

  foreach ($key in $RequiredKeys) {
    if (-not $envMap.ContainsKey($key)) {
      $issues.Add("Missing key: $key")
      continue
    }

    $value = [string]$envMap[$key]
    if ([string]::IsNullOrWhiteSpace($value)) {
      $issues.Add("Empty value: $key")
      continue
    }

    foreach ($pattern in $PlaceholderPatterns) {
      if ($value -like "*$pattern*") {
        $issues.Add("Placeholder value still present: $key")
        break
      }
    }
  }

  if ($issues.Count -gt 0) {
    $issues | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    throw "Env validation failed for $Path"
  }

  Write-Host "Env validation passed: $Path" -ForegroundColor Green
}

function Assert-HttpStatus {
  param(
    [string]$Url,
    [int]$ExpectedStatus = 200,
    [string]$Label = $Url
  )
  $status = (Invoke-WebRequest -UseBasicParsing $Url).StatusCode
  if ($status -ne $ExpectedStatus) {
    throw "Unexpected status for ${Label}: expected $ExpectedStatus, got $status"
  }
  Write-Host ("OK {0} -> {1}" -f $Label, $status) -ForegroundColor Green
}
