# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** calib_12_s2.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 39 | 48.7% | 19817 | 580 |
| `scripted:religious` | 41 | 51.2% | 23751 | 602 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 9, `scripted:religious` 10
- **Splits:** 21 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 65 |
| secured | 14 |
| gold | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR001` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR002` | scripted:military | scripted:religious | split |
| `AR003` | scripted:religious | scripted:military | split |
| `AR004` | scripted:religious | scripted:military | split |
| `AR005` | scripted:religious | scripted:military | split |
| `AR006` | scripted:military | scripted:military | swept by scripted:military |
| `AR007` | scripted:religious | scripted:military | split |
| `AR008` | scripted:military | scripted:military | swept by scripted:military |
| `AR009` | scripted:military | scripted:military | swept by scripted:military |
| `AR010` | scripted:religious | scripted:military | split |
| `AR011` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR012` | scripted:military | scripted:religious | split |
| `AR013` | scripted:military | scripted:military | swept by scripted:military |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:military | scripted:military | swept by scripted:military |
| `AR016` | scripted:military | scripted:religious | split |
| `AR017` | scripted:military | scripted:religious | split |
| `AR018` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR019` | scripted:religious | scripted:military | split |
| `AR020` | scripted:military | scripted:military | swept by scripted:military |
| `AR021` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR022` | scripted:military | scripted:military | swept by scripted:military |
| `AR023` | scripted:military | scripted:military | swept by scripted:military |
| `AR024` | scripted:religious | scripted:military | split |
| `AR025` | scripted:religious | scripted:military | split |
| `AR026` | scripted:military | scripted:religious | split |
| `AR027` | scripted:religious | scripted:military | split |
| `AR028` | scripted:religious | scripted:military | split |
| `AR029` | scripted:military | scripted:religious | split |
| `AR030` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR031` | scripted:military | scripted:religious | split |
| `AR032` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR033` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR034` | scripted:military | scripted:religious | split |
| `AR035` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR036` | scripted:religious | scripted:military | split |
| `AR037` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR038` | scripted:military | scripted:religious | split |
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
| `scripted:military` | ABSORB=1, ADDRESS=80, ALLY=80, ATTACK=20, BORROW=59, BUILD=63, BUY_SHIP=1, CAPTURE=6, CHARGE=5, COLLECT=372, CONJURE=547, CREATE=178, ENEMY=240, FLY=532, FORTIFY=188, IF=564, INVEST=678, LURK=280, MINE=77, MOVE=800, NAME=876, NEUTRAL=80, PASSAGE=39, PASSWORD=80, PAY=210, POST=389, PROBE=10, PROMOTE=322, RECRUIT=3880, REPAY=190, REPORT=378, SAY=546, SCAN=42, SCRY=559, SECURE=2251, STUDY=1235, SUMMON=318, TAX=2400, TELEPORT=17, TRADE=234, TRAIN=400, UNFORTIFY=4, WORK=586 | 19.0 | 0 | +0/−0 | 92.6 |
| `scripted:religious` | ADDRESS=80, ALLY=116, ATTACK=14, BLESS=1313, BORROW=26, BUILD=74, CAPTURE=2, COLLECT=332, CONJURE=533, CREATE=192, CURSE=4, ENEMY=163, FLY=350, FORTIFY=311, HEAL=12, IF=568, INVEST=1053, LURK=307, MINE=73, MOVE=721, NAME=994, NEUTRAL=121, OFFER=91, PASSAGE=49, PASSWORD=80, PAY=222, POST=407, PRAY=434, PREACH=1654, PROBE=6, PROMOTE=374, RECRUIT=3649, REPAY=200, REPORT=344, SAY=581, SCAN=42, SCRY=575, SECURE=2310, STUDY=1488, SUMMON=184, TAX=2389, TELEPORT=12, TRADE=255, TRAIN=483, UNFORTIFY=5, WORK=558 | 19.0 | 0 | +0/−0 | 90.6 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 39 | 1.0 | 0.037 | 3880 | 20 | 800 | 2251 | 2400 |
| `scripted:religious` | 41 | 1.0 | 0.037 | 3649 | 14 | 721 | 2310 | 2389 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 13.0 | 13.5 |
| `scripted:religious` | 12.0 | 10.5 |

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
