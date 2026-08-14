$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dataDir = if ($env:SOE_DATA_DIR) { $env:SOE_DATA_DIR } else { Join-Path $root 'server_data' }
$pidFile = Join-Path $dataDir 'https.pid'

if (-not (Test-Path $pidFile)) {
    Write-Host 'No HTTPS terminator PID file found.'
    exit 0
}

$httpsPid = [int](Get-Content $pidFile -Raw)
$process = Get-Process -Id $httpsPid -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $httpsPid
    $process.WaitForExit(10000)
    if (-not $process.HasExited) {
        throw "HTTPS terminator PID $httpsPid did not stop within 10 seconds."
    }
    Write-Host "Stopped HTTPS terminator PID $httpsPid."
} else {
    Write-Host "PID $httpsPid was not running."
}
Remove-Item -LiteralPath $pidFile -Force
