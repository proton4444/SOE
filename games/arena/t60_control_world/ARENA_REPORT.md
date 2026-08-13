# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** world.json
- **Games:** 80 (60 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 36 | 45.0% | 35163 | 462 |
| `random` | 44 | 55.0% | 33585 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 8, `random` 12
- **Splits:** 20 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 49 |
| secured | 28 |
| gold | 3 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR001` | random | scripted:balanced | split |
| `AR002` | random | random | swept by random |
| `AR003` | random | scripted:balanced | split |
| `AR004` | random | scripted:balanced | split |
| `AR005` | random | random | swept by random |
| `AR006` | scripted:balanced | random | split |
| `AR007` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR008` | random | scripted:balanced | split |
| `AR009` | random | random | swept by random |
| `AR010` | scripted:balanced | random | split |
| `AR011` | random | scripted:balanced | split |
| `AR012` | random | random | swept by random |
| `AR013` | random | random | swept by random |
| `AR014` | random | scripted:balanced | split |
| `AR015` | random | scripted:balanced | split |
| `AR016` | random | scripted:balanced | split |
| `AR017` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR018` | random | random | swept by random |
| `AR019` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR020` | random | scripted:balanced | split |
| `AR021` | random | scripted:balanced | split |
| `AR022` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR023` | random | random | swept by random |
| `AR024` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR025` | random | scripted:balanced | split |
| `AR026` | scripted:balanced | random | split |
| `AR027` | random | random | swept by random |
| `AR028` | random | scripted:balanced | split |
| `AR029` | random | scripted:balanced | split |
| `AR030` | random | random | swept by random |
| `AR031` | random | random | swept by random |
| `AR032` | random | random | swept by random |
| `AR033` | scripted:balanced | random | split |
| `AR034` | scripted:balanced | random | split |
| `AR035` | random | scripted:balanced | split |
| `AR036` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR037` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR038` | random | random | swept by random |
| `AR039` | random | scripted:balanced | split |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:balanced` | 4800 | 4800 | — | 100.0% | 0 | 0 |
| `random` | 4800 | 4800 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:balanced` | — | — | — | unknown |
| `random` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:balanced` | ABSORB=60, ADDRESS=80, ALLY=163, ATTACK=17, BORROW=117, BUILD=130, BUY_SHIP=13, CHARGE=77, COLLECT=512, CONJURE=583, CREATE=181, ENEMY=297, FLY=136, FORTIFY=120, IF=686, INVEST=407, LURK=570, MINE=126, MOVE=4070, NAME=640, NEUTRAL=180, PASSAGE=28, PASSWORD=80, PAY=388, POST=853, PROBE=3, PROMOTE=249, RECRUIT=7672, REPAY=420, REPORT=681, SAIL=22, SAY=1055, SCAN=125, SCRY=619, SEARCH=320, SECURE=4517, STUDY=1788, SUMMON=800, TAX=4800, TELEPORT=61, TRADE=441, TRAIN=298, UNFORTIFY=4, WORK=774 | 17.0 | 0 | +0/−0 | 47.1 |
| `random` | ATTACK=50, AWAIT=3396, COLLECT=3335, INVEST=3395, MOVE=3343, RECRUIT=6679, SECURE=3328, STUDY=3366, TAX=3318, WORK=3375 | 17.0 | 0 | +0/−0 | 37.5 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 36 | 1.0 | 0.013 | 7672 | 17 | 4070 | 4517 | 4800 |
| `random` | 44 | 1.0 | 0.013 | 6679 | 50 | 3343 | 3328 | 3318 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 25.0 | 46.0 |
| `random` | 31.0 | 41.0 |

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
