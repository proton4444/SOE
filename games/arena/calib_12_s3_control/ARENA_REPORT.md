# Arena — head-to-head

- **Policies:** `scripted:balanced` vs `random`
- **Map:** calib_12_s3.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:balanced` | 76 | 95.0% | 19540 | 755 |
| `random` | 4 | 5.0% | 16650 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:balanced` 36, `random` 0
- **Splits:** 4 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 76 |
| secured | 4 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR001` | random | scripted:balanced | split |
| `AR002` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR003` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR004` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR005` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR006` | random | scripted:balanced | split |
| `AR007` | scripted:balanced | random | split |
| `AR008` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR009` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR010` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
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
| `AR022` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR023` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR024` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR025` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR026` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR027` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
| `AR028` | scripted:balanced | scripted:balanced | swept by scripted:balanced |
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
| `random` | 2400 | 2400 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:balanced` | — | — | — | unknown |
| `random` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:balanced` | ABSORB=2, ADDRESS=80, ALLY=113, BORROW=90, BUILD=68, CHARGE=9, COLLECT=370, CONJURE=545, CREATE=233, ENEMY=166, FLY=844, FORTIFY=282, IF=559, INVEST=939, LURK=271, MINE=79, NAME=1049, NEUTRAL=121, PASSAGE=33, PASSWORD=80, PAY=200, POST=386, PROMOTE=389, RECRUIT=3251, REPAY=168, REPORT=380, SAY=601, SCAN=46, SCRY=563, SECURE=2308, STUDY=1166, SUMMON=318, TAX=2400, TRADE=215, TRAIN=541, UNFORTIFY=14, WORK=661 | — | 0 | +0/−0 | 147.3 |
| `random` | ATTACK=110, AWAIT=1725, COLLECT=1633, INVEST=1667, MOVE=1659, RECRUIT=3306, SECURE=1625, STUDY=1622, TAX=1660, WORK=1643 | — | 0 | +0/−0 | 43.6 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:balanced` | 76 | 1.0 | 0.0 | 3251 | 0 | 0 | 2308 | 2400 |
| `random` | 4 | 1.0 | 0.0 | 3306 | 110 | 1659 | 1625 | 1660 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:balanced` | 11.0 | — |
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
