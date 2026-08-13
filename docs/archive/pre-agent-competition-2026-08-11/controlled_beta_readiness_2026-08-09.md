# Controlled Beta Readiness Report

## Controlled beta status

**READY WITH CONDITIONS** for 4-8 explicitly invited trusted testers in 2-3
rooms, subject to the operator runbook being followed and a real HTTPS reverse
proxy being configured and verified on the target host before the first live
session.

The disposable restore drill has been completed on the development host and is
recorded under Verification. **HTTPS termination is now the only open
condition**; it remains unverified because no beta hostname or proxy exists yet.
See HTTPS termination below for the exact steps that close it.

This is not a public-beta approval.

## Changes made

- `webapp/backups.py`: added verified, file-based pre-turn snapshots containing
  the server room registry and complete room game directory. Manifests identify
  room, turn, authoritative pre-turn, timestamp, and state hash without placing
  credentials in names. Added validation and restore helpers that preserve
  current targets beside a restore.
- `webapp/service.py`: snapshots now occur after request/readiness validation
  and before parsing/resolution. Resolution stops when snapshot creation fails;
  safe resolution events are recorded; order and report files are published
  atomically; the existing process-local lock serializes all resolution work.
- `webapp/main.py`: added `/healthz`, safe request logging with request IDs,
  invite-code gating for room creation/joining, beta cookie configuration, and
  generic browser errors for unexpected resolution failures.
- `webapp/rooms.py`: corrupt or unreadable `rooms.json` now fails startup closed
  instead of silently presenting an empty room registry; persisted report and
  submission turn keys are normalized back to integers on reload.
- `webapp/observability.py`: added rotating file logging that records only
  method, path, status, duration, request ID, room/turn, backup, and state
  identifiers. Headers, query values, bodies, credentials, and order contents
  are not logged.
- `webapp/templates/index.html` and `webapp/templates/partials/panel.html`:
  added an invitation field when beta invite mode is enabled.
- `scripts/start_beta.ps1`, `scripts/stop_beta.ps1`, `scripts/check_beta.ps1`,
  `scripts/restore_beta.ps1`: added the one-worker launcher, health/process
  checks, safe stop, and validated restore workflow. The launcher binds to
  loopback, uses `--workers 1`, `--no-access-log`, no reload, and sets
  `SOE_COOKIE_SECURE=1`.
- `tests/test_webapp.py`: added focused backup creation, failed-backup blocking,
  safe event logging, and game/server restore coverage.
- `docs/mypy-baseline.txt` and `scripts/check_mypy_baseline.ps1`: established a
  reproducible 589-error baseline gate without attempting a repository cleanup.
- `pyproject.toml`: added development tools and excludes generated build
  directories from future mypy discovery.

## Verification

- Runtime tests: `python -m pytest tests/ -q` -> **423 passed**.
- Bandit: `bandit -r soe webapp cli.py -q -f json` -> **6 low,
  0 medium, 0 high**.
- Mypy baseline: `mypy soe webapp cli.py --no-incremental` -> **589
  errors**; `.\scripts\check_mypy_baseline.ps1` passes at 589.
- Ruff: `ruff check webapp tests/test_webapp.py scripts` -> **pass**.
- Compile check: `python -m compileall -q webapp scripts` -> **pass**.
- Package check: `python -m pip wheel . --no-deps --wheel-dir <temporary-dir>`
  -> **wheel built** (`soe-1.1.0a0-py3-none-any.whl`). The wheel is
  the core engine/CLI artifact and does not contain `webapp`; controlled beta
  deployment is from the source checkout, not from the wheel.
  `python -m build` is currently shadowed by the repository's generated local
  `build/` directory, so the reproducible package command for this checkout is
  `pip wheel` until that artifact is removed or renamed.
- Backup test: a successful forced turn creates a manifest whose copied state
  remains at turn 0 while live state advances to turn 1; state hash and load
  verification pass.
- Failed-backup test: injected snapshot failure returns HTTP 503 and leaves
  game state at turn 0; no resolution is run.
- Recovery test: `restore_backup` validates the manifest/hash, restores both
  `rooms.json` and the game directory, and a fresh `RoomStore`/state load
  confirms authoritative turn 0.
