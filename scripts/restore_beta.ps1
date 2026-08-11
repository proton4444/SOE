param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$DataDir = '',
    [string]$GamesDir = '',
    # Restore the snapshot's entire room registry instead of just the backed-up
    # room. Only correct when the live registry is unreadable or every room is
    # being rolled back together: the snapshot predates any room created since,
    # so this drops those rooms from the registry.
    [switch]$WholeRegistry
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
$roomsFile = Join-Path $data 'rooms.json'

# The restore itself is done by webapp.backups.restore_backup rather than
# reimplemented here, so the operator drill and the application cannot drift
# apart. Paths go through the environment to avoid quoting them into Python.
$env:PYTHONPATH = $root
$env:SOE_RESTORE_BACKUP_PATH = $backup
$env:SOE_RESTORE_ROOMS_FILE = $roomsFile
$env:SOE_RESTORE_GAMES_ROOT = $games
$env:SOE_RESTORE_WHOLE = if ($WholeRegistry) { '1' } else { '0' }

$restoreScript = @'
import os
from pathlib import Path

from webapp.backups import restore_backup

restore_backup(
    Path(os.environ["SOE_RESTORE_BACKUP_PATH"]),
    rooms_file=Path(os.environ["SOE_RESTORE_ROOMS_FILE"]),
    games_root=Path(os.environ["SOE_RESTORE_GAMES_ROOT"]),
    whole_registry=os.environ["SOE_RESTORE_WHOLE"] == "1",
)
'@

$restoreScript | python -
if ($LASTEXITCODE -ne 0) { throw 'Restore failed; the pre-restore copies are unchanged.' }

if ($WholeRegistry) {
    Write-Host 'Restored the snapshot''s entire room registry. Rooms created after this snapshot are no longer registered.'
} else {
    Write-Host "Restored only room $($manifest.room_code) in the registry. Other rooms were left as they were."
}

$state = Get-Content -LiteralPath (Join-Path $roomDir 'state.json') -Raw | ConvertFrom-Json
Write-Host "Restored room $($manifest.room_code). Authoritative game turn: $($state.turn_number)."
Write-Host "Pre-turn backup represented resolution turn $($manifest.turn). Preserve the .pre-restore directories until validation completes."
