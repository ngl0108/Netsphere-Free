param(
  [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$url = "http://127.0.0.1:$Port"
Start-Process $url | Out-Null
Write-Host "Opened NetSphere Free UI at $url"