- Operator recovery drill: disposable server on port 8771 created and resolved
  a room, validated the newest backup, stopped, restored, restarted, and
  confirmed `/healthz=ok`, room status turn 0, and game state turn 0.
- Deployment check: the launcher starts Uvicorn with one worker on loopback,
  disables access logging, creates persistent paths, and `/healthz` returns
  `status=ok`. HTTPS termination is external and was not verifiable from this
  repository; use the runbook's HTTPS check on the target host.

## HTTPS termination

**Status: NOT VERIFIED. This is the one remaining controlled-beta condition.**

- **Hostname tested:** none. No beta hostname exists yet. The runbook still
  carries the placeholder `<beta-hostname>`, and no DNS name, `.env` file, or
  deployment target is defined anywhere in the repository.
- **Termination layer:** a reverse proxy or managed HTTPS endpoint in front of
  the application, which listens on `127.0.0.1` only and never terminates TLS
  itself. This is the intended architecture, not an implemented one.
- **Configuration source:** intent is documented in
  `docs/controlled_beta_runbook.md` (proxy forwards to `http://127.0.0.1:8000`,
  redirects HTTP to HTTPS) and enforced on the application side by
  `scripts/start_beta.ps1`, which binds loopback, forces one worker, and sets
  `SOE_COOKIE_SECURE=1`. **No proxy configuration artifact exists**: the
  repository contains no nginx, Caddy, Traefik, Apache, IIS, Docker Compose,
  ingress, systemd, tunnel, or certificate-automation configuration, and the
  development host has no such service installed, no listener on 80/443/8000,
  no enabled SOE/proxy firewall exposure, and no machine certificate.
- **Date/time of latest inspection:** 2026-08-09 17:42 local (UTC+02:00).
- **Certificate validation result:** not performed. No endpoint to test.
- **HTTP redirect result:** not performed.
- **`/healthz` over HTTPS result:** not performed. Only the loopback check
  `http://127.0.0.1:8000/healthz` has passed, which is not evidence of HTTPS
  readiness.
- **Application/API verification through a proxy:** not performed.
- **WebSocket/streaming result:** not applicable. The web client uses HTMX
  polling over ordinary request/response cycles; the application exposes no
  WebSocket, SSE, or streaming endpoint, so no connection-upgrade path needs to
  survive the proxy.
- **Forwarded-header dependency:** none. The application never reads the request
  scheme, `X-Forwarded-*`, `Forwarded`, or the client address for any decision;
  request logging records only method, path, status, and duration, and all
  redirects are relative paths. Uvicorn therefore does not need `--proxy-headers`
  for correctness. The one scheme coupling is cookie-side: beta cookies are
  issued with `Secure`, so browsers will silently discard them unless the public
  origin is HTTPS. A plaintext deployment will appear to work and then fail to
  hold host/player sessions.

### Target discovery inspection

The 2026-08-09 continuation inspection stopped before infrastructure changes
because it did not discover a real beta target or public hostname:

- **Target host:** not provided or discoverable. The only accessible machine was
  `PC-ARIBERTI`; repository and system evidence identify it only as the local
  development workstation, not as the beta target.
- **Inspected machine OS:** Microsoft Windows 11 Pro 64-bit, version
  `10.0.26200`. This is not recorded as the target-host OS because the target has
  not been selected.
- **Public beta hostname and DNS:** none. The machine has no DNS suffix and the
  repository, environment, and Git remote contain no deployment hostname or
  inventory. No DNS record can be validated until the operator supplies the real
  hostname and intended host address.
- **Network evidence:** the workstation has LAN address `192.168.1.117`, private
  Tailscale address `100.79.227.18`, default gateway `192.168.1.254`, and observed
  Internet egress IPv4 `93.37.213.109`. The egress address does not prove that
  inbound traffic reaches this workstation. Router/NAT forwarding and the
  ability to expose TCP 80/443 remain unverified.
- **Installed proxy evidence:** no IIS web feature, Caddy, nginx, Apache, or
  Traefik command, service, or installation path was found. No proxy was selected
  because the actual target OS and its installed infrastructure are unknown.
