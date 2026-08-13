# AI War-Room Dashboard — Plan

Status: **in progress (M1)** · Owner: engine team · Source: `docs/ai_dashboard_plan.md`

## Goal

A host-facing "war room" where a gamemaster can:

1. **Create games** — pick a map, choose slots, decide per-slot player type.
2. **Create agents / subagents for each player** — managed AI players that
   occupy faction seats, with persona, model, and per-turn subagent roles.
3. **Progress turns from an event monitor** — a live timeline of resolution
   events; auto-play loop (think → submit → resolve → repeat) with speed
   control.
4. **Let the AI see the map** — agents receive both structured positions and
   rendered map images (fog-of-war aware) so vision-capable models can plan
   from visuals.

## What exists today (reuse, not rebuild)

| Piece | Where |
|---|---|
| Rooms (code + PIN + host key, slots, maps) | `webapp/rooms.py` — `Room`, `RoomPlayer`, `RoomStore` |
| Human pages + agent JSON API | `webapp/main.py` — `/create`, `/join`, `/api/rooms/*` |
| Turn resolution + event stream | `webapp/service.py::resolve_turn`, `turn_events.jsonl` |
| Master dashboard (readiness, events, all-visible map) | `/room/{code}/master` + `partials/master_panel.html` |
| Faction overlays on SVG map | `service.map_overlay()` + `mapview.render_svg()` |
| Fog-of-war structured state for agents | `service.player_state()` |

Key existing model facts:

- `RoomPlayer.kind` is `empty | human | agent` — the seat holder. A bot is a
  separate concept: an **agent profile** attached to a faction.
- Faction ids are `player_{i+1}`; `service.create_game()` seeds characters and
  start cities deterministically from the room code.
- Agents already authenticate with `X-Agent-Key` (header) or `key` (query).
- Deterministic seeds: `service.deterministic_seed(room, turn)`; single-worker
  server required (global stores are in-memory + file-backed).

## New components

### `webapp/ai/` package

```
webapp/ai/
├── __init__.py
├── registry.py      # AgentProfile + file-backed registry (M1)
├── brain.py         # LLM adapter — provider/model from env (M2)
├── orchestrator.py  # per-turn pipeline: think → submit → resolve (M4)
└── subagents.py     # role prompts + tool dispatch (M3)
```

### Agent model (M1)

```python
@dataclass
class AgentProfile:
    model: str = ""            # default from SOE_LLM_MODEL
    persona: str = ""          # e.g. "Aggressive expansionist, hoards gold"
    temperature: float = 0.0   # deterministic by default
    enabled: bool = False      # false = slot plays as human/external agent
    state: str = "idle"        # idle | thinking | submitted | done | error
    last_error: str = ""
    last_run_at: str = ""
```

Persisted in `server_data/agents.json` — `{"agents": {room_code: {faction_id: profile}}}`.
Same file-based, atomic-write, thread-safe ethos as `RoomStore`.

### Subagents (M3)

Per-turn bounded role tasks spawned by the orchestrator:

- `strategist` (strong model): reads state + map image + report → decides orders.
- `field` (cheap model, one per character): micro-orders — move, recruit, tax.
- `intel` (cheap model): summarises sightings, diplo stance, threats.

Results flow up to the strategist; final orders go through the existing
`service.submit_orders` path.

### Turn monitor & progression (M4)

- Live timeline on the master dashboard: poll `turn_events.jsonl`, grouped by
  turn and phase (movement, combat, income…), filterable.
- Auto-play loop: resolve → for each enabled bot: think → submit → when all
  submitted → resolve again. Speed control + pause/stop.
- Extend `turn_events.jsonl` events with phase/position fields so the timeline
  can animate the map.

### AI map visuals (M5)

`GET /api/rooms/{code}/map?faction=f1&format=svg|png|json`:

- `svg` — existing `render_svg(map_file, map_overlay(...))` for that faction's
  fog of war.
- `png` — rendered via `cairosvg` (new dependency) for vision-capable models.
- `json` — structured positions: city coords, what the faction sees, their
  units — for non-vision models.
- `?turn=N` — snapshot of the map at the end of turn N (re-load state file).

