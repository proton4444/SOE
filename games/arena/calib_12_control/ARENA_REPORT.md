# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** calib_12.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 69 | 86.3% | 20273 | 681 |
| `random` | 11 | 13.8% | 16534 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 30, `random` 1
- **Splits:** 9 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 67 |
| secured | 11 |
| gold | 1 |
| elimination | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR001` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR002` | random | scripted:balanced | split |
| `AR003` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR004` | random | scripted:balanced | split |
| `AR005` | random | scripted:balanced | split |
| `AR006` | scripted:balanced | random | split |
| `AR007` | scripted:balanced | random | split |
| `AR008` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR009` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR010` | scripted:balanced | random | split |
| `AR011` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR012` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR013` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR014` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR015` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR016` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR017` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR018` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR019` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR020` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR021` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR022` | random | random | swept by random |
| `AR023` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR024` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR025` | random | scripted:balanced | split |
| `AR026` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR027` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR028` | scripted:balanced | random | split |
| `AR029` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR030` | random | scripted:balanced | split |
| `AR031` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR032` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR033` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR034` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR035` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR036` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR037` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR038` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR039` | scripted:balanced | scripted:balanced | swept by scripted:balanced |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:balanced` | 2400 | 2400 | — | 100.0% | 0 | 0 |
| `random` | 2400 | 2400 | — | 99.3% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:balanced` | — | — | — | unknown |
| `random` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:balanced` | ABSORB=54, ADDRESS=80, ALLY=123, ATTACK=69, BORROW=60, BUILD=67, CAPTURE=46, CHARGE=66, COLLECT=288, CONJURE=555, CREATE=226, ENEMY=159, ENSLAVE=1, FLY=771, FORTIFY=261, FREE=3, IF=567, INTERROGATE=3, INVEST=927, KILL=3, LURK=263, MINE=85, MOVE=167, NAME=1030, NEUTRAL=118, PASSAGE=13, PASSWORD=80, PAY=191, POST=353, PROBE=22, PROMOTE=373, RECRUIT=3568, REPAY=169, REPORT=391, SAY=601, SCAN=47, SCRY=562, SEARCH=354, SECURE=2233, STUDY=1223, SUMMON=322, TAX=2384, TELEPORT=25, TRADE=226, TRAIN=513, UNFORTIFY=10, WORK=621 | 6.5 | 0 | +0/−0 | 122.1 |
| `random` | ATTACK=145, AWAIT=1693, COLLECT=1613, INVEST=1656, MOVE=1656, RECRUIT=3274, SECURE=1622, STUDY=1579, TAX=1657, WORK=1639 | 6.5 | 2 | +0/−0 | 37.2 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 69 | 1.0 | 0.075 | 3568 | 69 | 167 | 2233 | 2384 |
| `random` | 11 | 0.975 | 0.075 | 3274 | 145 | 1656 | 1622 | 1657 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 12.0 | 16.0 |
| `random` | 16.0 | 15.0 |

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
