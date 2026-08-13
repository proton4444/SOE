# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** calib_12_s3.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 57 | 71.3% | 19551 | 775 |
| `scripted:religious` | 23 | 28.7% | 23268 | 741 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 21, `scripted:religious` 4
- **Splits:** 15 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 71 |
| gold | 5 |
| secured | 4 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:military | scripted:religious | split |
| `AR001` | scripted:religious | scripted:military | split |
| `AR002` | scripted:military | scripted:military | swept by scripted:military |
| `AR003` | scripted:military | scripted:military | swept by scripted:military |
| `AR004` | scripted:military | scripted:religious | split |
| `AR005` | scripted:military | scripted:religious | split |
| `AR006` | scripted:military | scripted:military | swept by scripted:military |
| `AR007` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR008` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR009` | scripted:military | scripted:military | swept by scripted:military |
| `AR010` | scripted:religious | scripted:military | split |
| `AR011` | scripted:military | scripted:religious | split |
| `AR012` | scripted:religious | scripted:military | split |
| `AR013` | scripted:military | scripted:military | swept by scripted:military |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:military | scripted:military | swept by scripted:military |
| `AR016` | scripted:religious | scripted:military | split |
| `AR017` | scripted:military | scripted:military | swept by scripted:military |
| `AR018` | scripted:religious | scripted:military | split |
| `AR019` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR020` | scripted:military | scripted:military | swept by scripted:military |
| `AR021` | scripted:military | scripted:military | swept by scripted:military |
| `AR022` | scripted:military | scripted:military | swept by scripted:military |
| `AR023` | scripted:military | scripted:military | swept by scripted:military |
| `AR024` | scripted:military | scripted:military | swept by scripted:military |
| `AR025` | scripted:military | scripted:military | swept by scripted:military |
| `AR026` | scripted:religious | scripted:military | split |
| `AR027` | scripted:military | scripted:military | swept by scripted:military |
| `AR028` | scripted:military | scripted:military | swept by scripted:military |
| `AR029` | scripted:military | scripted:military | swept by scripted:military |
| `AR030` | scripted:religious | scripted:military | split |
| `AR031` | scripted:religious | scripted:military | split |
| `AR032` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR033` | scripted:military | scripted:military | swept by scripted:military |
| `AR034` | scripted:military | scripted:military | swept by scripted:military |
| `AR035` | scripted:religious | scripted:military | split |
| `AR036` | scripted:military | scripted:military | swept by scripted:military |
| `AR037` | scripted:military | scripted:religious | split |
| `AR038` | scripted:military | scripted:military | swept by scripted:military |
| `AR039` | scripted:military | scripted:military | swept by scripted:military |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:military` | 2400 | 2400 | — | 100.0% | 0 | 0 |
| `scripted:religious` | 2400 | 2400 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:military` | — | — | — | unknown |
| `scripted:religious` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:military` | ABSORB=2, ADDRESS=80, ALLY=80, BORROW=95, BUILD=66, CHARGE=9, COLLECT=370, CONJURE=544, CREATE=225, ENEMY=240, FLY=854, FORTIFY=281, IF=565, INVEST=936, LURK=280, MINE=73, NAME=1053, NEUTRAL=80, PASSAGE=33, PASSWORD=80, PAY=208, POST=396, PROMOTE=390, RECRUIT=3303, REPAY=155, REPORT=376, SAY=562, SCAN=51, SCRY=555, SECURE=2298, STUDY=1162, SUMMON=316, TAX=2400, TRADE=214, TRAIN=545, UNFORTIFY=14, WORK=660 | — | 0 | +0/−0 | 147.4 |
| `scripted:religious` | ADDRESS=80, ALLY=125, BLESS=1304, BORROW=54, BUILD=75, BUY_SHIP=2, COLLECT=350, CONJURE=536, CREATE=234, ENEMY=151, FLY=581, FORTIFY=452, IF=562, INVEST=1353, LURK=296, MINE=76, NAME=1096, NEUTRAL=124, OFFER=65, PASSAGE=33, PASSWORD=80, PAY=196, POST=421, PRAY=428, PREACH=1648, PROMOTE=429, RECRUIT=3023, REPAY=161, REPORT=344, SAY=561, SCAN=47, SCRY=560, SECURE=2384, STUDY=1444, SUMMON=205, TAX=2400, TRADE=236, TRAIN=557, UNFORTIFY=11, WORK=584 | — | 0 | +0/−0 | 125.1 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 57 | 1.0 | 0.0 | 3303 | 0 | 0 | 2298 | 2400 |
| `scripted:religious` | 23 | 1.0 | 0.0 | 3023 | 0 | 0 | 2384 | 2400 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 11.0 | — |
| `scripted:religious` | 10.0 | — |

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
