# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** world.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 40 | 50.0% | 20878 | 332 |
| `random` | 40 | 50.0% | 16650 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 8, `random` 8
- **Splits:** 24 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 54 |
| secured | 25 |
| gold | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR001` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR002` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR003` | random | scripted:balanced | split |
| `AR004` | random | scripted:balanced | split |
| `AR005` | scripted:balanced | random | split |
| `AR006` | scripted:balanced | random | split |
| `AR007` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR008` | random | scripted:balanced | split |
| `AR009` | scripted:balanced | random | split |
| `AR010` | scripted:balanced | random | split |
| `AR011` | scripted:balanced | random | split |
| `AR012` | random | random | swept by random |
| `AR013` | random | random | swept by random |
| `AR014` | random | scripted:balanced | split |
| `AR015` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR016` | random | scripted:balanced | split |
| `AR017` | scripted:balanced | random | split |
| `AR018` | random | random | swept by random |
| `AR019` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR020` | random | scripted:balanced | split |
| `AR021` | random | scripted:balanced | split |
| `AR022` | random | random | swept by random |
| `AR023` | random | scripted:balanced | split |
| `AR024` | scripted:balanced | random | split |
| `AR025` | random | scripted:balanced | split |
| `AR026` | scripted:balanced | random | split |
| `AR027` | random | random | swept by random |
| `AR028` | random | scripted:balanced | split |
| `AR029` | random | scripted:balanced | split |
| `AR030` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR031` | random | scripted:balanced | split |
| `AR032` | random | random | swept by random |
| `AR033` | scripted:balanced | random | split |
| `AR034` | scripted:balanced | random | split |
| `AR035` | random | random | swept by random |
| `AR036` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR037` | scripted:balanced | random | split |
| `AR038` | random | random | swept by random |
| `AR039` | random | scripted:balanced | split |

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
| `scripted:balanced` | ABSORB=19, ADDRESS=80, ALLY=109, ATTACK=1, BORROW=2, BUILD=80, BUY_SHIP=13, CHARGE=25, COLLECT=282, CONJURE=538, CREATE=125, ENEMY=166, FLY=58, FORTIFY=94, IF=560, INVEST=357, LURK=284, MINE=81, MOVE=2099, NAME=608, NEUTRAL=125, PASSAGE=25, PASSWORD=80, PAY=223, POST=442, PROMOTE=232, RECRUIT=4621, REPAY=270, REPORT=341, SAIL=7, SAY=567, SCAN=48, SCRY=563, SEARCH=182, SECURE=2361, STUDY=1417, SUMMON=324, TAX=2400, TELEPORT=11, TRADE=309, TRAIN=256, UNFORTIFY=2, WORK=491 | 17.0 | 0 | +0/−0 | 49.9 |
| `random` | ATTACK=15, AWAIT=1717, COLLECT=1639, INVEST=1659, MOVE=1674, RECRUIT=3317, SECURE=1644, STUDY=1631, TAX=1682, WORK=1672 | 17.0 | 0 | +0/−0 | 27.1 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 40 | 1.0 | 0.013 | 4621 | 1 | 2099 | 2361 | 2400 |
| `random` | 40 | 1.0 | 0.013 | 3317 | 15 | 1674 | 1644 | 1682 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 15.0 | 18.0 |
| `random` | 16.0 | 4.0 |

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
