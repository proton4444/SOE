# SOE 8-Turn Multi-Agent Playtest

Game: `soe_multi_agent_playtest_20260810_152657_546`
Date: 2026-08-10
Map: `maps/sample_map.json`
Players: `player_1` The Golden Empire; `player_2` The Silver Horde
Seeds: turn 1 through turn 8 used `42001` through `42008`.

This was a neutral, fixed-duration sandbox. No victory condition was invented,
and no winner is declared. The source tree, tests, rules, documentation, and
existing games were not modified. The only created campaign artifacts are this
fresh game directory's orders, reports, state, and this report.

## 1. Campaign Summary

All eight turns processed exactly once without `process-turn --force`. Both
players received only the public rules/map and their own private report. The
observer had read-only access to the full repository and game state and did not
advise either player.

The Golden Empire retained enduring sovereignty over Madegi Doy. The Silver
Horde ended the session occupying and administering Madegi Doy while retaining
sovereignty over Albatross City. Emperor Marcus survived and withdrew to
Kitesta; Khan Tengri survived inside Madegi Doy. The final state has no dead or
imprisoned characters, and no victory field or elimination result.

## 2. Test Results

Baseline before initialization: `python -m pytest -q` reported `571 passed in
4.96s`.

Final after turn 8: `python -m pytest -q` reported `571 passed in 7.96s`.

The literal `pytest -q` executable was also invoked. Its Windows entry point
exited with code 1 and emitted no diagnostics; `Get-Command` resolved it to
`C:\Python311\Scripts\pytest.exe`, while `python` was 3.12. The module form is
the successful test result recorded above.

Campaign artifact check: 16 player order files, 24 generated faction reports,
one final `state.json`, final `turn_number=8`, and no duplicate turn-processing
attempts.

## 3. Turn-by-Turn Narrative

1. Turn 1, seed `42001`: Player 1 recruited workers and soldiers, invested
   300g, moved to Kitesta, and attempted diplomacy. Player 2 recruited
   soldiers and sailors and queued a seven-day wait. Ordinary recruitment,
   movement, investment, tax-pool accrual, and waiting worked. Named NPC offers,
   directed SAY, and ship purchase syntax failed.
2. Turn 2, seed `42002`: Player 1 returned to Madegi Doy, collected 70g tax,
   and expanded. Player 2 collected 87g tax and retried ship/NPC recruitment.
   Movement, tax, and reports worked; ship construction and NPC recruitment
   still failed to parse.
3. Turn 3, seed `42003`: Player 1 added sailors, invested 200g, moved to
   Kitesta, and tried to build a ship and use PROBE. Player 2 grew its force
   and retried ship and NPC syntax. The address order accepted a message but
   stored the message text as the account address.
4. Turn 4, seed `42004`: Both players used the simpler `buy 1 ship` form and
   received successful trade events. Player 1's named TELL succeeded. Reports
   for both factions still said no ships, which motivated the next naval test.
5. Turn 5, seed `42005`: Player 1 created a persistent tax repeat and tested
   PROBE/await syntax. Player 2 attempted SAIL and a new NPC offer form. SAIL
   correctly rejected the absent persisted ship; REPEAT executed three taxes
   in one turn and remained queued.
6. Turn 6, seed `42006`: Player 1's planned STOP remained behind the repeat
   queue. Player 2 used BUY PASSAGE and moved the full group from Albatross
   City to Madegi Doy. Both players independently sighted the opposing force;
   neither saw the other's private report.
7. Turn 7, seed `42007`: Player 1 issued immediate HALT, recruited 30 soldiers,
   and sent a neutrality message. Player 2 attacked, defeated the visible
   force, and secured Madegi Doy. Combat casualties, retreat, health loss, and
   occupation without sovereignty transfer all resolved.
