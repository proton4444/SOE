# Benchmark Phase 0 — is there a skill gradient?

Status: **complete, and the answer is no — not yet.** Date: 2026-08-11.
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

`scripts/arena.py` runs headless games against `webapp.service` directly (no
server, no HTTP). Two policies:

- **`scripted`** — `plan_orders` from `scripts/beta_100_turns.py`: taxes,
  budgets recruitment, secures its home city, seeks targets.
- **`random`** — draws 4–10 orders per turn from the same whitelist the
  strategist prompt gives an LLM. Every line parses; none of them cohere.

Score is head-to-head win rate: most secured cities, then gold, soldiers,
surviving characters as tiebreaks.

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

## What this means for the benchmark

**The thesis is not refuted — it is untestable in the current configuration.**
Nothing here says models cannot be separated by this game. It says the game as
currently set up cannot separate *anything*, because the factions never fight,
the economy pays for spam, and the score rewards hoarding.

Spending on Phase 1/2 now would buy a number with no meaning. The three fixes
are all cheap and all things the game wants regardless of whether a benchmark
ever ships:

1. **Enforce a per-turn time budget.** Orders in one turn must fit in
   `DAYS_PER_TURN`. This is a real rules concept (`DAYS_PER_MONTH` already
   exists in config) that was never wired into resolution.
2. **Force contact.** Small maps, or seeded starts within a few towns of each
   other, or many more factions on the big map. Benchmark games must be
   contests.
3. **Fix the score.** Territory should dominate; elimination should be
   decisive; gold should be a weak tiebreak at most.

Re-run Phase 0 after each. The gate to Phase 1 is `scripted` sweeping `random`
convincingly — that is what a skill gradient looks like, and it costs nothing
to check.

## Reproducing

```bash
python scripts/arena.py --seeds 12 --turns 30                          # full map
python scripts/arena.py --seeds 12 --turns 30 --map starter_map.json   # small map
```

Reports land in `games/arena/`. Runs are deterministic: policies are seeded
per seat and turn, so a rerun of a matchup is byte-identical.

## Roster for later phases

When Phase 1 becomes worth running, the models named for comparison are
`poolside/laguna-s-2.1:free` and `nvidia/nemotron-3-ultra-550b-a55b:free`.
Both need `python scripts/probe_model.py <model>` for order-format compliance
first, and free-tier rate limits will pace any large matrix.
