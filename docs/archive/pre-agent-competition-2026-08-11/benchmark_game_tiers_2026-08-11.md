# Benchmark game tiers

- **Status:** format locked; implementation and model runs pending.
- **Date:** 2026-08-11.
- **Depends on:** `docs/benchmark_phase0_2026-08-11.md`.

## Decision

The tiers describe **game types**, not model price or capability bands. They
increase the strategic surface while keeping the same engine and order
language:

| Tier | Game type | Players | Map | Turns | Primary question |
|---|---|---:|---|---:|---|
| 1 | Contact duel | 2 | `starter_map.json` (6 towns) | 30 | Can the agent turn legal orders into coherent territorial play? |
| 2 | Regional conflict | 4 | generated 24-town regional maps | 50 | Can it adapt to several opponents, fog, diplomacy, and changing threats? |
| 3 | Imperial campaign | 6 | generated 154-town worlds | 100 | Can a complete agent system sustain long-horizon strategy at full scale? |

Tier 1 is the comparison benchmark. Tier 2 is the strategic benchmark. Tier 3
is the flagship campaign. Results from different tiers are reported
separately; they are not combined into one score.

## Rules shared by every tier

### Match integrity

- All competitors use the production parser and engine. No benchmark-only
  orders or state mutations are allowed.
- Engine randomness is seeded and replayable. Model inference is recorded as
  submitted order text, but model output itself is not claimed to be
  deterministic.
- A model sees only its faction's report, structured fog-of-war state, and the
  same rules/command prompt supplied to every competitor in that tier.
- Credentials, provider names, retry state, and hidden map seeds never enter a
  model prompt.
- A failed model call produces no orders for that turn. It is counted as a
  reliability failure, not silently retried into a different result beyond the
  published retry policy.

### Agent configuration

- Tier 1 and Tier 2 compare the strategist model directly: one strategist call
  per faction per turn, temperature `0.0`, vision off, and no subagents.
- Tier 3 evaluates the complete agent configuration. Vision and subagents may
  be enabled, but every entrant must declare its strategist model, subagent
  model, prompt version, token limits, and retry policy.
- Prompts, token budgets, and engine commit are frozen before an official run.
  Prompt changes create a new benchmark version.
- Every model must pass `python scripts/probe_model.py <model>` before it can
  enter a game. The probe is a syntax gate, not a benchmark result.

### Outcome and reliability reporting

An eliminated faction cannot win. All surviving factions place above all
eliminated factions. Eliminated factions are ordered by elimination turn
(later is better), with same-turn eliminations tied. Surviving factions are
ordered by:

1. secured cities;
2. controlled cities;
3. soldiers;
4. surviving characters;
5. gold.

Gold remains the final tiebreak so economic order spam cannot dominate the
result. Every report must also publish calls attempted, calls failed, parsed
orders, parser warnings, eliminations, contact turns, wall time, and token/cost
totals where the provider exposes them. A benchmark result without the raw
orders and run manifest is provisional.

A **parseable model call** contains the required order marker and at least one
order accepted by the production parser. A **hostile contact** occurs when a
valid attack or capture targets another faction, opposing factions resolve
combat, or a faction attempts to secure a city held by another faction. Merely
seeing another faction through fog of war is not hostile contact.

## Tier 1: contact duel

### Format

- Two factions on the fixed six-town contact map.
- Thirty turns, with early termination only when one faction is eliminated.
- Each seed is played twice with the competitors exchanging seats.
- Official set: 20 seed pairs (40 games) per matchup. A four-pair smoke run is
  required before spending the official call budget.
- Initial reference matches are `model vs random`, `model vs scripted`, and
  then `model vs model`. The random and scripted policies are frozen from the
  Phase 0 harness.

The paired seed is the unit of analysis. Report raw wins, but use sweep counts
and the paired sweep differential as the headline comparison. A split says the
start position dominated that pair and does not distinguish the competitors.

### Scope

Tier 1 emphasizes movement, recruitment, work/tax choices, securing territory,
and attack timing. All legal orders remain available; this is an emphasis
created by the compact map, not an artificial command whitelist.

### Entry and completion gates

The game format is ready because the Phase 0 scripted policy swept random on
nine of 40 pairs while random swept none. A model completes Tier 1 only when:

- the syntax probe passes;
- all 40 official games reach their recorded end state without engine error;
- at least 95% of model calls are parseable model calls;
- its sweep count exceeds random's in their direct matchup; and
- it records at least one sweep against the scripted reference policy.

The last gate is deliberately modest: Tier 1 establishes competence and
separation, not a claim that the model is stronger than the reference bot.

### Required implementation

- Add an LLM-backed arena policy that uses the existing `brain` and strategist
  prompt without going through HTTP or mutating state outside `engine.run_turn`.
- Persist the prompt version, model configuration, raw response, extracted
  orders, usage, latency, and failure class in the arena result bundle.
- Add early elimination, smoke/official run modes, and a resumable checkpoint
  so provider rate limits do not invalidate a batch.

## Tier 2: regional conflict

### Format