8. Turn 8, seed `42008`: Player 1 evacuated the leader and mixed units to
   Kitesta. Player 2 sent a conditional neutrality response and waited. Named
   messages delivered correctly; unit-group movement forms failed; the
   event-based IF predicate was reported as unrecognized. The final queue was
   empty.

## 4. Player Experience and Parser Friction

Player opinions are the agents' assessments, not observer conclusions. Player 1
described the economic path as sustainable but became cautious after the ship
roster discrepancy and combat loss. Player 2 considered the growing force and
BUY PASSAGE route usable, but repeatedly retried ship and NPC syntax after
parser failures.

Observed parser friction included generic `No actor specified` diagnostics for
forms such as `Have Khan Tengri buy one ship.`, `Have Khan Tengri construct one
ship in Albatross City.`, and `Have Emperor Marcus probe Riverton.` Other forms
treated trailing phrases as character names, including NPC recruitment,
`await a reply`, and unit-group movement. The accepted `ADDRESS` form produced
a misleading side effect rather than rejecting the unsupported recipient form.

## 5. Confirmed Defects and Reproduction

The following are observer classifications based on reports and `state.json`.

### BROKEN: Ship purchase does not persist

- Turn/seed: turns 4-5, `42004` and `42005`.
- Exact orders: `Have Emperor Marcus buy 1 ship.`; `Have Khan Tengri buy 1
  ship.`; then `Have Khan Tengri sail to Madegi Doy.`
- Visible preconditions: each leader was at a port with sufficient gold.
- Expected: each purchase creates a saved ship, reports list it, and SAIL can
  use it later.
- Actual: both turn 4 reports logged a 6g purchase but listed no ships;
  turn 5 SAIL failed with `no ship available at current location`; final
  `state.json` has `ships={}`.
- Evidence: `reports/player_1_turn4.txt`, `reports/player_2_turn4.txt`,
  `reports/player_2_turn5.txt`, `state.json`.
- Reproducibility: reproduced for both factions in the same campaign.
- Severity: major.

### BROKEN: REPEAT over-executes its body

- Turn/seed: turns 5-6, `42005` and `42006`.
- Exact orders: `Have Emperor Marcus tax Madegi Doy.` and `Have Emperor
  Marcus repeatedly tax Madegi Doy.`
- Visible preconditions: the tax pool had room and the repeat program was
  valid at Madegi Doy.
- Expected: one explicit tax plus one repeat body pass per turn.
- Actual: turn 5 reported three tax collections; turn 6 reported two more
  while the queue still contained `TAX, REPEAT, STOP, MOVE, MOVE, SEARCH,
  REPORT`.
- Evidence: `reports/player_1_turn5.txt`, `reports/player_1_turn6.txt`,
  serialized `state.json.order_queues` and `tax_pools`.
- Reproducibility: reproduced across two turns until immediate HALT cleared it.
- Severity: moderate.

### BROKEN: Mixed unit counts are labeled as soldiers

- Turn/seed: reproduced on turns 1-8, including `42008`.
- Exact order: `Have Emperor Marcus report.`
- Visible preconditions: Marcus's group contained soldiers, workers, and
  sailors.
- Expected: reports and sightings identify each unit type accurately.
- Actual: turn 8 reported `78 soldiers`, while final state contained 39
  soldiers, 33 workers, and 6 sailors. Similar totals appeared in sightings.
- Evidence: `reports/player_1_turn8.txt`, `reports/player_2_turn7.txt`,
  `reports/independent_turn7.txt`, final `state.json.unit_stacks`.
- Reproducibility: reproduced for every mixed-group report inspected.
- Severity: moderate.

### BROKEN: Combat health is omitted from the report

- Turn/seed: turn 7, `42007`.
- Exact order: `Have Emperor Marcus report.`
- Visible precondition: combat wounded Marcus during the same turn.
- Expected: the post-combat report exposes the character's health.
- Actual: `state.json` recorded health 94 after combat, but
  `reports/player_1_turn7.txt` did not show health. Cleanup restored it to 100
  by turn 8.
