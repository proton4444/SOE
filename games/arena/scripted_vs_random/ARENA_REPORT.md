# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** world.json
- **Games:** 24 (30 turns each, both seat orderings per seed)
- **Decisive:** 24  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 13 | 54.2% | 6068 | 53 |
| `random` | 11 | 45.8% | 4972 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 4, `random` 3
- **Splits:** 5 / 12

## What decided each game

| Metric | Games |
|---|---:|
| gold | 16 |
| secured | 8 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | random | random | swept by random |
| `AR001` | random | random | swept by random |
| `AR002` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR003` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR004` | random | scripted:balanced | split |
| `AR005` | random | scripted:balanced | split |
| `AR006` | scripted:balanced | random | split |
| `AR007` | random | random | swept by random |
| `AR008` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR009` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR010` | random | scripted:balanced | split |
| `AR011` | random | scripted:balanced | split |

## Reading this

The headline number is sweeps, not raw win rate. Raw win rate mixes
skill with start-city luck; a sweep controls for the map.

If `scripted` does not sweep clearly more often than `random`, the
game has no skill gradient at this length, and that is a finding about
the game rather than the policies: deliberate play and arbitrary legal
play reach the same place, and no model could separate either. Any
benchmark claim rests on this first.

Watch `decided_by` too. If games are decided by `gold` rather than
`secured`, the contest is an economic tiebreak, not a struggle for
territory, and the scoring metric may be measuring the wrong thing.
