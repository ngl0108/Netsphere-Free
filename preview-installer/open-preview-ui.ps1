param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$url = "http://localhost:$Port"
Start-Process $url | Out-Null
Write-Host "Opened NetSphere Free UI at $url"