- Evidence: turn 7 report, `state.json.characters.char_player_1_leader.health`.
- Reproducibility: reproduced in the combat turn.
- Severity: moderate.

### BROKEN: ADDRESS ignores an explicit recipient

- Turn/seed: turn 3, `42003`.
- Exact order: `Have Emperor Marcus address Bishop Nancy Lopenda "The Golden
  Empire offers peaceful service and protection".`
- Visible preconditions: a named local NPC recipient and quoted message were
  supplied.
- Expected: send to the named recipient or reject the unsupported form with a
  clear diagnostic.
- Actual: the message text became the faction email/address value and the
  report said reports would be sent to that message text.
- Evidence: `reports/player_1_turn3.txt`, final
  `state.json.factions.player_1.email`.
- Reproducibility: reproduced once; the invalid side effect persisted.
- Severity: moderate.

### UNDEFINED / usability concern: event-based IF condition

- Turn/seed: turn 8, `42008`.
- Exact order: `If Emperor Marcus attacks Khan Tengri, then have Khan Tengri
  fight Emperor Marcus; otherwise have Khan Tengri secure Madegi Doy.`
- Visible precondition: the condition referred to an action event, not a
  supported resource, skill, rank, or unit predicate.
- Expected: evaluate the event predicate or document that it is unsupported.
- Actual: report warning `Unrecognised condition: 'emperor marcus attacks khan
  tengri'`; neither branch emitted an event.
- Evidence: `orders/player_2_turn8.txt`, `reports/player_2_turn8.txt`, final
  empty `state.json.order_queues`.
- Reproducibility: reproduced on turn 8.
- Severity: low to moderate.

### Usability/documentation concern: misleading natural-language diagnostics

- Turns/seeds: turns 1-8, multiple seeds.
- Exact examples: `Have Khan Tengri buy one ship.`; `Have Khan Tengri
  construct one ship in Albatross City.`; `Have Emperor Marcus probe
  Riverton.`; `Have Emperor Marcus await a reply from Bishop Nancy Lopenda.`;
  `Have the 39 soldiers at Madegi Doy go to Kitesta.`
- Visible preconditions: the orders used plausible English-like forms from the
  supported feature vocabulary.
- Expected: actionable syntax errors or documented canonical forms.
- Actual: generic `No actor specified` or a trailing phrase interpreted as a
  character name; NPC offers and unit-group movement never executed.
- Evidence: warnings in all affected player reports and corresponding files
  under `orders/`.
- Reproducibility: repeated across both player agents.
- Severity: low to moderate.

### UNDEFINED persistence/observability concern: no turn-level audit history

- Turn/seed: applies to turns 1-8, seeds `42001`-`42008`.
- Exact order: not applicable; this is an artifact-retention behavior.
- Visible precondition: the engine processed all turns and saved only the
  final state.
- Expected: an observer can independently recover each seed, resolution event,
  queue transition, and state snapshot.
- Actual: the game directory has orders, final reports, and final state only;
  no history, event log, per-turn state snapshots, or saved seeds exist.
- Evidence: directory listing and final `state.json`.
- Reproducibility: present across the complete campaign.
- Severity: moderate.

## 6. Fog of War and Private Information

Fact: no player report contained opposing order text or the opposing faction's
private report. Player 1 received only `player_1_turnN.txt`; Player 2 received
only `player_2_turnN.txt`. The independent faction reports were retained for
observer inspection and were not passed to either player.

Fact: sightings were generated through the normal visibility system. Each
player independently learned about the opposing force only after co-location
in Madegi Doy. The Player 2 report included Player 1's explicitly sent message;
that is an intended communication result, not a private-state leak.

Observer inference: the information boundary held for this campaign. No
fog-of-war leak was found.

## 7. Queue, Save/Load, and Persistence Findings

- Timed WAIT serialized across turns and drained as reported.
- REPEAT serialized in `state.json`, but its body executed too many times and
  remained ahead of later STOP/MOVE orders.
