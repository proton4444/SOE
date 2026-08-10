param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dataDir = if ($env:SOE_DATA_DIR) { $env:SOE_DATA_DIR } else { Join-Path $root 'server_data' }
$pidFile = Join-Path $dataDir 'beta.pid'

if (-not (Test-Path $pidFile)) {
    throw 'No controlled beta PID file found.'
}
$betaPid = [int](Get-Content $pidFile -Raw)
$process = Get-Process -Id $betaPid -ErrorAction SilentlyContinue
if (-not $process) {
    throw "Recorded beta PID $betaPid is not running."
}

$health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 5
$health | ConvertTo-Json -Depth 5
Write-Host "Application process: PID $betaPid ($($process.ProcessName))"
Write-Host 'Configured application workers: 1 (verify the command line below).'
Get-CimInstance Win32_Process -Filter "ProcessId = $betaPid" |
    Select-Object ProcessId, CommandLine
Get-PSDrive -Name (Get-Item $dataDir).PSDrive.Name |
    Select-Object Name, @{Name='FreeGB';Expression={[math]::Round($_.Free / 1GB, 2)}}
