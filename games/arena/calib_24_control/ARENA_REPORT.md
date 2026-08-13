# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** calib_24.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 60 | 75.0% | 20369 | 673 |
| `random` | 20 | 25.0% | 16650 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 21, `random` 1
- **Splits:** 18 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 67 |
| secured | 12 |
| gold | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR001` | scripted:balanced | random | split |
| `AR002` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR003` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR004` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR005` | random | scripted:balanced | split |
| `AR006` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR007` | random | scripted:balanced | split |
| `AR008` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR009` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR010` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR011` | random | scripted:balanced | split |
| `AR012` | scripted:balanced | random | split |
| `AR013` | scripted:balanced | random | split |
| `AR014` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR015` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR016` | random | scripted:balanced | split |
| `AR017` | random | scripted:balanced | split |
| `AR018` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR019` | scripted:balanced | random | split |
| `AR020` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR021` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR022` | random | scripted:balanced | split |
| `AR023` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR024` | scripted:balanced | random | split |
| `AR025` | random | random | swept by random |
| `AR026` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR027` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR028` | scripted:balanced | random | split |
| `AR029` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR030` | random | scripted:balanced | split |
| `AR031` | random | scripted:balanced | split |
| `AR032` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR033` | random | scripted:balanced | split |
| `AR034` | random | scripted:balanced | split |
| `AR035` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR036` | random | scripted:balanced | split |
| `AR037` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR038` | random | scripted:balanced | split |
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
| `scripted:balanced` | ABSORB=19, ADDRESS=80, ALLY=109, ATTACK=19, BORROW=58, BUILD=65, CAPTURE=7, CHARGE=21, COLLECT=342, CONJURE=535, CREATE=204, ENEMY=166, FLY=623, FORTIFY=226, IF=555, INVEST=775, LURK=293, MINE=73, MOVE=565, NAME=1003, NEUTRAL=125, PASSAGE=51, PASSWORD=80, PAY=220, POST=408, PROBE=6, PROMOTE=377, RECRUIT=3776, REPAY=190, REPORT=361, SAY=577, SCAN=38, SCRY=566, SEARCH=278, SECURE=2276, STUDY=1270, SUMMON=288, TAX=2390, TELEPORT=31, TRADE=243, TRAIN=483, UNFORTIFY=5, WORK=592 | 13.5 | 0 | +0/−0 | 111.0 |
| `random` | ATTACK=67, AWAIT=1717, COLLECT=1620, INVEST=1659, MOVE=1675, RECRUIT=3313, SECURE=1644, STUDY=1626, TAX=1667, WORK=1662 | 13.5 | 0 | +0/−0 | 35.8 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 60 | 1.0 | 0.025 | 3776 | 19 | 565 | 2276 | 2390 |
| `random` | 20 | 1.0 | 0.025 | 3313 | 67 | 1675 | 1644 | 1667 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 12.0 | 19.0 |
| `random` | 16.0 | 19.0 |

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
