# Benchmark Phase 0 — is there a skill gradient?

Status: **complete; remediation establishes a skill gradient.** Date: 2026-08-11.
Harness: `scripts/arena.py`. Cost: zero (no model calls).

## Why this ran first

`docs/ip_cleanroom.md` frames the clean-room work as preparation for a public
AI benchmark. A benchmark's load-bearing claim is that it *separates* strong
play from weak play. That claim had never been tested here.

Phase 0 tests it with the cheapest possible instrument: a rule-based bot
against a bot that emits legal orders at random. Both are free to run. If
deliberate play cannot beat arbitrary play, no model can separate either, and
every downstream question — which models, what prompt, held-out maps — is
premature.

## Method

`scripts/arena.py` creates headless games through `webapp.service`, then runs
the production parser and engine in memory (no server, HTTP, or per-turn
persistence). Two policies:

- **`scripted`** — `plan_orders` from `scripts/beta_100_turns.py`: taxes,
  budgets recruitment, secures its home city, seeks targets.
- **`random`** — draws 4–10 orders per turn from the same whitelist the
  strategist prompt gives an LLM. Every line parses; none of them cohere.

Score is head-to-head win rate: secured cities, controlled cities, soldiers,
surviving characters, then gold. An eliminated faction cannot win. The
original baseline below predates this scoring fix and used gold second.

**The unit of analysis is a pair, not a game.** Start cities derive from the
room code, so each seed is played twice on the *same* map with the seats
exchanged. A **sweep** — one policy winning from both seats — cannot be
explained by start-city luck; a **split** is the map talking.

> A first version of this harness gave the two orderings different room codes,
> which silently gave them different maps and made the seat swap do nothing.
> Fixed before any results below were taken.

## Results

12 seeds × 2 seat orders = 24 games per configuration, 30 turns each.

| | `world.json` (154 towns) | `starter_map.json` (6 towns) |
|---|---|---|
| scripted win rate | 54.2% | **33.3%** |
| random win rate | 45.8% | **66.7%** |
| sweeps (scripted / random) | 4 / 3 | 1 / 5 |
| splits | 5 | 6 |
| decided by `secured` / `gold` | 8 / 16 | 9 / 15 |

On the full map the result is chance. On the small map **it inverts: random
beats the deliberate bot two to one.**

## Remediation reruns

Each change was rerun independently on the existing six-town contact map with
40 seeds x 2 seat orders = 80 games, 30 turns each. Contact rules were not
changed.

| Checkpoint | Scripted wins | Random wins | Sweeps (scripted / random) | Splits | What decided games |
|---|---:|---:|---:|---:|---|
| 1. Seven-day actor budget | 32 | 48 | 4 / 12 | 24 | secured 23, gold 57 |
| 2. Work wage rebalance | 32 | 48 | 4 / 12 | 24 | secured 23, gold 57 |
| 3. Territory-first score + elimination | **49** | 31 | **9 / 0** | 31 | elimination 8, secured 15, soldiers 57 |

The wage checkpoint also has a five-turn identical-state A/B regression:
weekly WORK earns 390.5g gross while weekly TAX earns 390g gross. Work no
longer dominates territorial income.

The Phase 1 gate now passes on the contact map. Scripted play swept nine seed
pairs while random swept none, and no game was decided by gold. Forced contact
remains deferred; this result uses the small map that already produced contact
and the original inversion.

### Caveats on the gate

- **The gradient is partly mechanical.** Random still finishes with large gold
  piles (roughly 12,000-40,000g after the wage revalue) because WORK remains
  linear in `(workers + 1)` with no worker-count ceiling. The time-axis exploit
  is closed, but worker scaling is not. Scripted spends on armies, and the new
  score intentionally prefers armies to hoarded gold. That is legitimate game
  strategy, but Phase 1 must detect whether a model merely learns "recruit a
  lot" rather than demonstrating broader planning.
- **The signal is noisy.** Thirty-one of 40 seed pairs split by seat. The nine
  scripted sweeps against zero random sweeps establish a gradient, but map and
  starting-position variance still dominate most individual games.