- Four factions on generated 24-town, four-region maps. Population bands scale
  proportionally from the full-world profile: 12 tiny, eight small, three
  medium, and one large town.
- Fifty turns, or early termination when only one faction remains.
- Eight public development maps and 12 held-out official map seeds.
- On each map, use four cyclic seat rotations so every entrant occupies every
  start slot exactly once. Do not use all 24 permutations.
- The standard pod contains four entrants. If fewer than four qualifying
  models are available, fill empty seats with the frozen scripted policy and
  label the run a qualification pod rather than an official ranking pod.

### Scope

Tier 2 adds simultaneous threats, opportunistic conflict, fog-of-war
interpretation, diplomacy, support, sea movement, and recovery after losses.
The primary result is mean finishing place across maps and rotations. Also
report first-place rate, survival rate, territory at turn 50, and results by
start slot. Ties receive the average of the occupied finishing places.

### Entry and completion gates

Tier 2 work begins only after at least two models complete Tier 1. Before model
runs, a free-policy calibration must show:

- at least 80% of games produce hostile contact by turn 20;
- scripted finishes above random on mean placement;
- no start slot wins more than 40% of calibration games; and
- the same manifest replays to the same final state hash.

A model completes Tier 2 when it finishes all held-out rotations, has no engine
errors, has parseable model calls on at least 95% of calls, and finishes
above the random policy on mean placement. Ranking claims require an official
pod; qualification pods only support pass/fail claims.

### Required implementation

- Generalize `scripts/arena.py` from exactly two policies to four-player pods.
- Generate or stage map files by seed and store the generator version and map
  hash in the run manifest.
- Fix the generator's population-band allocator to scale `BAND_WEIGHTS` to the
  requested town count. It currently truncates the full-world counts, which
  makes a 24-town map contain only tiny towns.
- Add cyclic seat rotation, multiplayer placement/tie handling, contact-turn
  instrumentation, and per-seat summaries.
- Validate that generated 24-town maps remain connected and give every start a
  reachable opponent before turn 20 under the calibration policies.

## Tier 3: imperial campaign

### Format

- Six factions on full generated 154-town worlds.
- One hundred turns, or early termination when only one faction remains.
- Three held-out world seeds, each played through six cyclic seat rotations.
- One declared complete agent configuration per seat. Tier 3 may compare model
  stacks, not just a single strategist model.

### Scope

Tier 3 exercises the full system: long-range expansion, economy, naval travel,
magic, religion, intelligence, diplomacy, resource conversion, attrition, and
multi-turn order queues. The primary result is mean finishing place. Report
first-place rate, survival, secured and controlled territory, contact timing,
territorial turnover, order diversity, reliability, token use, and cost.

Tier 3 is not an automatic extension of Tier 2. Phase 0 showed that two players
on the full world may never meet, so a six-player calibration must prove that
the format creates a contest before any model result is accepted.

### Entry and completion gates

Tier 3 begins only after the Tier 2 calibration passes and at least two models
complete Tier 2. Its free-policy calibration must show:

- every faction has hostile contact by turn 40 in at least 80% of games;
- at least half of games record a secured-city transfer or an elimination;
- scripted finishes above random on mean placement;
- no start slot wins more than 35% of calibration games; and
- all 100-turn games replay to their recorded final state hash.

An agent configuration completes Tier 3 only after all 18 held-out games finish
without engine error and at least 95% of its calls are parseable model calls.
Tier 3 winners are named only after the complete matrix finishes; partial runs
are published as campaign case studies, not rankings.

### Required implementation

- Extend the pod harness to six factions and 100-turn resumable runs.
- Add full run manifests, immutable map/prompt hashes, token and cost accounting,
  and per-turn state-hash verification.
- Add campaign metrics for contact, territory transfer, elimination, order
  families, and resource/economic development.
- Run the six-player full-world calibration. If it misses the contact gate,
  change the game format (start placement, player density, or map size) and
  rerun calibration; do not reinterpret a no-contact result as model skill.

## Execution order

1. Freeze the current Phase 0 remediation and its reproducible evidence.
2. Implement the Tier 1 LLM policy, manifests, checkpointing, and tests.
3. Probe the selected models, run the Tier 1 smoke matrix, then the official
   Tier 1 matrix.
4. Build and calibrate the four-player regional harness without model calls.
5. Run Tier 2 qualification pods, then an official pod when four entrants
   qualify.
6. Build and calibrate the six-player full-world format without model calls.
7. Freeze the Tier 3 prompt, maps, and configurations; then run the 18-game
   held-out campaign matrix.

## Versioned outputs

Each official tier run writes to `games/arena/<run_id>/`:

- `manifest.json`: engine commit, dirty-tree flag, map and prompt hashes,
  policies/models, inference settings, seeds, rotations, and retry policy;
- `games.jsonl`: one final record per game;
- `turns.jsonl`: per-turn outcome, reliability, contact, and usage metrics;
- `orders/`: exact submitted order text and parser feedback;
- `ARENA_REPORT.md`: human-readable summary generated from those records.

Public development seeds may be used for debugging. Held-out seeds must not be
committed before the official run; publish them with the completed result so
the run can be independently replayed afterward.
