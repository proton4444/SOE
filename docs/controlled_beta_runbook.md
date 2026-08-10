# Controlled Beta Runbook

This runbook is for 4-8 trusted, explicitly invited testers in 2-3 rooms. It
assumes one Windows host, file-backed state, one Uvicorn application worker,
and an HTTPS reverse proxy forwarding to `127.0.0.1:8000`.

## Before Starting

From `C:\Antigravity\SOE`, set the private invite code in the current operator
session. Do not commit it or print it in diagnostics.

```powershell
Set-Location C:\Antigravity\SOE
$env:SOE_BETA_ACCESS_CODE = "<private-invite-code>"
$env:SOE_DATA_DIR = "C:\Antigravity\SOE\server_data"
$env:SOE_GAMES_DIR = "C:\Antigravity\SOE\games"
$env:SOE_BACKUP_DIR = "C:\Antigravity\SOE\server_data\backups"
$env:SOE_LOG_FILE = "C:\Antigravity\SOE\server_data\beta.log"
```

Verify the HTTPS proxy is configured for the expected hostname, redirects HTTP
to HTTPS, and forwards only to `http://127.0.0.1:8000`. The application port
must not be exposed directly to the Internet.

```powershell
Test-NetConnection 127.0.0.1 -Port 8000
Get-PSDrive -Name C | Select-Object Name,Free
Get-ChildItem $env:SOE_BACKUP_DIR -ErrorAction SilentlyContinue
git rev-parse HEAD
python -c "import spoils_engine; print(spoils_engine.__version__)"
```

Start and check the server. The launcher fails if the invite code is missing,
sets beta cookies to Secure, creates the persistent directories, and starts one
worker without reload or access logs.

```powershell
.\scripts\start_beta.ps1 -Port 8000
.\scripts\check_beta.ps1 -Port 8000
.\scripts\check_https.ps1 -BetaHostname <beta-hostname>
```

`check_https.ps1` validates DNS, TCP/443, the TLS handshake, certificate chain,
hostname match and expiry, `/healthz` and application routes over HTTPS, the
HTTP-to-HTTPS redirect, and that port 8000 is not reachable publicly. It must
exit `0` before testers are invited. Never relax its certificate validation or
substitute `curl -k`.

Confirm exactly one application process and keep the reverse proxy as the only
public listener:

```powershell
$betaPid = [int](Get-Content (Join-Path $env:SOE_DATA_DIR "beta.pid"))
Get-CimInstance Win32_Process -Filter "ProcessId = $betaPid" |
  Select-Object ProcessId,CommandLine
Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq $betaPid
```

## During Beta

Use the header `X-Agent-Key` for player or host credentials. Do not put keys in
query strings. Check these manually at least once per session and after each
turn:

```powershell
Get-Content $env:SOE_LOG_FILE -Tail 100
Get-Content (Join-Path $env:SOE_DATA_DIR "uvicorn.stderr.log") -Tail 50
Get-PSDrive -Name C | Select-Object Name,Free
Invoke-RestMethod http://127.0.0.1:8000/healthz | ConvertTo-Json -Depth 5
Get-ChildItem $env:SOE_BACKUP_DIR -Directory -Recurse |
  Sort-Object LastWriteTime -Descending | Select-Object -First 20 FullName,LastWriteTime
```

Watch for application errors, backup failures, repeated failed requests,
unexpected restarts, low disk space, and rooms waiting indefinitely for a turn.
Only the host should resolve turns. Do not run parallel resolution requests for
the same room or claim concurrency safety beyond the single-worker setup.

## If a Turn Fails

1. Tell testers to stop submitting or resolving turns. Do not retry resolution
   until the evidence and backup are identified.
2. Preserve `beta.log`, `uvicorn.stderr.log`, the room's
   `resolution_events.jsonl`, the application commit, room code, and turn. Do
   not preserve keys, PINs, cookies, or full order text in the incident log.
3. Identify the newest valid snapshot for the affected room:

```powershell
$room = "<ROOMCODE>"
$latest = Get-ChildItem (Join-Path $env:SOE_BACKUP_DIR "room_$room") -Directory |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
$env:SOE_RESTORE_BACKUP = $latest.FullName
Get-Content (Join-Path $env:SOE_RESTORE_BACKUP "manifest.json")
python -c "from pathlib import Path; from webapp.backups import validate_backup; print(validate_backup(Path(r'$env:SOE_RESTORE_BACKUP')))"
```

4. Stop the application before restoring:

```powershell
.\scripts\stop_beta.ps1
```

5. Restore the validated snapshot. The script preserves current files as
   `.pre-restore-*` instead of deleting them:

```powershell
.\scripts\restore_beta.ps1 -BackupPath $env:SOE_RESTORE_BACKUP
```

6. Restart and verify the authoritative turn from both the manifest and the
   restored state, then check the room through the host API before resuming:

```powershell
.\scripts\start_beta.ps1 -Port 8000
.\scripts\check_beta.ps1 -Port 8000
Get-Content (Join-Path $env:SOE_GAMES_DIR "room_$room\state.json") |
  Select-String 'turn_number'
```

If the restored turn is not unambiguous, keep the room paused and do not
resolve another turn.

## After a Session

Retain the pre-turn backups for every affected room and useful redacted logs.
Record the room code, turn, failure, expected result, actual result, commit,
backup path, and required fix. Do not delete or expire backups during the
controlled beta without an operator decision and an independent copy.

## Routine Checks

```powershell
python -m pytest tests/ -q
bandit -r spoils_engine webapp cli.py
mypy spoils_engine webapp cli.py --no-incremental
.\scripts\check_mypy_baseline.ps1
```
