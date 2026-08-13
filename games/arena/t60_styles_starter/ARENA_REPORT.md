# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** starter_map.json
- **Games:** 80 (60 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 42 | 52.5% | 33535 | 412 |
| `scripted:religious` | 38 | 47.5% | 38090 | 525 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 5, `scripted:religious` 3
- **Splits:** 32 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 40 |
| secured | 24 |
| elimination | 16 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:military | scripted:religious | split |
| `AR001` | scripted:military | scripted:religious | split |
| `AR002` | scripted:military | scripted:military | swept by scripted:military |
| `AR003` | scripted:military | scripted:religious | split |
| `AR004` | scripted:religious | scripted:military | split |
| `AR005` | scripted:religious | scripted:military | split |
| `AR006` | scripted:military | scripted:religious | split |
| `AR007` | scripted:religious | scripted:military | split |
| `AR008` | scripted:military | scripted:military | swept by scripted:military |
| `AR009` | scripted:military | scripted:religious | split |
| `AR010` | scripted:religious | scripted:military | split |
| `AR011` | scripted:military | scripted:religious | split |
| `AR012` | scripted:military | scripted:religious | split |
| `AR013` | scripted:religious | scripted:military | split |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:religious | scripted:military | split |
| `AR016` | scripted:military | scripted:religious | split |
| `AR017` | scripted:military | scripted:military | swept by scripted:military |
| `AR018` | scripted:military | scripted:military | swept by scripted:military |
| `AR019` | scripted:military | scripted:military | swept by scripted:military |
| `AR020` | scripted:religious | scripted:military | split |
| `AR021` | scripted:military | scripted:religious | split |
| `AR022` | scripted:religious | scripted:military | split |
| `AR023` | scripted:religious | scripted:military | split |
| `AR024` | scripted:religious | scripted:military | split |
| `AR025` | scripted:religious | scripted:military | split |
| `AR026` | scripted:religious | scripted:military | split |
| `AR027` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR028` | scripted:military | scripted:religious | split |
| `AR029` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR030` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR031` | scripted:military | scripted:religious | split |
| `AR032` | scripted:religious | scripted:military | split |
| `AR033` | scripted:religious | scripted:military | split |
| `AR034` | scripted:religious | scripted:military | split |
| `AR035` | scripted:military | scripted:religious | split |
| `AR036` | scripted:religious | scripted:military | split |
| `AR037` | scripted:military | scripted:religious | split |
| `AR038` | scripted:military | scripted:religious | split |
| `AR039` | scripted:religious | scripted:military | split |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:military` | 4800 | 4800 | — | 95.8% | 0 | 0 |
| `scripted:religious` | 4800 | 4800 | — | 89.2% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:military` | — | — | — | unknown |
| `scripted:religious` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:military` | ABSORB=35, ADDRESS=80, ALLY=80, ATTACK=365, BORROW=176, BUILD=137, BUY_SHIP=86, CAPTURE=196, CHARGE=43, COLLECT=444, CONJURE=573, CREATE=423, ENEMY=462, ENSLAVE=15, FLY=567, FORTIFY=324, FREE=19, IF=675, INTERROGATE=42, INVEST=1105, KILL=24, LURK=490, MINE=131, MOVE=2311, NAME=1076, NEUTRAL=80, PASSAGE=33, PASSWORD=80, PAY=368, POST=775, PROBE=117, PROMOTE=412, RECRUIT=5546, REPAY=344, REPORT=674, SAIL=128, SAY=881, SCAN=138, SCRY=629, SEARCH=662, SECURE=4098, STUDY=1713, SUMMON=752, TAX=4275, TELEPORT=94, TRADE=397, TRAIN=644, UNFORTIFY=11, WORK=805 | 7.0 | 5 | +0/−0 | 302.2 |
| `scripted:religious` | ABSORB=23, ADDRESS=80, ALLY=151, ATTACK=247, BLESS=2852, BORROW=74, BUILD=103, BUY_SHIP=91, CAPTURE=159, CHARGE=19, COLLECT=518, CONJURE=550, CREATE=500, CURSE=68, ENEMY=256, ENSLAVE=9, FLY=416, FORTIFY=451, FREE=11, HEAL=22, IF=628, INTERROGATE=17, INVEST=1641, KILL=7, LURK=472, MINE=111, MOVE=1874, NAME=1320, NEUTRAL=172, OFFER=196, PASSAGE=41, PASSWORD=71, PAY=353, POST=652, PRAY=389, PREACH=3383, PROBE=104, PROMOTE=525, RECRUIT=3958, REPAY=362, REPORT=655, SAIL=99, SAY=894, SCAN=126, SCRY=573, SEARCH=206, SECURE=3775, STUDY=2409, SUMMON=552, TAX=3990, TELEPORT=81, TRADE=412, TRAIN=799, UNFORTIFY=17, WORK=626 | 7.0 | 15 | +0/−0 | 159.3 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 42 | 0.938 | 0.45 | 5546 | 365 | 2311 | 4098 | 4275 |
| `scripted:religious` | 38 | 0.812 | 0.45 | 3958 | 247 | 1874 | 3775 | 3990 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 21.0 | 18.0 |
| `scripted:religious` | 20.0 | 34.0 |

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
