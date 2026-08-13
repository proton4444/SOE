# Arena — head-to-head

- **Policies:** `llm:openai/gpt-4o-mini:expansionist-v1` vs `scripted:military`
- **Map:** calib_12.json
- **Games:** 80 (30 turns each, both seat orderings per seed)
- **Decisive:** 80  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate | Submitted lines | Warned lines | Warning rate |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 64 | 80.0% | 9479 | 342 | 3.6% |
| `scripted:military` | 16 | 20.0% | 20130 | 1704 | 8.5% |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `llm:openai/gpt-4o-mini:expansionist-v1` 25, `scripted:military` 1
- **Splits:** 14 / 40

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 70 |
| secured | 9 |
| gold | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR001` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR002` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR003` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR004` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR005` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR006` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR007` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR008` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR009` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR010` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR011` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR012` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR013` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR014` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR015` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR016` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR017` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR018` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR019` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR020` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR021` | llm:openai/gpt-4o-mini:expansionist-v1 | scripted:military | split |
| `AR022` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR023` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR024` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR025` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR026` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR027` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR028` | scripted:military | scripted:military | swept by scripted:military |
| `AR029` | llm:openai/gpt-4o-mini:expansionist-v1 | scripted:military | split |
| `AR030` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR031` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR032` | llm:openai/gpt-4o-mini:expansionist-v1 | scripted:military | split |
| `AR033` | llm:openai/gpt-4o-mini:expansionist-v1 | scripted:military | split |
| `AR034` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR035` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR036` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR037` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR038` | llm:openai/gpt-4o-mini:expansionist-v1 | scripted:military | split |
| `AR039` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Accepted | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 2400 | 2400 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 2035.2 | 7663960 | 147096 | 1.225473 |

## Emitted order quality (before safety filtering)

| Policy | Emitted lines | Warned lines | Warning messages | Warned-line rate |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 9470 | 11 | 11 | 0.1% |

The Phase 0 threshold is at most 5% of emitted order lines carrying one or more warnings. Multiple messages on one line count once.

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | AWAIT=1433, COLLECT=174, INVEST=11, MOVE=2320, RECRUIT=2434, SECURE=713, TAX=2394 | 2.0 | 1 | +0/−0 | 182.7 |
| `scripted:military` | ABSORB=58, ADDRESS=80, ALLY=80, ATTACK=43, BORROW=64, BUILD=65, CAPTURE=5, CHARGE=76, COLLECT=290, CONJURE=552, CREATE=207, ENEMY=240, FLY=737, FORTIFY=259, FREE=1, IF=564, INVEST=884, LURK=265, MINE=76, MOVE=225, NAME=1022, NEUTRAL=80, PASSAGE=14, PASSWORD=80, PAY=183, POST=365, PROBE=15, PROMOTE=370, RECRUIT=3642, REPAY=180, REPORT=370, SAY=603, SCAN=55, SCRY=560, SEARCH=320, SECURE=2199, STUDY=1228, SUMMON=310, TAX=2377, TELEPORT=23, TRADE=230, TRAIN=506, UNFORTIFY=10, WORK=617 | 2.0 | 0 | +0/−0 | 118.1 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 64 | 0.988 | 0.075 | 2434 | 0 | 2320 | 713 | 2394 |
| `scripted:military` | 16 | 1.0 | 0.075 | 3642 | 43 | 225 | 2199 | 2377 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 16.0 | — |
| `scripted:military` | 12.0 | 15.0 |

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
