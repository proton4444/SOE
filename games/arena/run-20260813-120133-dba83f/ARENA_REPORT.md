# Arena — head-to-head

- **Policies:** `llm:openai/gpt-4o-mini:expansionist-v1` vs `scripted:military`
- **Map:** calib_12.json
- **Games:** 4 (30 turns each, both seat orderings per seed)
- **Decisive:** 4  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate | Submitted lines | Warned lines | Warning rate |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 3 | 75.0% | 488 | 41 | 8.4% |
| `scripted:military` | 1 | 25.0% | 1053 | 76 | 7.2% |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `llm:openai/gpt-4o-mini:expansionist-v1` 1, `scripted:military` 0
- **Splits:** 1 / 2

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 3 |
| secured | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR001` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 120 | 120 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 1959.0 | 384563 | 7080 | 0.061313 |

## Emitted order quality (before safety filtering)

| Policy | Emitted lines | Warned lines | Warning messages | Warned-line rate |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 482 | 18 | 29 | 3.7% |

The Phase 0 threshold is at most 5% of emitted order lines carrying one or more warnings. Multiple messages on one line count once.

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | AWAIT=65, COLLECT=5, ENEMY=2, MOVE=139, RECRUIT=117, SECURE=35, TAX=124, WORK=1 | — | 0 | +0/−0 | 174.5 |
| `scripted:military` | ABSORB=5, ADDRESS=4, ALLY=4, BORROW=2, BUILD=5, CHARGE=8, COLLECT=18, CONJURE=29, CREATE=13, ENEMY=12, FLY=27, FORTIFY=10, IF=29, INVEST=42, LURK=19, MINE=4, MOVE=18, NAME=49, NEUTRAL=4, PASSWORD=4, PAY=5, POST=26, PROMOTE=17, RECRUIT=178, REPAY=10, REPORT=16, SAY=33, SCAN=5, SCRY=28, SEARCH=40, SECURE=118, STUDY=67, SUMMON=17, TAX=120, TELEPORT=1, TRADE=13, TRAIN=23, WORK=30 | — | 0 | +0/−0 | 102.8 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 3 | 1.0 | 0.0 | 117 | 0 | 139 | 35 | 124 |
| `scripted:military` | 1 | 1.0 | 0.0 | 178 | 0 | 18 | 118 | 120 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 16.0 | — |
| `scripted:military` | 12.0 | — |

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
