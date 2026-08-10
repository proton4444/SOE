# SOE Eight-Turn Multi-Agent Playtest

## Scope and Method

- Campaign: `agent_playtest_20260810_145237`
- Setup: `maps/sample_map.json`, `examples/players.yaml`, `rules.md`, `cli.py`
- Seeds: `42001` through `42008`, one resolution per turn, no `--force`
- Roles: independent Player 1, Player 2, and neutral observer contexts
- Boundary: only this new campaign directory was written

No `AGENTS.md` exists under the repository root. No existing game was modified.

## Verification

- Baseline: `571 passed in 4.82s`
- Final: `571 passed in 5.13s`
- Final state load: successful, `turn_number=8`
- Final campaign artifacts: 16 player order files, 16 player reports, zero queued entries

## Campaign Summary

The campaign completed eight deterministic turns without a crash, state-load failure, or need to stop early. Player 1 developed Madegi Doy, secured it, recruited soldiers and workers, offered for Bishop Nancy Lopenda, expanded to Kitesta, and returned to its capital. Player 2 recovered from an early naval overspend, worked for income, recruited soldiers and sailors, retained a galley, sailed to Madegi Doy on Turn 8, and declined a poor-odds attack. No victory condition, score, elimination, or winner was introduced.

## Turn-by-Turn Narrative

1. **Turn 1, seed 42001:** Player 1 recruited workers and bought horses; several implicit-actor, naming, and trading orders failed. Player 2 bought a galley and attempted recruitment, an independent offer, naming, grouping, and naval pressure. The offer reported insufficient gold but still produced a Wizard group-membership side effect.
2. **Turn 2, seed 42002:** Player 1 created a seven-day wait queue; a missing period after a message swallowed later orders. Player 2 could not recruit or collect taxes after spending the starting purse on the galley.
3. **Turn 3, seed 42003:** Player 1 halted and rebuilt the queue, recruited 20 soldiers, secured Madegi Doy, and collected taxes. Player 2's galley sale, recruitment, passage, and attack attempts failed; the faction remained in an economic deadlock.
4. **Turn 4, seed 42004:** Player 1's queue remained active and collected three weeks of tax. Player 2's `WORK` earned 89.6g, but the `IF` conditions were evaluated before that work and skipped their dependent orders.
5. **Turn 5, seed 42005:** Player 1's queued Bishop offer succeeded. Player 2 recruited 31 soldiers and 50 sailors, collected taxes, paid wages, and maintained diplomacy.
6. **Turn 6, seed 42006:** Player 1 moved to and secured Kitesta; a same-turn Bishop join failed because the Bishop was still at Madegi Doy. Player 2's repeated `NAME` attempt failed, so all dependent grouping and sailing orders failed.
7. **Turn 7, seed 42007:** Player 1 moved the Bishop to Kitesta and joined her successfully. Player 2's `sail to outside Madegi Doy` was parsed as a nonexistent city, so no movement occurred.
8. **Turn 8, seed 42008:** Player 1 returned to Madegi Doy, collected tax, and paid wages. Player 2 used the bare `sail to Madegi Doy` form successfully with the galley and 81 units, then declined combat because the odds were too poor.

## Player Experience Findings

### Facts

- Both players could interpret private reports, revise plans, use diplomacy, recruit, tax, work, queue waits, move, secure, report, and sail.
- Reports were faction-scoped in the observed run. No opposing orders or unrelated private reports were exposed to either player context.
- The players experienced meaningful uncertainty about queue timing, taxation prerequisites, independent-character ownership, naming syntax, and sea movement syntax.
- The first Player 2 order file had a coordinator-generated UTF-8 BOM, which prevented its first order from parsing. Future order files were written without a BOM. This is a harness/environment note, not an engine defect finding.

### Player Opinions

- Player 1 repeatedly described the Bishop offer, Kitesta sovereignty, and queue completion as uncertain and adapted by separating offer, wait, join, movement, and reporting orders.
- Player 2 considered the failed naming path unusable, treated the galley sale as unexplained, and adapted from `outside Madegi Doy` to bare `Madegi Doy` after the parser warning.

### Observer Inferences

