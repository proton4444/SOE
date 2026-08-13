# Arena — head-to-head

- **Policies:** `llm:openai/gpt-4o-mini:expansionist-v1` vs `random`
- **Map:** starter_map.json
- **Games:** 8 (30 turns each, both seat orderings per seed)
- **Decisive:** 8  ·  **Draws:** 0

## Win rate

| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 0 | 0.0% | 0 | 0 |
| `random` | 8 | 100.0% | 1629 | 0 |

## Paired result (the signal)

Each seed is played twice on the *same* map with the seats exchanged.
A **sweep** — one policy winning from both seats — cannot be explained
by start-city luck. A **split** is the map talking, not the policy.

- **Sweeps:** `llm:openai/gpt-4o-mini:expansionist-v1` 0, `random` 4
- **Splits:** 0 / 4

## What decided each game

| Metric | Games |
|---|---:|
| secured | 7 |
| gold | 1 |

| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |
|---|---|---|---|
| `AR000` | random | random | swept by random |
| `AR001` | random | random | swept by random |
| `AR002` | random | random | swept by random |
| `AR003` | random | random | swept by random |

## Reliability (LLM seats)

| Policy | Calls | Completed | Failures | Parseable | No-op turns | Retried |
|---|---:|---:|---|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 240 | 0 | not_configured=240 | 0.0% | 240 | 0 |
| `random` | 240 | 240 | — | 100.0% | 0 | 0 |

| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |
|---|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | — | — | — | unknown |
| `random` | — | — | — | unknown |

## Strategy (per policy)

| Policy | Order families | First contact (median) | Eliminations | Territory +/− | Midgame soldiers |
|---|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | — | 6.0 | 0 | +0/−0 | 0.0 |
| `random` | ATTACK=55, AWAIT=177, COLLECT=166, INVEST=151, MOVE=156, RECRUIT=293, SECURE=144, STUDY=158, TAX=183, WORK=146 | 6.0 | 0 | +0/−0 | 39.7 |

## Blueprint differentiation

The gate requires the difference to show in orders or game state, not only in the rationale text.

| Blueprint | Wins | Survival | Contact | Recruit | Attack | Movement | Secure | Tax |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | 0 | 1.0 | 0.375 | 0 | 0 | 0 | 0 | 0 |
| `random` | 8 | 1.0 | 0.375 | 293 | 55 | 156 | 144 | 183 |

| Blueprint | First recruit (median) | First attack (median) |
|---|---:|---:|
| `llm:openai/gpt-4o-mini:expansionist-v1` | — | — |
| `random` | 15.0 | 13.0 |

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
