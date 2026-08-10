# Beta Readiness Audit - 2026-08-09

## Decision

**GO for a controlled, invite-only beta on a single application process.**

**NO-GO for an open Internet beta** until the P0 items below are closed. The
engine has strong regression coverage and a deterministic long-run harness, but
the web service does not yet include the abuse controls and operational recovery
needed for untrusted public traffic.

## Evidence Collected

| Gate | Result | Evidence |
|---|---|---|
| Unit/integration tests | PASS | 416 tests passed on Python 3.12 after the auth regression fix |
| Coverage | PASS WITH GAPS | 78% total; parser magic/units/social and several phases are below 60% |
| Lint | PASS | Ruff reports no issues |
| Dependency consistency | PASS | `pip check` reports no broken requirements |
| Package wheel | PASS | Wheel builds and its `soe` entry point runs in a clean virtual environment |
| Security static scan | PASS WITH NOTES | Bandit reports six low-severity findings and no medium/high findings |
| Type checking | FAIL | mypy reports 589 errors; it is not configured as a release gate |
| Long-run simulation | PASS WITH LIMITS | Existing 100-turn, two-faction scripted run completed without engine errors |
| CI/release automation | MISSING | No repository CI workflow or reproducible release job |

## Fixed During This Audit

- Duplicate display names previously returned the existing player's agent key.
  A user who knew the room PIN could impersonate another player by entering that
  public name. Duplicate names are now rejected and covered through both API and
  browser tests.
- The README incorrectly said turns resolved automatically. It now describes the
  host-driven resolution behavior.
- API documentation now recommends credential headers rather than query strings.
- The built wheel declared a console entry point for `cli.py` but did not contain
  that module. Packaging now includes it, and package/API versions agree on
  `1.1.0a0`.

## Release Blockers

### P0 - Required Before an Open Beta

- Add rate limits for room creation and join attempts. A 4-digit PIN provides no
  protection against unrestricted online guessing, and anonymous room creation
  can consume disk indefinitely.
- Add request size limits, especially for order text and JSON bodies.
- Define HTTPS-only deployment and set authentication cookies `Secure` in that
  environment. Keep `HttpOnly` and an explicit `SameSite` policy.
- Add retention and deletion for rooms, reports, and orders. Runtime data grows
  without a quota or expiry.
- Add backup/restore procedures and test recovery from a corrupt `rooms.json` or
  interrupted multi-file turn resolution.
- Add structured server logging and error monitoring without recording agent
  keys, host keys, PINs, or order contents by default.

### P1 - Required During Controlled Beta

- Add CI for Python 3.11 and 3.12 running tests, Ruff, coverage, wheel build, and
  dependency/security scans.
- Establish a type-checking baseline. The current 589 errors make mypy unusable
  for detecting regressions; reduce or baseline them before making it blocking.
- Add concurrency tests for simultaneous submissions and duplicate resolve
  requests. Current locks are process-local, so deployment must use exactly one
  worker until storage and locking support multiple processes.
- Add corrupt-state, disk-full, and partial-write recovery tests across the room
  registry, game state, order files, and report files.
- Re-run the 100-turn harness from a clean directory and reconcile its report:
  `BETA_REPORT.md` lists character gold while `FINAL_SUMMARY.txt` lists faction
  treasury, which currently looks contradictory to an operator.
- Stop tracking bulk generated turn orders/reports as source, or move a minimal
  fixture set under a dedicated test-fixtures directory.

## Controlled Beta Protocol

### Cohort and Hosting

- Begin with 4-8 invited testers in 2-3 rooms.
- Run one Uvicorn worker behind HTTPS; do not use `--reload`.
- Back up `server_data/` and `games/room_*` before every turn resolution.
- Give keys only through private channels and instruct agents to use the
  `X-Agent-Key` header.

### Test Sessions

1. Onboarding: create, join, wrong PIN, duplicate name, full room, refresh and
   reconnect behavior.
2. Orders: valid, invalid, mixed, repeated replacement, empty orders, and every
   documented verb family.
3. Turn lifecycle: missing submission, forced resolution, normal resolution,
   report retrieval, and next-turn submission.
4. Privacy: attempt cross-player state, report, order, and host actions using
   missing, wrong, and other-room keys.
5. Recovery: restart the server between submission and resolution and after a
   resolved turn; verify state, reports, and credentials survive.
6. Gameplay: complete at least 10 human turns per room and record confusing
   parser feedback, balance failures, stalled games, and report ambiguity.

### Exit Criteria

- No unresolved data-loss, authentication, cross-player information leak, or
  double-resolution defects.
- At least 30 cumulative human-played turns across three rooms.
- At least 95% of submitted lines either parse as intended or return a useful,
  actionable warning.
- Recovery from a normal process restart succeeds for every active room.
- All automated tests and lint checks remain green on the beta candidate commit.

## Issue Template

Record: room code (never keys/PIN), turn, actor/faction, exact submitted orders,
expected result, actual report/result, whether retrying reproduced it, server
version/commit, and relevant redacted logs. Classify severity as P0 data/security,
P1 turn-blocking or incorrect state, P2 incorrect command/report, or P3 usability.
