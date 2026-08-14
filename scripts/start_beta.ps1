param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ([string]::IsNullOrWhiteSpace($env:SOE_BETA_ACCESS_CODE)) {
    throw 'SOE_BETA_ACCESS_CODE must be set before starting the controlled beta.'
}
if ([string]::IsNullOrWhiteSpace($env:SOE_OPERATOR_KEY)) {
    throw 'SOE_OPERATOR_KEY must be set before starting the controlled beta.'
}

$dataDir = if ($env:SOE_DATA_DIR) { $env:SOE_DATA_DIR } else { Join-Path $root 'server_data' }
$gamesDir = if ($env:SOE_GAMES_DIR) { $env:SOE_GAMES_DIR } else { Join-Path $root 'games' }
$backupDir = if ($env:SOE_BACKUP_DIR) { $env:SOE_BACKUP_DIR } else { Join-Path $dataDir 'backups' }
$logFile = if ($env:SOE_LOG_FILE) { $env:SOE_LOG_FILE } else { Join-Path $dataDir 'beta.log' }

New-Item -ItemType Directory -Force -Path $dataDir, $gamesDir, $backupDir, (Split-Path -Parent $logFile) | Out-Null
$env:SOE_DATA_DIR = $dataDir
$env:SOE_GAMES_DIR = $gamesDir
$env:SOE_BACKUP_DIR = $backupDir
$env:SOE_LOG_FILE = $logFile
$env:SOE_COOKIE_SECURE = '1'

$pidFile = Join-Path $dataDir 'beta.pid'
if (Test-Path $pidFile) {
    $oldPid = [int](Get-Content $pidFile -Raw)
    if (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {
        throw "A beta server process is already recorded as PID $oldPid."
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$python = (Get-Command python).Source
$stdout = Join-Path $dataDir 'uvicorn.stdout.log'
$stderr = Join-Path $dataDir 'uvicorn.stderr.log'
$arguments = @('-m', 'uvicorn', 'webapp.main:app', '--host', '127.0.0.1', '--port', $Port,
    '--workers', '1', '--no-access-log')
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
$process.Id | Set-Content -LiteralPath $pidFile -NoNewline

Write-Host "Started controlled beta PID $($process.Id) on 127.0.0.1:$Port."
Write-Host 'HTTPS must terminate in front of this process (deploy/Caddyfile or scripts/start_https.ps1).'
Write-Host 'This process is the single application worker; do not publish port 8000.'