- The natural-language surface is credible enough to support strategic play, but error messages and report ordering make it difficult to distinguish a failed order, a deferred order, and a state transition that will occur in a later phase.
- Queue persistence is valuable and should be protected, but queued orders need clearer visibility about when each entry will execute and which phase will process it.

## Confirmed Defects

### 1. Failed independent offer mutates group membership

- Classification: **BROKEN**
- Severity: **major**
- Turn/seed: Turn 1 / `42001`
- Exact order: `Offer 1800 gold to Wizard Ojibenmi and have him join Khan Tengri.`
- Player-visible preconditions: Wizard Ojibenmi was independent at Albatross City; Khan Tengri had insufficient funds after buying the galley.
- Expected: A failed offer should not attach the independent character to the player's group.
- Actual: The report showed insufficient gold, but also showed Wizard Ojibenmi joining Khan Tengri's group. Persisted state retained independent faction ownership alongside Player 2 group membership through Turn 8.
- Reproduced: Persisted inconsistency observed on Turns 1-8.

### 2. `NAME` cannot resolve the acting faction/player

- Classification: **BROKEN**
- Severity: **major**
- Turns/seeds: Turns 1, 2, and 6 / `42001`, `42002`, `42006`
- Exact order: `Name male sailor Arslan Tideborn.`
- Player-visible preconditions: Player 2 had an available sailor pool by Turn 6.
- Expected: Name one available sailor, then allow assignment and sailing orders to target that character.
- Actual: The report repeatedly said `Character player_2 not found`; all dependent `ASSIGN`, `SAIL`, and `REPORT` orders failed.
- Reproduced: Yes, including after 50 sailors existed and the order file had no BOM.

### 3. Trading study is rejected despite being a rules-defined skill

- Classification: **BROKEN**
- Severity: **moderate**
- Turn/seed: Turn 1 / `42001`
- Exact order: `Study trading to level 20.`
- Player-visible preconditions: Emperor Marcus was the active leader and had starting gold.
- Expected: A rules-defined `trading` study order should parse or produce a specific eligibility/resource failure.
- Actual: The report said the order could not parse and no actor was specified.
- Reproduced: Yes in the Turn 1 player report.

### 4. Explicit reports mislabel all group units as soldiers

- Classification: **BROKEN**
- Severity: **moderate**
- Turns/seeds: Turns 6 and 8 / `42006`, `42008`
- Exact orders: `Report.` and `Have Khan Tengri report.`
- Player-visible preconditions: Player 1 had 20 soldiers plus 30 workers; Player 2 had 31 soldiers plus 50 sailors.
- Expected: Reports should preserve unit types and counts.
- Actual: Player 1's explicit report said 50 soldiers; Player 2's said 81 soldiers. The detailed unit summaries showed the correct separate types.
- Reproduced: Yes for both factions.

### 5. Wage-debt event text disagrees with persisted state

- Classification: **BROKEN**
- Severity: **moderate**
- Turns/seeds: Turns 5 and 8 / `42005`, `42008`
- Exact orders: `Have Khan Tengri pay.` and `Pay.`
- Player-visible preconditions: Each faction had wage debt and also incurred upkeep during the same resolution.
- Expected: The report event sequence and final faction summary should reconcile with persisted debt.
- Actual: Reports showed debt paid to zero, then added new debt during income/upkeep and displayed a contradictory ending debt. Persisted state loaded with zero debt in the final verification.
- Reproduced: Yes across both factions and multiple turns.

### 6. Documented `SAIL to outside <city>` syntax is unsupported

- Classification: **BROKEN**
- Severity: **moderate**
- Turn/seed: Turn 7 / `42007`
- Exact order: `Have Khan Tengri sail to outside Madegi Doy.`
- Player-visible preconditions: Player 2 had a galley, 50 sailors, and sufficient forces for sea movement.
- Expected: The documented `outside` destination form should resolve as sea movement.
- Actual: The parser treated `outside Madegi Doy` as a city name and reported `Destination city not found`.
- Reproduced: Yes. The corrected bare form `Have Khan Tengri sail to Madegi Doy.` succeeded on Turn 8.

### 7. Plaintext password remains in raw state

