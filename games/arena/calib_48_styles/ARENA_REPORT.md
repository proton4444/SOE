# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** calib_48.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 43 | 53.7% | 20424 | 576 |
| `scripted:religious` | 37 | 46.3% | 24105 | 612 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 7, `scripted:religious` 4
- **Splits:** 29 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 74 |
| secured | 5 |
| elimination | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:military | scripted:military | swept by scripted:military |
| `AR001` | scripted:military | scripted:religious | split |
| `AR002` | scripted:religious | scripted:military | split |
| `AR003` | scripted:religious | scripted:military | split |
| `AR004` | scripted:religious | scripted:military | split |
| `AR005` | scripted:military | scripted:religious | split |
| `AR006` | scripted:religious | scripted:military | split |
| `AR007` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR008` | scripted:military | scripted:military | swept by scripted:military |
| `AR009` | scripted:military | scripted:military | swept by scripted:military |
| `AR010` | scripted:religious | scripted:military | split |
| `AR011` | scripted:military | scripted:religious | split |
| `AR012` | scripted:religious | scripted:military | split |
| `AR013` | scripted:religious | scripted:military | split |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:military | scripted:religious | split |
| `AR016` | scripted:religious | scripted:military | split |
| `AR017` | scripted:religious | scripted:military | split |
| `AR018` | scripted:military | scripted:religious | split |
| `AR019` | scripted:religious | scripted:military | split |
| `AR020` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR021` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR022` | scripted:religious | scripted:military | split |
| `AR023` | scripted:military | scripted:military | swept by scripted:military |
| `AR024` | scripted:military | scripted:religious | split |
| `AR025` | scripted:military | scripted:religious | split |
| `AR026` | scripted:religious | scripted:military | split |
| `AR027` | scripted:military | scripted:religious | split |
| `AR028` | scripted:military | scripted:religious | split |
| `AR029` | scripted:military | scripted:religious | split |
| `AR030` | scripted:religious | scripted:military | split |
| `AR031` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR032` | scripted:military | scripted:religious | split |
| `AR033` | scripted:military | scripted:religious | split |
| `AR034` | scripted:military | scripted:military | swept by scripted:military |
| `AR035` | scripted:military | scripted:religious | split |
| `AR036` | scripted:military | scripted:religious | split |
| `AR037` | scripted:religious | scripted:military | split |
| `AR038` | scripted:military | scripted:military | swept by scripted:military |
| `AR039` | scripted:military | scripted:military | swept by scripted:military |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `scripted:military` | 2400 | 2400 | — | 100.0% | 0 | 0 |
| `scripted:religious` | 2400 | 2400 | — | 99.5% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `scripted:military` | — | — | — | unknown |
| `scripted:religious` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `scripted:military` | ABSORB=22, ADDRESS=80, ALLY=80, ATTACK=24, BORROW=50, BUILD=61, CAPTURE=7, CHARGE=47, COLLECT=318, CONJURE=536, CREATE=141, ENEMY=240, FLY=420, FORTIFY=217, IF=563, INVEST=724, LURK=262, MINE=82, MOVE=951, NAME=897, NEUTRAL=80, PASSAGE=51, PASSWORD=80, PAY=250, POST=438, PROBE=4, PROMOTE=325, RECRUIT=3982, REPAY=207, REPORT=350, SAY=554, SCAN=39, SCRY=558, SEARCH=160, SECURE=2323, STUDY=1294, SUMMON=343, TAX=2400, TELEPORT=15, TRADE=266, TRAIN=408, UNFORTIFY=4, WORK=571 | 9.0 | 0 | +0/−0 | 92.1 |
| `scripted:religious` | ABSORB=25, ADDRESS=80, ALLY=122, ATTACK=15, BLESS=1268, BORROW=22, BUILD=59, CHARGE=21, COLLECT=314, CONJURE=542, CREATE=174, CURSE=2, ENEMY=158, FLY=336, FORTIFY=346, IF=564, INVEST=1116, LURK=288, MINE=58, MOVE=884, NAME=956, NEUTRAL=119, OFFER=27, PASSAGE=54, PASSWORD=80, PAY=214, POST=429, PRAY=443, PREACH=1602, PROBE=7, PROMOTE=371, RECRUIT=3781, REPAY=195, REPORT=349, SAY=572, SCAN=44, SCRY=553, SEARCH=188, SECURE=2364, STUDY=1521, SUMMON=208, TAX=2388, TELEPORT=9, TRADE=260, TRAIN=445, UNFORTIFY=10, WORK=522 | 9.0 | 1 | +0/−0 | 85.2 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 43 | 1.0 | 0.037 | 3982 | 24 | 951 | 2323 | 2400 |
| `scripted:religious` | 37 | 0.988 | 0.037 | 3781 | 15 | 884 | 2364 | 2388 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 13.0 | 13.5 |
| `scripted:religious` | 13.0 | 11.0 |

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
