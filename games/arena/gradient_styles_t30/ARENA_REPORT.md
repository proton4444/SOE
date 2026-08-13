# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** world.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 23 | 28.7% | 20884 | 327 |
| `scripted:religious` | 57 | 71.3% | 24175 | 420 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 2, `scripted:religious` 19
- **Splits:** 19 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 62 |
| secured | 10 |
| gold | 8 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:religious | scripted:military | split |
| `AR001` | scripted:military | scripted:religious | split |
| `AR002` | scripted:military | scripted:military | swept by scripted:military |
| `AR003` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR004` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR005` | scripted:religious | scripted:military | split |
| `AR006` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR007` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR008` | scripted:religious | scripted:military | split |
| `AR009` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR010` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR011` | scripted:military | scripted:military | swept by scripted:military |
| `AR012` | scripted:religious | scripted:military | split |
| `AR013` | scripted:religious | scripted:military | split |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:religious | scripted:military | split |
| `AR016` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR017` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR018` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR019` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR020` | scripted:religious | scripted:military | split |
| `AR021` | scripted:military | scripted:religious | split |
| `AR022` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR023` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR024` | scripted:military | scripted:religious | split |
| `AR025` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR026` | scripted:military | scripted:religious | split |
| `AR027` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR028` | scripted:religious | scripted:military | split |
| `AR029` | scripted:military | scripted:religious | split |
| `AR030` | scripted:religious | scripted:military | split |
| `AR031` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR032` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR033` | scripted:religious | scripted:military | split |
| `AR034` | scripted:military | scripted:religious | split |
| `AR035` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR036` | scripted:religious | scripted:military | split |
| `AR037` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR038` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR039` | scripted:religious | scripted:military | split |

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
| `scripted:military` | ABSORB=8, ADDRESS=80, ALLY=80, ATTACK=1, BORROW=2, BUILD=82, BUY_SHIP=13, CHARGE=11, COLLECT=294, CONJURE=540, CREATE=126, ENEMY=240, FLY=54, FORTIFY=89, IF=558, INVEST=350, LURK=282, MINE=85, MOVE=2101, NAME=608, NEUTRAL=80, PASSAGE=26, PASSWORD=80, PAY=228, POST=437, PROMOTE=231, RECRUIT=4632, REPAY=256, REPORT=360, SAIL=9, SAY=575, SCAN=42, SCRY=562, SEARCH=178, SECURE=2358, STUDY=1424, SUMMON=340, TAX=2400, TELEPORT=13, TRADE=301, TRAIN=252, UNFORTIFY=3, WORK=493 | 29.0 | 0 | +0/−0 | 53.2 |
| `scripted:religious` | ABSORB=24, ADDRESS=80, ALLY=104, ATTACK=1, BLESS=1303, BORROW=3, BUILD=73, BUY_SHIP=43, CAPTURE=1, CHARGE=36, COLLECT=304, CONJURE=540, CREATE=210, ENEMY=173, FLY=42, FORTIFY=149, IF=558, INVEST=588, LURK=320, MINE=66, MOVE=1838, NAME=813, NEUTRAL=123, OFFER=4, PASSAGE=36, PASSWORD=80, PAY=242, POST=424, PRAY=444, PREACH=1663, PROMOTE=307, RECRUIT=3931, REPAY=243, REPORT=351, SAIL=7, SAY=582, SCAN=51, SCRY=564, SEARCH=136, SECURE=2336, STUDY=1605, SUMMON=202, TAX=2400, TELEPORT=29, TRADE=267, TRAIN=391, UNFORTIFY=2, WORK=486 | 29.0 | 0 | +0/−0 | 88.8 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 23 | 1.0 | 0.013 | 4632 | 1 | 2101 | 2358 | 2400 |
| `scripted:religious` | 57 | 1.0 | 0.013 | 3931 | 1 | 1838 | 2336 | 2400 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 15.0 | 30.0 |
| `scripted:religious` | 14.0 | 30.0 |

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