## API surface (new)

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /api/rooms/{code}/agents` | host key | list bot profiles per faction |
| `PUT /api/rooms/{code}/agents/{faction_id}` | host key | upsert profile |
| `DELETE /api/rooms/{code}/agents/{faction_id}` | host key | remove profile |
| `POST /api/rooms/{code}/agents/{faction_id}/run` | host key | run one bot's turn (decide + submit) |
| `POST /api/rooms/{code}/agents/run-all` | host key | run every enabled bot |
| `GET /api/rooms/{code}/map` (M5) | player/agent key | fog-of-war map visuals |
| `GET /room/{code}/setup` (host cookie) | host | setup dashboard page |
| `POST /room/{code}/setup/agents/{faction_id}` (host cookie) | host | configure from the UI (save/clear/run) |

## Implementation order

| # | Milestone | Contents | Status |
|---|---|---|---|
| M1 | Setup dashboard + agent registry | `webapp/ai/registry.py`, agent CRUD API, `/room/{code}/setup` UI, bot badges in status | ✅ done |
| M2 | Brain + strategist loop | `brain.py` (OpenRouter/OpenAI-compatible, env-configured), orchestrator plays a full turn; `run`/`run-all` API + setup UI buttons | ✅ done |
| M3 | Subagent system | `subagents.py`: intel briefing + field drafts per leader; strategist prompt whitelist; parser-filtered orders (`_filter_clean_orders`); `SOE_SUBAGENT_MODEL`/`SOE_MAX_SUBAGENTS` env | ✅ done |
| M4 | Event monitor + auto-play | `autoplay.py` background loop (bots → resolve → repeat, force/wait-for-humans options, stop on demand); master dashboard timeline grouped by turn with phase tags + phase/faction filters; validated live (2 turns, 48 events) | ✅ done |
| M5 | AI map endpoints | `GET /api/rooms/{code}/map?format=json|svg|png&turn=N` with fog of war; per-turn snapshots (`state_turnN.json`); PNG via cairosvg → playwright fallback; `SOE_BOT_VISION=1` attaches the map PNG to the strategist call; validated live | ✅ done |
| M6 | Hardening | 429/5xx retries with Retry-After backoff; provider error messages surfaced; autoplay circuit breaker (3 failures → suspend); determinism guard (`post_state_sha` + `scripts/verify_determinism.py`); `/healthz` AI section; `SOE_LLM_RETRIES`/`SOE_LLM_MAX_TOKENS`/`SOE_SUBAGENT_TOKENS` env; validated live | ✅ done |

## Workflows (deploy to the server box)

`workflows/` holds automation for the machine that holds the game files:

- `workflows/bot_loop.py` — headless auto-play: run every enabled bot for N
  turns (subagents → strategist → parser-filtered orders → seeded resolve),
  with per-bot error tolerance. Validated live (2026-08-10): 2 bots × 2 turns,
  deterministic seeds, warnings cleared by turn 2.
- `workflows/README.md` — usage + the robocopy command to deploy to a remote
  PC.

## M4 notes (2026-08-10)

- **Timeline**: the master dashboard's gameplay feed is now grouped per turn
  (`<details>` per turn, newest first), with engine-phase tags and filter
  chips (`?phase=combat` etc.) that the HTMX poll preserves.
- **Auto-play**: `webapp/ai/autoplay.py` runs one daemon thread per room.
  Options on the master dashboard: turns, seconds between turns, force
  resolve (missing humans count as empty), wait for humans. Stop is
  cooperative — a mid-LLM-call cycle finishes before the loop checks again.
- Found and fixed a real shadowing bug while wiring filters:
  `for faction_id, faction in state.factions.items()` rebinds `faction`,
  silently clobbering a filter parameter of the same name (and adding 8 mypy
  errors). Filter params are now named `phase_filter`/`faction_filter`.

## M5 notes (2026-08-10)

- **Endpoint**: `GET /api/rooms/{code}/map` — a player key sees their seat's
  fog of war; the host key sees everything (or one faction with
  `faction=player_N`). `format=json` returns a compact coordinate-bearing
  board (`x`/`y` per city from the map layout, observed flags, holders);
  `format=svg` the rendered board; `format=png` a raster for vision models.
- **Rewind**: every resolution writes `state_turn{N}.json` (turn 0 on game
  creation), so `?turn=N` shows the board at the end of that turn. Unknown
  turns → 404.
- **PNG backend** (`webapp/mapimg.py`): cairosvg first (needs native cairo),
  then playwright/chromium — this machine has no cairo DLL, so the
  playwright fallback is what actually runs (~1-2s per render). Neither
  available → 501 with a clear message.
- **Vision in the loop**: `SOE_BOT_VISION=1` attaches the faction's fog-of-war
  map PNG (data URI) to the strategist call. Off by default because text-only
  models reject image parts. Validated live: gpt-4o-mini accepted the map and
  played a full turn (16 orders, 2 warnings).

## M6 notes (2026-08-10)

- **Retries**: `brain.chat` now retries on 429 and 5xx (was: transport only),
  honouring `Retry-After` (capped at 30s); `SOE_LLM_RETRIES` controls the
  count. Non-retryable HTTP errors carry the provider's own message (≤200
  chars, e.g. "Insufficient credits") so the dashboard explains itself.
- **Budgets**: `SOE_LLM_MAX_TOKENS` (strategist/default output), 
  `SOE_SUBAGENT_TOKENS`, `SOE_LLM_TIMEOUT`, `SOE_MAX_SUBAGENTS` — all env.
- **Circuit breaker**: autoplay suspends a bot after 3 consecutive turn
  failures (logged to the run log) so one broken profile can't stall a room.
- **Determinism guard**: every completed resolution records
  `post_state_sha` (SHA-256 of the post-turn state) in
  `resolution_events.jsonl`. `scripts/verify_determinism.py --code X --turn N`
  replays turn N from the pre-turn snapshot + recorded order files + the
  deterministic seed and compares hashes — validated live: clean replay
  matches, tampered orders mismatch. Note: the guard checks *reproducibility
  of inputs*, not current `state.json` integrity (it re-derives the state).
- **Ops**: `/healthz` now reports `ai: {configured, model, base_url, vision}`
  — no secrets.

## Constraints (kept from the codebase)

- Deterministic engine: seeded turns; bot calls never mutate game state.
- File-based persistence; no databases.
- No secrets in logs, URLs, or the dashboard; agent keys never exposed beyond
  the joiner.
- Single-worker uvicorn; registry mirrors the `RoomStore` singleton pattern.
- Bot profiles are not credentials — a profile says *how* a faction plays, the
  seat holder still holds the key.

## Testing

- `tests/test_webapp.py` grows an agent-registry section (host-gated CRUD,
  persistence, 404s, bot flags in `/status`).
- Subagent/LLM logic is tested with a fake `brain` (no network in tests).

## Model guide (OpenRouter, checked 2026-08-10)

Selection criteria: strict order-format adherence (the `--- ORDERS ---`
marker), vision for M5 map images, and cost — a full game (50 turns × 6
factions) costs ~$0.60 at gpt-4o-mini, so compliance, not price, decides.

| Role | Model | $ in/out per 1M | Vision | Probe (2026-08-10) |
|---|---|---|---|---|
| Strategist (default) | `openai/gpt-4o-mini` | 0.15 / 0.60 | ✅ | ✅ passes |
| Strategist (quality) | `openai/gpt-4.1-mini` | 0.40 / 1.60 | ✅ | ✅ passes |
| Strategist (reasoning) | `google/gemini-2.5-flash` | 0.30 / 2.50 | ✅ | ❌ essays, ignores order format |
| Strategist (budget) | `meta-llama/llama-3.3-70b-instruct` | 0.10 / 0.32 | ❌ | ❌ garbled output |
| Field/intel (M3) | `google/gemini-2.5-flash-lite` | 0.10 / 0.40 | ✅ | untested |
| Field/intel (M3) | `qwen/qwen3-32b` | 0.08 / 0.28 | ❌ | ✅ passes (text-only budget) |
| Free fallback | `google/gemma-4-31b-it:free` | 0 | ✅ | untested (rate-limited) |

Live end-to-end (2026-08-10, gpt-4o-mini): two bots played turn 1 of a live
game — orders submitted (15-16 parsed each), turn resolved with a seeded,
reproducible run. Observed LLM behaviours to prompt against: movement-order
"city touring" (now capped in the strategist prompt), attacks on cities
instead of characters, `Invest.` without amount/city.

Verify a candidate before adopting it: `python scripts/probe_model.py <model>`
runs one order-writing task through `webapp.ai.brain` and reports marker +
parse compliance (needs `SOE_LLM_KEY`).

## Decisions log

- Bots are registry entries, not `RoomPlayer.kind` changes — keeps rooms.json
  backward compatible and the seat/key model untouched.
- `temperature=0.0` default for reproducibility; persona overrides are
  encouraged via the setup UI.
- **Provider: OpenRouter** (M2). `brain.py` speaks the OpenAI-compatible
  `chat/completions` format against `SOE_LLM_BASE` (default
  `https://openrouter.ai/api/v1`), key from `SOE_LLM_KEY`, default model from
  `SOE_LLM_MODEL` (default `openai/gpt-4o-mini`). An Anthropic/Gemini client
  can be added later behind the same `chat()` interface.
- The strategist reply convention: reasoning first, then a `--- ORDERS ---`
  marker line, then one order per line. The orchestrator strips everything
  before the marker and submits through `service.submit_orders`, so bots share
  the exact same validation and persistence as humans.
