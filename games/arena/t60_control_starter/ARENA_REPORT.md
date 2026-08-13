# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** starter_map.json
- **Games:** 80 (60 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 49 | 61.3% | 35362 | 431 |
| `random` | 31 | 38.8% | 30409 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 9, `random` 0
- **Splits:** 31 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 48 |
| secured | 18 |
| elimination | 14 |

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
| `AR009` | scripted:balanced | random | split |
| `AR010` | random | scripted:balanced | split |
| `AR011` | scripted:balanced | random | split |
| `AR012` | scripted:balanced | random | split |
| `AR013` | random | scripted:balanced | split |
| `AR014` | scripted:balanced | random | split |
| `AR015` | scripted:balanced | random | split |
| `AR016` | scripted:balanced | random | split |
| `AR017` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR018` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR019` | random | scripted:balanced | split |
| `AR020` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR021` | scripted:balanced | random | split |
| `AR022` | random | scripted:balanced | split |
| `AR023` | random | scripted:balanced | split |
| `AR024` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR025` | random | scripted:balanced | split |
| `AR026` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR027` | scripted:balanced | random | split |
| `AR028` | scripted:balanced | random | split |
| `AR029` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
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

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:balanced` | 4800 | 4800 | — | 100.0% | 0 | 0 |
| `random` | 4800 | 4800 | — | 90.3% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:balanced` | — | — | — | unknown |
| `random` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:balanced` | ABSORB=145, ADDRESS=80, ALLY=192, ATTACK=450, BORROW=139, BUILD=131, BUY_SHIP=87, CAPTURE=271, CHARGE=191, COLLECT=442, CONJURE=581, CREATE=444, ENEMY=273, ENSLAVE=14, FLY=541, FORTIFY=340, FREE=18, IF=689, INTERROGATE=31, INVEST=1133, KILL=19, LURK=495, MINE=136, MOVE=2515, NAME=1119, NEUTRAL=175, PASSAGE=33, PASSWORD=80, PAY=382, POST=855, PROBE=128, PROMOTE=431, RECRUIT=5850, REPAY=353, REPORT=695, SAIL=89, SAY=932, SCAN=137, SCRY=634, SEARCH=844, SECURE=4255, STUDY=1776, SUMMON=774, TAX=4447, TELEPORT=136, TRADE=434, TRAIN=625, UNFORTIFY=11, WORK=810 | 8.0 | 0 | +0/−0 | 220.9 |
| `random` | ATTACK=803, AWAIT=3015, COLLECT=2973, INVEST=3020, MOVE=2944, RECRUIT=5871, SECURE=2948, STUDY=2948, TAX=2903, WORK=2984 | 8.0 | 15 | +0/−0 | 84.2 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 49 | 1.0 | 0.438 | 5850 | 450 | 2515 | 4255 | 4447 |
| `random` | 31 | 0.812 | 0.438 | 5871 | 803 | 2944 | 2948 | 2903 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 23.0 | 30.0 |
| `random` | 29.0 | 30.0 |

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