- **Listeners and firewall:** TCP 80, 443, and 8000 were not listening. No enabled
  SOE/proxy firewall rule exists. Windows has disabled built-in rule definitions
  for unrelated services on 80/443; these are not beta exposure and were not
  changed.
- **Certificate evidence:** the Local Machine personal certificate store is
  empty. No certificate was requested because hostname and DNS prerequisites are
  absent.
- **External results:** HTTP redirect, HTTPS `/healthz`, normal session/cookie
  flow, external port 8000 isolation, certificate validation, persistence, and
  `scripts/check_https.ps1` were not testable. No localhost or self-signed result
  was substituted.

Before work can resume, the operator must provide the target machine or remote
access to it, confirm its OS, provide the real public beta hostname, create or
authorize the required DNS record to the target's public/reachable address, and
confirm that TCP 443 and (if used for redirect or ACME) TCP 80 can reach that
machine through its host firewall and any upstream firewall/NAT. With those
facts available, proxy selection and certificate issuance can proceed on that
host.

### Verification tooling added

`scripts/check_https.ps1` performs the full external check with strict
certificate validation. It was self-tested on 2026-08-09 against a known-good
public TLS endpoint (`example.com`) to confirm the instrument itself works: DNS,
TCP/443, TLS 1.3 handshake, chain-and-hostname validation with
`SslPolicyErrors: None`, and expiry math all reported correctly, while the
SOE-specific route checks correctly failed against a host that is not SOE. That
self-test validates the tool only. **It is not evidence about any beta endpoint.**

Certificate verification is never relaxed in that script, and `curl -k` or
`-SkipCertificateCheck` must not be substituted for it.

### Exact steps remaining on the target host

Run in order, on the real host, once a hostname and proxy exist:

```powershell
# 1. Application first: one loopback worker, no TLS in the app.
.\scripts\start_beta.ps1 -Port 8000
.\scripts\check_beta.ps1 -Port 8000

# 2. Confirm the app is bound to loopback only and is a single process.
Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8000 |
  Select-Object LocalAddress, LocalPort, OwningProcess

# 3. Configure the reverse proxy (whichever product the host already runs) to:
#    - listen on 443 with a certificate valid for <beta-hostname>;
#    - proxy only to http://127.0.0.1:8000;
#    - redirect http://<beta-hostname>/* to https://<beta-hostname>/*;
#    - never publish port 8000 to the Internet.

# 4. Verify end to end with strict certificate validation.
.\scripts\check_https.ps1 -BetaHostname <beta-hostname>

# 5. Verify a real room route through the proxy, using a room created for the
#    drill. The key is sent as a header and is not echoed by the script.
.\scripts\check_https.ps1 -BetaHostname <beta-hostname> -RoomCode <code> -AgentKey $key
```

The condition closes only when `check_https.ps1` exits `0` against the public
hostname from a machine outside the host. Record the run date, hostname,
certificate issuer, and expiry date here; do not paste private keys, full
certificates, invite codes, or agent keys into this document.

### Unresolved issues

- No hostname, no DNS record, and no proxy product have been chosen.
- No certificate or certificate-renewal automation exists.
- This session had no access to any beta target host, so no part of the external
  path could be verified. Nothing above may be treated as a passing result.

## Accepted technical debt

- Six existing low-severity Bandit findings remain accepted: `B311` at
  `soe/engine.py:239`, `soe/parser/verbs_units.py:282`,
  `soe/phases/economy.py:105`,
  `soe/phases/intel.py:254`, and `webapp/service.py:118`; plus
  parser quote-token `B105` at `soe/parser/text.py:35`. No
  medium/high findings were reported.
- The existing mypy debt remains **589 errors**, measured by the exact targeted
  command above. The baseline gate prevents count growth but is not a cleanup
  project.
- No CI workflow, retention policy, public traffic controls, or structured
  monitoring platform was introduced for this controlled beta.

## Controlled-beta operating limits

- 4-8 trusted testers only, explicitly invited with `SOE_BETA_ACCESS_CODE`.
- 2-3 rooms maximum.
- Exactly one application worker; no `--reload`; no parallel same-room turn
  resolution. The process-local lock is not a multi-process lock.
