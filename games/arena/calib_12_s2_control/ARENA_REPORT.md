# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** calib_12_s2.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 49 | 61.3% | 19823 | 577 |
| `random` | 31 | 38.8% | 16650 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 14, `random` 5
- **Splits:** 21 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 63 |
| secured | 17 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | random | scripted:balanced | split |
| `AR001` | random | random | swept by random |
| `AR002` | scripted:balanced | random | split |
| `AR003` | random | scripted:balanced | split |
| `AR004` | scripted:balanced | random | split |
| `AR005` | random | scripted:balanced | split |
| `AR006` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR007` | random | random | swept by random |
| `AR008` | scripted:balanced | random | split |
| `AR009` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR010` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR011` | random | random | swept by random |
| `AR012` | scripted:balanced | random | split |
| `AR013` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR014` | scripted:balanced | random | split |
| `AR015` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR016` | scripted:balanced | random | split |
| `AR017` | scripted:balanced | random | split |
| `AR018` | scripted:balanced | random | split |
| `AR019` | random | scripted:balanced | split |
| `AR020` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR021` | random | random | swept by random |
| `AR022` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR023` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR024` | random | scripted:balanced | split |
| `AR025` | random | scripted:balanced | split |
| `AR026` | scripted:balanced | random | split |
| `AR027` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR028` | random | scripted:balanced | split |
| `AR029` | scripted:balanced | random | split |
| `AR030` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR031` | scripted:balanced | random | split |
| `AR032` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR033` | random | random | swept by random |
| `AR034` | scripted:balanced | random | split |
| `AR035` | random | scripted:balanced | split |
| `AR036` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR037` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR038` | scripted:balanced | random | split |
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
| `scripted:balanced` | ABSORB=2, ADDRESS=80, ALLY=120, ATTACK=1, BORROW=58, BUILD=64, BUY_SHIP=1, CHARGE=4, COLLECT=366, CONJURE=544, CREATE=169, ENEMY=159, FLY=520, FORTIFY=187, IF=561, INVEST=678, LURK=278, MINE=80, MOVE=827, NAME=868, NEUTRAL=121, PASSAGE=37, PASSWORD=80, PAY=213, POST=388, PROBE=1, PROMOTE=322, RECRUIT=3879, REPAY=189, REPORT=384, SAY=564, SCAN=41, SCRY=566, SECURE=2263, STUDY=1245, SUMMON=318, TAX=2400, TELEPORT=12, TRADE=239, TRAIN=398, UNFORTIFY=4, WORK=592 | 25.5 | 0 | +0/−0 | 91.4 |
| `random` | ATTACK=113, AWAIT=1719, COLLECT=1625, INVEST=1655, MOVE=1668, RECRUIT=3299, SECURE=1642, STUDY=1619, TAX=1668, WORK=1642 | 25.5 | 0 | +0/−0 | 33.9 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 49 | 1.0 | 0.025 | 3879 | 1 | 827 | 2263 | 2400 |
| `random` | 31 | 1.0 | 0.025 | 3299 | 113 | 1668 | 1642 | 1668 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 13.0 | 30.0 |
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
