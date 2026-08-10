param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$DataDir = '',
    [string]$GamesDir = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backup = (Resolve-Path -LiteralPath $BackupPath).Path
$manifestFile = Join-Path $backup 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestFile)) { throw 'Backup manifest not found.' }
$manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
if ($manifest.room_code -notmatch '^[A-Z2-9]{5}$') { throw 'Backup room code is invalid.' }
if (-not (Test-Path -LiteralPath (Join-Path $backup 'rooms.json'))) { throw 'Backup rooms.json not found.' }
if (-not (Test-Path -LiteralPath (Join-Path $backup 'game\state.json'))) { throw 'Backup game state not found.' }
$null = Get-Content -LiteralPath (Join-Path $backup 'rooms.json') -Raw | ConvertFrom-Json
$stateHash = (Get-FileHash -LiteralPath (Join-Path $backup 'game\state.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($stateHash -ne $manifest.state_version.ToLowerInvariant()) { throw 'Backup state hash does not match its manifest.' }

if (-not $DataDir) { $DataDir = if ($env:SOE_DATA_DIR) { $env:SOE_DATA_DIR } else { Join-Path $root 'server_data' } }
if (-not $GamesDir) { $GamesDir = if ($env:SOE_GAMES_DIR) { $env:SOE_GAMES_DIR } else { Join-Path $root 'games' } }
$data = [IO.Path]::GetFullPath($DataDir)
$games = [IO.Path]::GetFullPath($GamesDir)
New-Item -ItemType Directory -Force -Path $data, $games | Out-Null
$roomDir = Join-Path $games ("room_" + $manifest.room_code)
$stamp = Get-Date -Format 'yyyyMMddTHHmmssfffZ'
$roomsFile = Join-Path $data 'rooms.json'

if (Test-Path -LiteralPath $roomsFile) {
    Move-Item -LiteralPath $roomsFile -Destination (Join-Path $data ("rooms.pre-restore-$stamp.json"))
}
Copy-Item -LiteralPath (Join-Path $backup 'rooms.json') -Destination ($roomsFile + '.restore.tmp')
Move-Item -LiteralPath ($roomsFile + '.restore.tmp') -Destination $roomsFile

if (Test-Path -LiteralPath $roomDir) {
    Move-Item -LiteralPath $roomDir -Destination ($roomDir + ".pre-restore-$stamp")
}
Copy-Item -LiteralPath (Join-Path $backup 'game') -Destination $roomDir -Recurse

$state = Get-Content -LiteralPath (Join-Path $roomDir 'state.json') -Raw | ConvertFrom-Json
Write-Host "Restored room $($manifest.room_code). Authoritative game turn: $($state.turn_number)."
Write-Host "Pre-turn backup represented resolution turn $($manifest.turn). Preserve the .pre-restore directories until validation completes."