- HTTPS must terminate at a reverse proxy or managed endpoint, with the app
  reachable only on loopback.
- Manual monitoring using `/healthz`, safe rotating logs, process checks, disk
  checks, and backup listings.
- A verified pre-turn backup is mandatory before every resolution.

## Remaining controlled-beta risks

- **HTTPS configuration is external and unverified.** Likelihood: medium.
  Consequence: credentials and game traffic could be intercepted, and `Secure`
  beta cookies would be dropped by browsers over plaintext, breaking sessions.
  Mitigation: configure the HTTPS proxy and run `scripts\check_https.ps1
  -BetaHostname <beta-hostname>` to exit `0` before inviting testers; do not
  expose port 8000 directly.
- **File-based restore is operator-driven.** Likelihood: low during a small
  beta. Consequence: a bad restore could pause or regress a room. Mitigation:
  run the disposable restore drill, validate the manifest/hash, stop the app,
  preserve `.pre-restore-*` directories, and verify the authoritative turn.
- **Concurrency is intentionally unproven.** Likelihood: medium if operators
  double-submit. Consequence: incorrect or confusing turn progression if the
  deployment violates the one-worker policy. Mitigation: one worker, host-only
  resolution, global process lock, and no parallel resolution attempts.
- **No retention/quota automation exists.** Likelihood: low for 2-3 rooms.
  Consequence: disk pressure can block writes and backups. Mitigation: check
  free storage each session and retain/rotate data manually only after an
  operator decision.
- **Query-string key compatibility remains.** Likelihood: low for trusted
  testers. Consequence: a key can leak through client history or an external
  proxy. Mitigation: use `X-Agent-Key`, and keep Uvicorn access logs disabled.

## Public-beta blockers

- [ ] Rate limiting
- [ ] Request-size limits
- [ ] Secure production cookies fully verified in the production deployment
- [ ] Data-retention policy
- [ ] Tested production recovery procedures and disaster rollback
- [ ] Structured monitoring
- [ ] Realistic concurrency testing
- [ ] CI release gates
- [ ] Wheel packaging for web deployment, if source-checkout deployment changes

## Operator commands

Run these from `C:\Antigravity\SOE` after setting the environment variables in
[`controlled_beta_runbook.md`](controlled_beta_runbook.md).

```powershell
# Start one loopback worker; the reverse proxy supplies HTTPS.
.\scripts\start_beta.ps1 -Port 8000

# Stop before any restore.
.\scripts\stop_beta.ps1

# Health, process, worker-policy, and disk check.
.\scripts\check_beta.ps1 -Port 8000

# Direct health check; use the HTTPS hostname for the proxy check.
Invoke-RestMethod http://127.0.0.1:8000/healthz | ConvertTo-Json -Depth 5
Invoke-WebRequest https://<beta-hostname>/healthz

# Safe application and Uvicorn logs. These omit request bodies and credentials.
Get-Content $env:SOE_LOG_FILE -Tail 100
Get-Content (Join-Path $env:SOE_DATA_DIR 'uvicorn.stderr.log') -Tail 50

# List and inspect backups without exposing keys in filenames.
Get-ChildItem $env:SOE_BACKUP_DIR -Directory -Recurse |
  Sort-Object LastWriteTime -Descending | Select-Object -First 20 FullName,LastWriteTime
Get-Content '<backup-path>\manifest.json'
python -c "from pathlib import Path; from webapp.backups import validate_backup; print(validate_backup(Path(r'<backup-path>')))"

# Restore a validated backup after stopping the server.
.\scripts\restore_beta.ps1 -BackupPath '<backup-path>'

# Runtime and accepted-debt checks.
python -m pytest tests/ -q
bandit -r soe webapp cli.py
mypy soe webapp cli.py --no-incremental
.\scripts\check_mypy_baseline.ps1

# Core package build check; web beta deployment is from source, not this wheel.
$wheelDir = Join-Path $env:TEMP ('soe-wheel-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $wheelDir | Out-Null
python -m pip wheel . --no-deps --wheel-dir $wheelDir
```
