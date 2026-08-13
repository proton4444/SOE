# Arena — head-to-head

- **Policies:** `llm:openai/gpt-4o-mini:expansionist-v1` vs `scripted:military`
- **Map:** calib_12.json
- **Games:** 8 (30 turns each, both seat orderings per seed)
- **Decisive:** 8  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate | Submitted lines | Warned lines | Warning rate |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 7 | 87.5% | 923 | 34 | 3.7% |
| `scripted:military` | 1 | 12.5% | 2063 | 148 | 7.2% |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `llm:openai/gpt-4o-mini:expansionist-v1` 3, `scripted:military` 0
- **Splits:** 1 / 4

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 8 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR001` | scripted:military | llm:openai/gpt-4o-mini:expansionist-v1 | split |
| `AR002` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR003` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 240 | 240 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 1926.2 | 767147 | 13500 | 0.119935 |

## Emitted order quality (before safety filtering)

| Policy | Emitted lines | Warned lines | Warning messages | Warned-line rate |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 924 | 1 | 1 | 0.1% |

The Phase 0 threshold is at most 5% of emitted order lines carrying one or more warnings. Multiple messages on one line count once.

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | AWAIT=143, COLLECT=12, MOVE=233, RECRUIT=241, SECURE=54, TAX=240 | — | 0 | +0/−0 | 189.4 |
| `scripted:military` | ABSORB=5, ADDRESS=8, ALLY=8, BORROW=4, BUILD=7, CHARGE=8, COLLECT=40, CONJURE=56, CREATE=29, ENEMY=24, FLY=63, FORTIFY=24, IF=57, INVEST=93, LURK=35, MINE=7, MOVE=45, NAME=95, NEUTRAL=8, PASSWORD=8, PAY=14, POST=58, PROMOTE=30, RECRUIT=354, REPAY=18, REPORT=29, SAY=67, SCAN=7, SCRY=57, SEARCH=40, SECURE=236, STUDY=123, SUMMON=32, TAX=240, TELEPORT=1, TRADE=24, TRAIN=47, WORK=62 | — | 0 | +0/−0 | 104.2 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 7 | 1.0 | 0.0 | 241 | 0 | 233 | 54 | 240 |
| `scripted:military` | 1 | 1.0 | 0.0 | 354 | 0 | 45 | 236 | 240 |

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
