# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** starter_map.json
- **Games:** 24 (30 turns each, both seat orderings per seed)
- **Decisive:** 24  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 8 | 33.3% | 6143 | 81 |
| `random` | 16 | 66.7% | 4278 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 1, `random` 5
- **Splits:** 6 / 12

## What decided each game

| Metric | Games |
|---|---:|
| gold | 15 |
| secured | 9 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | random | split |
| `AR001` | random | scripted:balanced | split |
| `AR002` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR003` | scripted:balanced | random | split |
| `AR004` | random | random | swept by random |
| `AR005` | random | scripted:balanced | split |
| `AR006` | random | random | swept by random |
| `AR007` | random | random | swept by random |
| `AR008` | random | scripted:balanced | split |
| `AR009` | random | random | swept by random |
| `AR010` | random | scripted:balanced | split |
| `AR011` | random | random | swept by random |

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