- **The gate is contact-map only.** The full map and its contact rules are
  unchanged. Its 13/24 scripted result remains a chance baseline, not evidence
  that the fixed benchmark separates play on the 154-town map.
- **Model calls still have a compliance gate.** Each Phase 1 roster model must
  pass `python scripts/probe_model.py <model>` before the first benchmark call.
- **The worktree contains unrelated dashboard WIP.** The game-switcher changes
  in `webapp/main.py` and its template/style files are not part of this
  remediation or evidence for the gate.

## Finding 1 — on the full map, the factions never meet

Every faction in all 24 full-map games finished with `controlled: 1` and
`secured: 1`. Not one city was ever taken from anyone.

Two players on a 154-town map, moving at most a couple of towns per turn,
simply never make contact in 30 turns. The "game" is two solitaire economic
simulations running side by side, and the winner is whoever spawned on the
richer city. That is why the win rate sits at chance — there is no contest to
be good at. It also explains the `beta_100` flatline, where a faction sat at
4 soldiers and 3 secured cities from turn 10 to turn 100.

## Finding 2 — the economy has an unbounded exploit, and random finds it

On the small map the factions do meet, and the result gets worse: random wins.

Random ends games with 20,000–47,000 gold against scripted's 1,000–3,000. The
mechanism is `process_work` (`soe/phases/units.py:20`):

```python
wage = daily * order.duration_days * (workers + 1)
```

`config.DAYS_PER_TURN` is 7, but **nothing enforces that a turn's orders fit
inside a turn.** `duration_days` is read in 15 places across the phases and
budgeted in none. A character may issue `Work for 3 weeks` four times in one
7-day turn and be paid 84 days of wages.

Random spams economic verbs and stumbles into this. A bot that plays
"properly" — recruiting soldiers, securing territory — does not, and loses.

Confirmed directly (5 turns, identical otherwise):

| duplicate `Work for 3 weeks` orders per turn | 1 | 2 | 4 | 8 |
|---|---:|---:|---:|---:|
| final gold | 1231 | 1252 | 1504 | 2848 |

And by income attribution over 6 turns of random play: **WORK 2,188g** vs tax
650g. Labour, not territory or trade, is the dominant income source.

## Finding 3 — the score rewards the wrong thing

`secured` decided only a third of games; gold decided the rest. Since gold is
the exploitable quantity, the tiebreak hands the game to whoever exploits
hardest.

Worse, several games were won by a faction with `characters_alive: 0` — its
leader dead, its army gone, its gold pile intact. Any scoring rule that lets a
faction win after being wiped out is not measuring strategy.

## What the baseline meant for the benchmark

Before remediation, **the thesis was not refuted; it was untestable in that
configuration.** Nothing in the baseline said models could not be separated by
this game. It showed that the original setup could not separate anything,
because the factions never fought, the economy paid for spam, and the score
rewarded hoarding.

The remediation sequence resolved two of the three issues and deliberately
deferred the other:

1. **Per-turn time budget: complete.** Timed orders release at most
   `DAYS_PER_TURN` per actor; excess duration remains queued.
2. **Force contact: deferred.** Phase 1 is restricted to the existing small
   map. Full-map benchmarking remains out of scope until contact is designed.
3. **Territory-first score and elimination: complete.** Gold is the final
   tiebreak, and eliminated factions cannot win.

Phase 1 is therefore defensible only on the contact map, subject to the noisy
and partly mechanical gradient described above.

## Reproducing

```bash
python scripts/arena.py --seeds 40 --turns 30                          # full map
python scripts/arena.py --seeds 40 --turns 30 --map starter_map.json   # small map
```

Reports land in `games/arena/`. Runs are deterministic: policies are seeded
per seat and turn, so a rerun of a matchup is byte-identical.

## Roster for later phases

Before Phase 1 begins, the models named for comparison are
`poolside/laguna-s-2.1:free` and `nvidia/nemotron-3-ultra-550b-a55b:free`.
Both need `python scripts/probe_model.py <model>` for order-format compliance
first, and free-tier rate limits will pace any large matrix.