- Classification: **BROKEN/security**
- Severity: **major at-rest exposure**
- Evidence: Observer inspection of `state.json` found a plaintext password field. No password value appeared in player reports, and no player was allowed to inspect raw state during play.
- Expected: Credentials should not be persisted as plaintext in a state file that may be copied or backed up.
- Actual: Raw coordinator state contains the credential material.
- Reproduced: Present in the final state.

## UNDEFINED Items Requiring Product Decisions

- **Queue phase semantics:** On Turn 6, a fresh `JOIN` failed because a queued leader movement completed in the movement phase before the join phase. Decide whether same-turn cross-character joins should be ordered by user sequence, documented as phase-ordered, or surfaced with a clearer pending prerequisite.
- **`IF` timing relative to `WORK`:** On Turn 4, `WORK` earned money after the `IF` conditions had already evaluated. Decide whether conditions intentionally observe start-of-turn state or should observe preceding orders.
- **Kitesta sovereignty:** `SECURE Kitesta` created occupation and administration while sovereignty remained `none`. This is consistent with the separate sovereignty/occupation mechanics, but the player-facing path for sovereignty is not clear.
- **Fog at shared locations:** Same-location notable-person visibility was consistent with the stochastic implementation, but deterministic expectations for what becomes visible when two factions share a city are not explicit.
- **Galley sale semantics:** `Have Khan Tengri sell 1 galley.` failed while the report listed one galley. The campaign did not isolate whether this is a parser, ownership, or economic-rule issue.

## Parser and Order-Language Friction

- Missing punctuation after a quoted message caused following orders to be swallowed; the parser did provide a warning.
- `Have Khan Tengri tell Emperor Marcus "...".` sent the message but swallowed a following `BUY PASSAGE` order, while the simpler `Tell Khan Tengri "...".` form split correctly. The grammar difference needs documentation or normalization.
- Implicit actor forms varied: `Study magic` and some promotion/tax forms executed, while `Study trading`, `NAME`, and dependent named-character orders did not.
- The `outside` sailing qualifier is documented but rejected; the player discovered a working bare-destination workaround only through a later report.
- `PAY` and `TAX` produce state-sensitive results, but reports should make phase timing and target-location assumptions explicit.

## Queue and Persistence Findings

- `WAIT` created durable pending queues across turns.
- `HALT` canceled the queued entries visible in the report and allowed Player 1 to rebuild the plan safely.
- Queue execution continued across later turns without rerunning a processed turn.
- Final state loaded successfully at turn 8 with zero queue entries.
- No state corruption or turn-number regression occurred.

## Strategic-System Observations

- Economic prerequisites materially shaped strategy: a galley purchase consumed Player 2's starting purse, and tax collection required soldiers, creating a recoverable but confusing deadlock.
- `WORK` provided a credible recovery route, after which one soldier unlocked tax income and enabled recruitment of a naval force.
- Diplomacy and messages were useful under uncertainty; both players exchanged a provisional non-aggression position without introducing a victory condition.
- Naval movement worked once the player used a supported destination form; the cautious attack correctly declined when odds were poor, with no casualties.
- `SECURE` separated occupation/administration from sovereignty. That distinction should remain intact and be explained more clearly rather than simplified away.

## Protected Mechanics

Do not simplify away the mechanics that proved valuable in the playtest:

- Independent faction ownership versus player group membership, once the failed-offer mutation is fixed.
- Private faction-scoped reports and fog-of-war filtering.
- Durable queues, `WAIT`, `HALT`, and deferred multi-turn consequences.
- Separate sovereignty, occupation, and administration statuses.
- Resource-gated recruitment, tax collection, upkeep, wage debt, and naval logistics.
- Deterministic seeded resolution and cautious combat refusal when odds are poor.

## Smallest Safe Next Validation Slice

Create a focused regression slice without changing the campaign state:

1. Add parser/engine tests for `NAME` with a live sailor pool, including dependent `ASSIGN` and `SAIL` orders.
2. Add an offer-failure test proving no group membership mutation when funds are insufficient.
3. Add report tests for mixed soldiers/workers/sailors and for wage-debt reconciliation against persisted state.
4. Add a movement parser test for documented `SAIL to outside <city>` syntax.
5. Re-run a two-turn scratch game covering queue movement plus cross-character join and `IF` after `WORK`; do not replay the processed campaign state.
