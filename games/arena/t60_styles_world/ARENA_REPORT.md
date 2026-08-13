# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** world.json
- **Games:** 80 (60 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 16 | 20.0% | 35324 | 438 |
| `scripted:religious` | 64 | 80.0% | 44142 | 712 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 0, `scripted:religious` 24
- **Splits:** 16 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 64 |
| secured | 13 |
| gold | 3 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR001` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR002` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR003` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR004` | scripted:religious | scripted:military | split |
| `AR005` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR006` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR007` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR008` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR009` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR010` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR011` | scripted:religious | scripted:military | split |
| `AR012` | scripted:military | scripted:religious | split |
| `AR013` | scripted:religious | scripted:military | split |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:religious | scripted:military | split |
| `AR016` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR017` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR018` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR019` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR020` | scripted:religious | scripted:military | split |
| `AR021` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR022` | scripted:military | scripted:religious | split |
| `AR023` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR024` | scripted:military | scripted:religious | split |
| `AR025` | scripted:military | scripted:religious | split |
| `AR026` | scripted:military | scripted:religious | split |
| `AR027` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR028` | scripted:religious | scripted:military | split |
| `AR029` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR030` | scripted:military | scripted:religious | split |
| `AR031` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR032` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR033` | scripted:religious | scripted:military | split |
| `AR034` | scripted:military | scripted:religious | split |
| `AR035` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR036` | scripted:religious | scripted:military | split |
| `AR037` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR038` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR039` | scripted:religious | scripted:religious | swept by scripted:religious |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:military` | 4800 | 4800 | — | 100.0% | 0 | 0 |
| `scripted:religious` | 4800 | 4800 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:military` | — | — | — | unknown |
| `scripted:religious` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:military` | ABSORB=49, ADDRESS=80, ALLY=80, ATTACK=3, BORROW=119, BUILD=131, BUY_SHIP=13, CHARGE=66, COLLECT=500, CONJURE=584, CREATE=184, ENEMY=480, FLY=107, FORTIFY=108, IF=685, INVEST=376, LURK=574, MINE=136, MOVE=4173, NAME=641, NEUTRAL=80, PASSAGE=28, PASSWORD=80, PAY=392, POST=851, PROBE=1, PROMOTE=244, RECRUIT=7692, REPAY=397, REPORT=706, SAIL=22, SAY=1073, SCAN=110, SCRY=625, SEARCH=310, SECURE=4591, STUDY=1800, SUMMON=840, TAX=4800, TELEPORT=48, TRADE=451, TRAIN=294, UNFORTIFY=6, WORK=794 | 29.0 | 0 | +0/−0 | 53.3 |
| `scripted:religious` | ABSORB=47, ADDRESS=80, ALLY=166, ATTACK=3, BLESS=3169, BORROW=131, BUILD=116, BUY_SHIP=56, CAPTURE=3, CHARGE=73, COLLECT=498, CONJURE=579, CREATE=419, ENEMY=288, FLY=79, FORTIFY=219, IF=675, INVEST=768, LURK=624, MINE=109, MOVE=3957, NAME=1242, NEUTRAL=186, OFFER=8, PASSAGE=38, PASSWORD=80, PAY=417, POST=841, PRAY=444, PREACH=4061, PROMOTE=474, RECRUIT=6155, REPAY=388, REPORT=722, SAIL=30, SAY=1062, SCAN=128, SCRY=621, SEARCH=418, SECURE=4700, STUDY=2598, SUMMON=637, TAX=4800, TELEPORT=53, TRADE=384, TRAIN=773, UNFORTIFY=5, WORK=818 | 29.0 | 0 | +0/−0 | 101.9 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 16 | 1.0 | 0.013 | 7692 | 3 | 4173 | 4591 | 4800 |
| `scripted:religious` | 64 | 1.0 | 0.013 | 6155 | 3 | 3957 | 4700 | 4800 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 25.0 | 32.0 |
| `scripted:religious` | 23.0 | 32.0 |

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
