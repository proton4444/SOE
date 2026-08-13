# Arena — head-to-head

- **Policies:** `llm:openai/gpt-4o-mini:expansionist-v1` vs `random`
- **Map:** starter_map.json
- **Games:** 8 (30 turns each, both seat orderings per seed)
- **Decisive:** 8  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 8 | 100.0% | 3306 | 352 |
| `random` | 0 | 0.0% | 1629 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `llm:openai/gpt-4o-mini:expansionist-v1` 4, `random` 0
- **Splits:** 0 / 4

## What decided each game

| Metric | Games |
|---|---:|
| soldiers | 5 |
| secured | 3 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR001` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR002` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |
| `AR003` | llm:openai/gpt-4o-mini:expansionist-v1 | llm:openai/gpt-4o-mini:expansionist-v1 | swept by llm:openai/gpt-4o-mini:expansionist-v1 |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 240 | 240 | — | 100.0% | 0 | 0 |
| `random` | 240 | 240 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 3916.9 | 616832 | 50564 | 0.121635 |
| `random` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | ALLY=1, ATTACK=373, AWAIT=473, ENEMY=1, FLY=5, INVEST=518, MINE=2, MOVE=352, NEUTRAL=1, RECRUIT=644, SAIL=22, SECURE=352, STUDY=7, SUMMON=5, TAX=548, WORK=2 | 4.0 | 0 | +0/−0 | 222.4 |
| `random` | ATTACK=39, AWAIT=181, COLLECT=164, INVEST=159, MOVE=159, RECRUIT=294, SECURE=144, STUDY=162, TAX=183, WORK=144 | 4.0 | 0 | +0/−0 | 38.3 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 8 | 1.0 | 0.625 | 644 | 373 | 352 | 352 | 548 |
| `random` | 0 | 1.0 | 0.625 | 294 | 39 | 159 | 144 | 183 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 18.0 | 16.0 |
| `random` | 15.0 | 10.0 |

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