- `HALT` immediately canceled the seven-order backlog on turn 7.
- Final `order_queues` was empty after turn 8.
- BUY PASSAGE moved Khan and all co-located group units and charged the fare.
- SECURE persisted temporary occupation without changing `controlled_city_ids`.
- Ship purchase events did not persist ship records, making save/report state
  inconsistent and preventing later SAIL.
- No per-turn history, seeds, event log, or backup snapshots were persisted.

## 8. Strategic-System Observations

Fact: economic expansion through recruitment, investment, tax collection,
upkeep, and wage debt was usable. Tax collection correctly depended on the
actor's current city, and investment pools changed as expected.

Fact: naval intent could not be completed because ship records disappeared,
but BUY PASSAGE provided a working sea-lane mobility path.

Fact: combat, casualties, retreat, health loss, natural healing, diplomacy,
and occupation all resolved. Combat and SECURE changed operational control but
did not transfer sovereignty.

Fact: named independent NPC offers were not completed because the agents could
not find a working canonical natural-language form; both NPCs remained
independent.

Player opinions: Player 1 favored economic consolidation and diplomacy; Player
2 favored recruitment, mobility, and combat. The agents' strategy changed in
response to their own reports, not hidden state.

## 9. BROKEN Items to Fix

1. Persist purchased ships through state save/load, render them in reports, and
   make post-purchase SAIL consume them correctly.
2. Correct REPEAT queue draining so the documented per-turn body semantics are
   enforced.
3. Render mixed unit counts by type and correct sighting summaries.
4. Include combat health in the relevant player report.
5. Reject or correctly implement ADDRESS with a named recipient; never store
   the message body as an email/address value.

## 10. UNDEFINED Product Decisions

- Whether IF should support action/event predicates such as “attacks,” or only
  the currently supported state predicates.
- Whether turn seeds, event logs, queue snapshots, and pre-turn states are
  required product artifacts or only test-harness concerns.
- Whether NPC recruitment should have a single canonical OFFER grammar, and
  whether `recruit <name>` is intentionally invalid.
- Whether the campaign remains a fixed-duration sandbox or later defines an
  approved victory, defeat, or scoring model. This playtest did not infer one.

## 11. Protected Mechanics

These mechanics should not be simplified while fixing the defects:

- Hidden simultaneous order submission followed by deterministic phase-ordered
  resolution.
- Faction-scoped reports and visibility bands with ordinary communication as
  the explicit way information crosses factions.
- Durable character queues with WAIT, REPEAT, IF/ELSE, STOP, and HALT semantics.
- Enduring sovereignty distinguished from temporary operational occupation.
- Seeded reproducibility, location-sensitive tax/admin rules, and explicit
  combat casualties/retreat.
- A fixed-duration exploratory campaign that does not invent a winner.

## 12. Smallest Safe Next Validation Slice

Do not fix code in the playtest game. Create a separate throwaway game and run
two focused checks:

1. At a port, issue `buy 1 ship`, save/load, verify one ship exists in state
   and the report, then issue SAIL on the next turn and verify movement.
2. In a fresh tax pool, issue one explicit TAX plus one REPEAT TAX, process two
   turns, and assert exactly one repeat-body execution per turn and correct
   queue serialization.

Capture the seed, exact orders, preconditions, reports, and state before/after
each check. Only after those two tests pass should mixed-unit reporting,
combat-health reporting, ADDRESS rejection, and conditional-language decisions
be validated in separate slices.

## Evidence Provenance

- Facts: CLI output, player reports, independent reports, exact order files,
  and final `state.json` in this game directory.
- Player opinions: the two isolated player-agent assessments and strategy
  changes supplied after their own reports.
- Observer inferences: defect classifications, reproduction statements, and
  privacy audit in this report.
- Recommendations: sections 9-12; they are not changes made during the
  playtest.
