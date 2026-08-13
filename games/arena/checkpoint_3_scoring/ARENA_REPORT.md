# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** starter_map.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 49 | 61.3% | 21157 | 309 |
| `random` | 31 | 38.8% | 15845 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 9, `random` 0
- **Splits:** 31 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 57 |
| secured | 15 |
| elimination | 8 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR001` | random | scripted:balanced | split |
| `AR002` | scripted:balanced | random | split |
| `AR003` | scripted:balanced | random | split |
| `AR004` | random | scripted:balanced | split |
| `AR005` | random | scripted:balanced | split |
| `AR006` | scripted:balanced | random | split |
| `AR007` | random | scripted:balanced | split |
| `AR008` | scripted:balanced | random | split |
| `AR009` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR010` | random | scripted:balanced | split |
| `AR011` | scripted:balanced | random | split |
| `AR012` | scripted:balanced | random | split |
| `AR013` | random | scripted:balanced | split |
| `AR014` | scripted:balanced | random | split |
| `AR015` | scripted:balanced | random | split |
| `AR016` | scripted:balanced | random | split |
| `AR017` | scripted:balanced | random | split |
| `AR018` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR019` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR020` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR021` | scripted:balanced | random | split |
| `AR022` | random | scripted:balanced | split |
| `AR023` | random | scripted:balanced | split |
| `AR024` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR025` | random | scripted:balanced | split |
| `AR026` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR027` | scripted:balanced | random | split |
| `AR028` | scripted:balanced | random | split |
| `AR029` | random | scripted:balanced | split |
| `AR030` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR031` | scripted:balanced | random | split |
| `AR032` | random | scripted:balanced | split |
| `AR033` | random | scripted:balanced | split |
| `AR034` | scripted:balanced | random | split |
| `AR035` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR036` | random | scripted:balanced | split |
| `AR037` | random | scripted:balanced | split |
| `AR038` | scripted:balanced | random | split |
| `AR039` | random | scripted:balanced | split |

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
