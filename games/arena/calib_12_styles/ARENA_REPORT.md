# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** calib_12.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 51 | 63.7% | 20128 | 690 |
| `scripted:religious` | 29 | 36.2% | 23953 | 673 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 15, `scripted:religious` 4
- **Splits:** 21 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 64 |
| secured | 10 |
| gold | 4 |
| elimination | 2 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:military | scripted:religious | split |
| `AR001` | scripted:military | scripted:military | swept by scripted:military |
| `AR002` | scripted:religious | scripted:military | split |
| `AR003` | scripted:military | scripted:military | swept by scripted:military |
| `AR004` | scripted:religious | scripted:military | split |
| `AR005` | scripted:religious | scripted:military | split |
| `AR006` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR007` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR008` | scripted:military | scripted:military | swept by scripted:military |
| `AR009` | scripted:military | scripted:military | swept by scripted:military |
| `AR010` | scripted:religious | scripted:military | split |
| `AR011` | scripted:military | scripted:religious | split |
| `AR012` | scripted:military | scripted:religious | split |
| `AR013` | scripted:military | scripted:military | swept by scripted:military |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:military | scripted:military | swept by scripted:military |
| `AR016` | scripted:religious | scripted:military | split |
| `AR017` | scripted:religious | scripted:military | split |
| `AR018` | scripted:religious | scripted:military | split |
| `AR019` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR020` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR021` | scripted:military | scripted:military | swept by scripted:military |
| `AR022` | scripted:military | scripted:religious | split |
| `AR023` | scripted:military | scripted:religious | split |
| `AR024` | scripted:military | scripted:military | swept by scripted:military |
| `AR025` | scripted:religious | scripted:military | split |
| `AR026` | scripted:military | scripted:military | swept by scripted:military |
| `AR027` | scripted:military | scripted:military | swept by scripted:military |
| `AR028` | scripted:military | scripted:military | swept by scripted:military |
| `AR029` | scripted:military | scripted:military | swept by scripted:military |
| `AR030` | scripted:religious | scripted:military | split |
| `AR031` | scripted:military | scripted:religious | split |
| `AR032` | scripted:military | scripted:religious | split |
| `AR033` | scripted:military | scripted:military | swept by scripted:military |
| `AR034` | scripted:military | scripted:military | swept by scripted:military |
| `AR035` | scripted:religious | scripted:military | split |
| `AR036` | scripted:military | scripted:military | swept by scripted:military |
| `AR037` | scripted:military | scripted:religious | split |
| `AR038` | scripted:military | scripted:religious | split |
| `AR039` | scripted:military | scripted:religious | split |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:military` | 2400 | 2400 | — | 99.4% | 0 | 0 |
| `scripted:religious` | 2400 | 2400 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:military` | — | — | — | unknown |
| `scripted:religious` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:military` | ABSORB=55, ADDRESS=80, ALLY=80, ATTACK=32, BORROW=63, BUILD=67, CAPTURE=9, CHARGE=63, COLLECT=286, CONJURE=546, CREATE=219, ENEMY=240, FLY=763, FORTIFY=266, IF=562, INVEST=918, LURK=265, MINE=78, MOVE=181, NAME=1029, NEUTRAL=80, PASSAGE=14, PASSWORD=80, PAY=188, POST=371, PROBE=16, PROMOTE=381, RECRUIT=3594, REPAY=170, REPORT=386, SAY=594, SCAN=51, SCRY=563, SEARCH=356, SECURE=2192, STUDY=1188, SUMMON=327, TAX=2369, TELEPORT=23, TRADE=232, TRAIN=517, UNFORTIFY=11, WORK=623 | 9.0 | 2 | +0/−0 | 120.0 |
| `scripted:religious` | ABSORB=33, ADDRESS=80, ALLY=119, ATTACK=63, BLESS=1311, BORROW=35, BUILD=74, CAPTURE=43, CHARGE=58, COLLECT=316, CONJURE=541, CREATE=229, CURSE=17, ENEMY=148, ENSLAVE=6, FLY=500, FORTIFY=396, FREE=1, IF=560, INTERROGATE=3, INVEST=1289, KILL=5, LURK=288, MINE=68, MOVE=262, NAME=1071, NEUTRAL=133, OFFER=64, PASSAGE=21, PASSWORD=80, PAY=230, POST=416, PRAY=439, PREACH=1601, PROBE=23, PROMOTE=417, RECRUIT=3387, REPAY=162, REPORT=348, SAY=560, SCAN=49, SCRY=559, SEARCH=202, SECURE=2320, STUDY=1489, SUMMON=185, TAX=2371, TELEPORT=24, TRADE=244, TRAIN=547, UNFORTIFY=6, WORK=560 | 9.0 | 0 | +0/−0 | 107.4 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 51 | 0.975 | 0.062 | 3594 | 32 | 181 | 2192 | 2369 |
| `scripted:religious` | 29 | 1.0 | 0.062 | 3387 | 63 | 262 | 2320 | 2371 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 12.0 | 19.0 |
| `scripted:religious` | 11.0 | 17.0 |

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
