# Arena — head-to-head

- **Policies:** `scripted:military` vs `scripted:religious`
- **Map:** calib_24.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `scripted:military` | 39 | 48.7% | 20331 | 663 |
| `scripted:religious` | 41 | 51.2% | 23965 | 727 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `scripted:military` 9, `scripted:religious` 10
- **Splits:** 21 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 67 |
| secured | 10 |
| gold | 3 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | scripted:military | scripted:military | swept by scripted:military |
| `AR001` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR002` | scripted:military | scripted:military | swept by scripted:military |
| `AR003` | scripted:military | scripted:religious | split |
| `AR004` | scripted:military | scripted:military | swept by scripted:military |
| `AR005` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR006` | scripted:military | scripted:military | swept by scripted:military |
| `AR007` | scripted:religious | scripted:military | split |
| `AR008` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR009` | scripted:religious | scripted:military | split |
| `AR010` | scripted:religious | scripted:military | split |
| `AR011` | scripted:religious | scripted:military | split |
| `AR012` | scripted:military | scripted:religious | split |
| `AR013` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR014` | scripted:military | scripted:religious | split |
| `AR015` | scripted:religious | scripted:military | split |
| `AR016` | scripted:religious | scripted:military | split |
| `AR017` | scripted:religious | scripted:military | split |
| `AR018` | scripted:military | scripted:religious | split |
| `AR019` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR020` | scripted:military | scripted:military | swept by scripted:military |
| `AR021` | scripted:military | scripted:military | swept by scripted:military |
| `AR022` | scripted:religious | scripted:military | split |
| `AR023` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR024` | scripted:military | scripted:religious | split |
| `AR025` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR026` | scripted:military | scripted:military | swept by scripted:military |
| `AR027` | scripted:religious | scripted:military | split |
| `AR028` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR029` | scripted:military | scripted:military | swept by scripted:military |
| `AR030` | scripted:religious | scripted:military | split |
| `AR031` | scripted:religious | scripted:military | split |
| `AR032` | scripted:military | scripted:religious | split |
| `AR033` | scripted:religious | scripted:military | split |
| `AR034` | scripted:religious | scripted:military | split |
| `AR035` | scripted:military | scripted:military | swept by scripted:military |
| `AR036` | scripted:religious | scripted:military | split |
| `AR037` | scripted:military | scripted:religious | split |
| `AR038` | scripted:religious | scripted:religious | swept by scripted:religious |
| `AR039` | scripted:religious | scripted:religious | swept by scripted:religious |

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
| `scripted:military` | ABSORB=19, ADDRESS=80, ALLY=80, ATTACK=11, BORROW=58, BUILD=65, CHARGE=16, COLLECT=324, CONJURE=538, CREATE=206, ENEMY=240, FLY=615, FORTIFY=226, IF=556, INVEST=772, LURK=292, MINE=69, MOVE=574, NAME=984, NEUTRAL=80, PASSAGE=51, PASSWORD=80, PAY=228, POST=397, PROBE=4, PROMOTE=371, RECRUIT=3816, REPAY=178, REPORT=368, SAY=573, SCAN=43, SCRY=556, SEARCH=262, SECURE=2262, STUDY=1289, SUMMON=294, TAX=2400, TELEPORT=33, TRADE=245, TRAIN=476, UNFORTIFY=5, WORK=595 | 3.0 | 0 | +0/−0 | 111.4 |
| `scripted:religious` | ABSORB=30, ADDRESS=80, ALLY=121, ATTACK=11, BLESS=1290, BORROW=34, BUILD=85, BUY_SHIP=18, CAPTURE=1, CHARGE=45, COLLECT=302, CONJURE=536, CREATE=194, CURSE=4, ENEMY=148, FLY=427, FORTIFY=398, IF=565, INVEST=1287, LURK=302, MINE=62, MOVE=491, NAME=1052, NEUTRAL=131, OFFER=16, PASSAGE=53, PASSWORD=80, PAY=201, POST=432, PRAY=432, PREACH=1622, PROBE=5, PROMOTE=441, RECRUIT=3370, REPAY=174, REPORT=334, SAY=554, SCAN=52, SCRY=565, SEARCH=234, SECURE=2363, STUDY=1490, SUMMON=159, TAX=2400, TELEPORT=17, TRADE=265, TRAIN=532, UNFORTIFY=6, WORK=554 | 3.0 | 0 | +0/−0 | 108.4 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scripted:military` | 39 | 1.0 | 0.013 | 3816 | 11 | 574 | 2262 | 2400 |
| `scripted:religious` | 41 | 1.0 | 0.013 | 3370 | 11 | 491 | 2363 | 2400 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `scripted:military` | 13.0 | 9.0 |
| `scripted:religious` | 11.0 | 9.0 |

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
