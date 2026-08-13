# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** calib_48.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 48 | 60.0% | 20408 | 560 |
| `random` | 32 | 40.0% | 16650 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 10, `random` 2
- **Splits:** 28 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 70 |
| secured | 10 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR001` | random | random | swept by random |
| `AR002` | scripted:balanced | random | split |
| `AR003` | random | scripted:balanced | split |
| `AR004` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR005` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR006` | random | scripted:balanced | split |
| `AR007` | scripted:balanced | random | split |
| `AR008` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR009` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR010` | random | scripted:balanced | split |
| `AR011` | scripted:balanced | random | split |
| `AR012` | random | scripted:balanced | split |
| `AR013` | scripted:balanced | random | split |
| `AR014` | scripted:balanced | random | split |
| `AR015` | scripted:balanced | random | split |
| `AR016` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR017` | random | scripted:balanced | split |
| `AR018` | scripted:balanced | random | split |
| `AR019` | random | scripted:balanced | split |
| `AR020` | random | random | swept by random |
| `AR021` | random | scripted:balanced | split |
| `AR022` | random | scripted:balanced | split |
| `AR023` | random | scripted:balanced | split |
| `AR024` | scripted:balanced | random | split |
| `AR025` | scripted:balanced | random | split |
| `AR026` | random | scripted:balanced | split |
| `AR027` | scripted:balanced | random | split |
| `AR028` | scripted:balanced | random | split |
| `AR029` | scripted:balanced | random | split |
| `AR030` | random | scripted:balanced | split |
| `AR031` | scripted:balanced | random | split |
| `AR032` | scripted:balanced | random | split |
| `AR033` | scripted:balanced | random | split |
| `AR034` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR035` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR036` | scripted:balanced | random | split |
| `AR037` | random | scripted:balanced | split |
| `AR038` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR039` | scripted:balanced | scripted:balanced | swept by scripted:balanced |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:balanced` | 2400 | 2400 | — | 100.0% | 0 | 0 |
| `random` | 2400 | 2400 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:balanced` | — | — | — | unknown |
| `random` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:balanced` | ABSORB=19, ADDRESS=80, ALLY=116, ATTACK=14, BORROW=53, BUILD=66, CHARGE=36, COLLECT=322, CONJURE=534, CREATE=147, ENEMY=162, FLY=409, FORTIFY=224, IF=565, INVEST=742, LURK=261, MINE=81, MOVE=945, NAME=887, NEUTRAL=122, PASSAGE=49, PASSWORD=80, PAY=253, POST=433, PROBE=2, PROMOTE=322, RECRUIT=3961, REPAY=202, REPORT=363, SAY=554, SCAN=39, SCRY=560, SEARCH=178, SECURE=2325, STUDY=1297, SUMMON=351, TAX=2400, TELEPORT=19, TRADE=260, TRAIN=399, UNFORTIFY=4, WORK=572 | 24.0 | 0 | +0/−0 | 90.7 |
| `random` | ATTACK=80, AWAIT=1715, COLLECT=1631, INVEST=1661, MOVE=1671, RECRUIT=3297, SECURE=1645, STUDY=1627, TAX=1666, WORK=1657 | 24.0 | 0 | +0/−0 | 33.3 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 48 | 1.0 | 0.037 | 3961 | 14 | 945 | 2325 | 2400 |
| `random` | 32 | 1.0 | 0.037 | 3297 | 80 | 1671 | 1645 | 1666 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 13.0 | 26.5 |
| `random` | 16.0 | 14.5 |

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
