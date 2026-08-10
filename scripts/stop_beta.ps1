$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dataDir = if ($env:SOE_DATA_DIR) { $env:SOE_DATA_DIR } else { Join-Path $root 'server_data' }
$pidFile = Join-Path $dataDir 'beta.pid'

if (-not (Test-Path $pidFile)) {
    Write-Host 'No controlled beta PID file found.'
    exit 0
}

$betaPid = [int](Get-Content $pidFile -Raw)
$process = Get-Process -Id $betaPid -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $betaPid
    $process.WaitForExit(10000)
    if (-not $process.HasExited) {
        throw "Beta PID $betaPid did not stop within 10 seconds; do not restore data yet."
    }
    Write-Host "Stopped controlled beta PID $betaPid."
} else {
    Write-Host "PID $betaPid was not running."
}
Remove-Item -LiteralPath $pidFile -Force
