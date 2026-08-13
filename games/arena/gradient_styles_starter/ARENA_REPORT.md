# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** starter_map.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 40 | 50.0% | 20565 | 301 |
| `scripted:religious` | 40 | 50.0% | 21142 | 327 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 4, `scripted:religious` 4
- **Splits:** 32 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 52 |
| secured | 15 |
| elimination | 13 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:military | scripted:religious | split |
| `AR001` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR002` | scripted:religious | scripted:military | split |
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
| `AR020` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR021` | scripted:military | scripted:religious | split |
| `AR022` | scripted:religious | scripted:military | split |
| `AR023` | scripted:religious | scripted:military | split |
| `AR024` | scripted:religious | scripted:military | split |
| `AR025` | scripted:religious | scripted:military | split |
| `AR026` | scripted:religious | scripted:military | split |
| `AR027` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR028` | scripted:military | scripted:religious | split |
| `AR029` | scripted:military | scripted:religious | split |
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
| `scripted:military` | 2400 | 2400 | — | 97.1% | 0 | 0 |
| `scripted:religious` | 2400 | 2400 | — | 91.1% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:military` | — | — | — | unknown |
| `scripted:religious` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:military` | ABSORB=12, ADDRESS=80, ALLY=80, ATTACK=230, BORROW=20, BUILD=77, BUY_SHIP=61, CAPTURE=148, CHARGE=11, COLLECT=274, CONJURE=534, CREATE=220, ENEMY=235, ENSLAVE=10, FLY=280, FORTIFY=261, FREE=16, IF=563, INTERROGATE=35, INVEST=949, KILL=22, LURK=232, MINE=77, MOVE=1187, NAME=834, NEUTRAL=80, PASSAGE=29, PASSWORD=80, PAY=223, POST=416, PROBE=79, PROMOTE=301, RECRUIT=3608, REPAY=221, REPORT=349, SAIL=33, SAY=513, SCAN=56, SCRY=570, SEARCH=276, SECURE=2189, STUDY=1322, SUMMON=322, TAX=2227, TELEPORT=41, TRADE=271, TRAIN=395, UNFORTIFY=5, WORK=511 | 6.0 | 4 | +0/−0 | 234.2 |
| `scripted:religious` | ABSORB=4, ADDRESS=80, ALLY=109, ATTACK=115, BLESS=1220, BORROW=2, BUILD=62, BUY_SHIP=67, CAPTURE=80, CHARGE=4, COLLECT=326, CONJURE=513, CREATE=241, CURSE=33, ENEMY=146, ENSLAVE=5, FLY=182, FORTIFY=274, FREE=7, HEAL=14, IF=538, INTERROGATE=13, INVEST=1084, KILL=2, LURK=247, MINE=70, MOVE=896, NAME=827, NEUTRAL=114, OFFER=117, PASSAGE=37, PASSWORD=71, PAY=208, POST=309, PRAY=389, PREACH=1429, PROBE=55, PROMOTE=327, RECRUIT=2584, REPAY=200, REPORT=340, SAIL=22, SAY=501, SCAN=48, SCRY=523, SEARCH=60, SECURE=1850, STUDY=1423, SUMMON=193, TAX=2019, TELEPORT=40, TRADE=268, TRAIN=390, UNFORTIFY=5, WORK=459 | 6.0 | 12 | +0/−0 | 144.9 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 40 | 0.95 | 0.4 | 3608 | 230 | 1187 | 2189 | 2227 |
| `scripted:religious` | 40 | 0.85 | 0.4 | 2584 | 115 | 896 | 1850 | 2019 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 13.0 | 11.0 |
| `scripted:religious` | 11.0 | 16.0 |

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
