# SOE (Alpha)

A deterministic play-by-email (PBEM) engine for a fantasy strategy game of
factions, characters and magic. Its rules reference is
[`MECHANICS.md`](MECHANICS.md).

## Overview

This is an alpha implementation of a turn-based engine that processes English-like orders and generates per-player reports. The engine is designed to be:

- **Deterministic**: Same inputs + same seed = identical outputs
- **File-based**: No databases, pure JSON/YAML persistence
- **Modular**: Clean separation of parsing, game logic, and reporting
- **Extensible**: Easy to add deferred features from the full rules

> **v1.1.0 — all 89 command verbs.** The remaining eight commands
> ship (`WORK`, `TRAIN`, `UNNAME`, `CREATE` elite troops, `INVEST`, `BUY
> PASSAGE`, `PREACH`, `OFFER` with independent characters), plus `IF`
> statements with `else`, `THEN` sequencing, and the sailing skill. Every
> command verb is now recognised. See
> [`MECHANICS.md`](MECHANICS.md).

## Features (Alpha v1.1.0)

### Implemented

✅ **World & Map**
- Cities with population bands (<1k, 1k-9k, 10k-99k, 100k+)
- Roads and sea lanes with quality ratings
- JSON-based map files
- Port cities for ship construction
- Location security and access control

✅ **Factions & Characters**
- Multiple player factions with full diplomacy system
- Ally/Enemy/Neutral diplomatic stances
- Secured locations (territorial control)
- Named characters with combat, magic, and religion skills
- Character health system (0-100, affects skill effectiveness)
- Character death and wounding in combat
- Character prisoners (capture and release)
- Character skill training (study and teach)
- Unit stacks (soldiers, sailors, workers, slaves)
- Per-character gold purses (legacy faction treasury migrates on load)
- Ships (galleys)
- Non-combatant and lurking status flags
- Magical items: amulets, crystals, orbs, rings and wands

✅ **Core Orders**
- **Movement**: Land movement between cities (GO/MOVE/TRAVEL)
- **Sailing**: Sea movement with ships (SAIL command)
- **Flying**: Magical flight bypassing roads (FLY command)
- **Recruiting**: RECRUIT/HIRE soldiers, sailors, and workers
- **Buying ships**: Purchase galleys at ports
- **Combat**: Simplified combat with character wounding/death
- **Capture**: CAPTURE command to take prisoners
- **Prisoner ops**: FREE/RELEASE, KILL/EXECUTE, ENSLAVE, INTERROGATE
- **Status**: NONCOM/COMBATANT, LURK/UNLURK
- **Magic**: Teleportation and flight spells
- **Magical items**: CONJURE, CHARGE/RECHARGE, ABSORB, SCAN with an orb
- **Pronouns**: `me`/`I`/`you`, `him`/`her`, `it`, `them` and the reflexives
- **Communication**: SAY/TELL, POST, REPORT/QUERY, ADDRESS, PASSWORD
- **Healing**: HEAL/CURE commands using religion skill
- **Location Control**: SECURE command for territorial control
- **Diplomacy**: ALLY/ENEMY/NEUTRAL commands
- **Unit/Gold Transfers**: ASSIGN/GIVE, GET/TAKE/OBTAIN, TRANSFER (bank fee)
- **UNLOAD**: detach a co-located character as independent (group model thin)
- **Finance**: PAY (wage debt), BORROW/REPAY (bankers guild)
- **Character Management**: NAME command to convert units to characters
- **Titles**: PROMOTE command to assign character titles
- **Taxation**: TAX command to collect taxes into the actor's purse
- **Training**: STUDY command to learn skills (costs gold)
- **Teaching**: TEACH command for character-to-character training (free)
- **Summoning**: SUMMON command to create magical creatures (costs magic power)
- **Resource Gathering**: COLLECT/GATHER commands for wood and stone
- **Mining**: MINE command to extract minerals (iron, gold, silver, copper, gems)
- **Construction**: BUILD/CONSTRUCT/MAKE commands to build galleys, catapults, weapons, and armor
- **Labour**: WORK for wages (population-scaled; nothing in tiny towns)
- **Training**: TRAIN command to convert workers into soldiers or sailors
- **Unnaming**: UNNAME command to convert a named character back to a worker
- **Elite troops**: CREATE command to form named elite troop units that train
  continuously (level rises about one point per five weeks), fight at their
  own level, draw salary by size × level, and must belong to a group leader
- **Investment**: INVEST command to grow a town's population (the only way
  population rises; weekly checks spend ~population/100 gold, and a town's
  income band can step up)
- **Sea travel without a ship**: BUY PASSAGE on a direct sealane (costs the
  party's size in gold, may fail for large groups, `definitely` helps)
- **Preaching**: PREACH to collect tithes scaled by religion skill and
  population, sometimes attracting followers
- **Recruiting NPCs**: OFFER gold to independent characters (from
  `players.yaml`), who accept at half their best level squared plus item
  value; prisoners of yours always accept
- **Conditionals**: IF ... THEN ... (OTHERWISE/ELSE) statements, scoped to
  the end of their sentence and never nested; conditions test gold, units,
  resources, galleys, summoned creatures, magic/religious power, and
  encumbrance (approximated by group size)
- **Sequencing**: THEN chains commands after a wait or in sequence

✅ **Groups & Group Leaders**
- A character is either assigned to somebody or leads their own group
- Groups travel together — moving a leader moves their people and their units
- Unit stacks belong to a character and march with them; recruits join the
  character who raised them
- `JOIN` and `ASSIGN` are the same operation from opposite ends
- `UNLOAD` sets a character loose without ordering them to do anything else
- A direct order (the `HAVE` form) promotes its target to group leader
- `LURK` covers the whole group, as the rules require
- `SUPPORT` puts a character into somebody else's battle without merging groups

✅ **Fog of War & Intel**
- Position bands: *inside* (default), *outside*, *near* — `go to outside Rome`
- Visibility matrix from the rules (inside sees outside, near is hard to spot, …)
- End-of-turn sightings: co-located enemies appear in the turn report only when
  noticed; LURK multiplies detection chance by ¼; larger groups are harder to hide
- `PROBE` — magical report of another player's character (25 power, skill vs
  effective skill resistance)
- `SEARCH`/`EXPLORE` — dig uninhabited ruins (must be inside; gold placeholder
  until magical items exist)
- `SCAN` — parsed, fails cleanly until orbs are inventory items

✅ **Order Queue**
- Orders persist on a per-character queue across turns and through save/load
- `AWAIT`/`WAIT FOR` — wait a duration, or wait for a named character to arrive
- `REPEAT`/`repeatedly` — loop the following orders, for a count or until halted
- `HALT` (immediate) and `STOP` (planned) cancel what has not started
- Queued orders are validated when they execute, against the world they land in
- Unblocked characters still resolve their whole submission in the same turn

✅ **Turn Processing**
- Phase 0: Order queue — HALT, intake, and one drain pass
- Phase 1: Validation, then group leadership
- Phase 2: Movement (land), then sailing (sea)
- Phase 3: Recruit & buy
- Phase 4: Magic (absorb, teleport, fly, heal), summoning, conjuring, charging,
  religion, then magic-free zone drain
- Phase 5: Combat (with character casualties), then capture
- Phase 6: Income & upkeep (wage debt + loan interest)
- Phase 7: Location control, diplomacy, assign/join/support, taxation, trade,
  gathering, mining, construction, transfers, get/unload, naming, promotion,
  prisoner ops, status flags, finance, study & teach
- Phase 8: Cleanup — support expiry, item regeneration and expiry, prisoner
  escape and natural healing

✅ **Economic System**
- City income based on population
- Unit and ship upkeep
- Character salaries (formula-based)
- Negative treasury warnings

✅ **Health & Healing**
- Character health (0-100)
- Natural healing (7 points per turn)
- Religious healing with HEAL/CURE commands
- Health affects skill effectiveness
- Character death at 0 health

✅ **Naval System**
- SAIL command for sea movement
- Crew requirements (10 sailors minimum, 40 rowers optimal)
- Sea lane pathfinding
- Ship capacity and encumbrance tracking
- Automatic unit transport on ships

✅ **Reporting**
- Per-player detailed reports
- Event logs with combat results
- Warning/error messages
- Character casualty reports

✅ **CLI**
- Game initialization
- Turn processing
- State inspection

✅ **Diplomacy System**
- ALLY command to declare allies
- ENEMY command to declare enemies
- NEUTRAL command to reset diplomatic stance
- Diplomatic relationships tracked per faction
- Foundation for access control based on alliances

✅ **Location Control**
- SECURE command to control locations
- Only one faction can secure a location
- Must attack to takeover secured locations
- Secured cities tracked per faction
- Foundation for taxation and access control

✅ **Prisoner System**
- CAPTURE command to take enemy characters prisoner
- Success based on power ratio (50% base + power advantage)
- Failed captures deal damage or kill targets
- FREE/RELEASE/DISCARD/DISMISS to free prisoners
- Prisoners tracked with captor_id

✅ **Skill Training System**
- STUDY command to learn/improve skills (1 gold/week)
- TEACH command for faster skill gains (free, needs teacher)
- Skills: combat, magic, religion, sailing
- Random gains: STUDY (1-5 per week), TEACH (2-7 per week)
- Teacher must have higher skill level
- Skills capped at 100

✅ **Summoning System**
- SUMMON command to create magical creatures
- 8 creature types: skeleton, zombie, harpy, minotaur, griffin, chimera, dragon, demon
- Magic power costs: 1-50 per creature (scales with power)
- Creatures add to combat power (attack: 2-75, defense: 1-70)
- Alpha: creatures never expire (simplified)
- Creatures fight for their summoner

✅ **Resource Gathering System**
- COLLECT/GATHER commands for resources
- Wood gathering: requires forest terrain (3/worker/day)
- Stone gathering: requires hills/mountains (2/worker/day)
- Workers required to gather resources
- Resources stored in character inventory
- Foundation for construction system

✅ **Mining System**
- MINE command to extract minerals from hills/mountains
- 5 mineral types: iron, gold, silver, copper, gems
- Worker-based yield rates (iron: 2/day, copper: 3/day, silver: 4/day, gold: 5/day, gems: 6/day)
- Requires hills or mountains terrain
- Workers required for mining operations
- Resources stored in character inventory
- Alpha: no richness variation (simplified)
- Iron used for weapon/armor construction

✅ **Construction System**
- BUILD/CONSTRUCT/MAKE commands to build items
- Supports 4 item types:
  - Galleys: 200 wood each (must be at port city)
  - Catapults: 4 wood each
  - Weapons: 1 iron each
  - Armor: 1 iron each
- All costs based on 1/5 of basic item cost
- Instant construction (alpha simplification)
- Resources consumed from character inventory
- Items stored in inventory (future: combat integration)
- Future: fortifications, siege equipment, more item types

### Deferred to Future Versions

⏸️ **Still To Implement:**
- Sub-turn game time — the queue's smallest unit is one weekly turn
- Retreat and morale in combat
- Encumbrance and item weight (BUY PASSAGE and IF encumbrance checks use the
  party's head-count as a stand-in)
- Group-level possession of ships, resources and gold
- Resource depletion (accumulation and its cap are in; depletion is not)
- `QUIETLY`/`SILENTLY` parse, but report-line suppression is not implemented
- `CREATE`'s elite troops cannot yet be assigned between leaders or disbanded

Every command verb is now recognised. [`MECHANICS.md`](MECHANICS.md)
has the command-by-command breakdown and the archived
[`alpha_scope.md`](docs/archive/pre-agent-competition-2026-08-11/alpha_scope.md)
records what the alpha deliberately left out.

## Installation

### Requirements

- Python 3.11+
- pip

### Setup

```bash
# Clone/download the repository
cd SOE

# Install dependencies
pip install -r requirements.txt

# Or install with development dependencies
pip install -e ".[dev]"
```

## Quick Start

### 1. Create Example Files

```bash
python3 cli.py example-setup
```

This creates:
- `maps/sample_map.json` - A small 5-city map
- `examples/players.yaml` - Example factions
- `examples/orders_player*_turn1.txt` - Sample order files

### 2. Initialize a Game

```bash
python3 cli.py init-game mygame \
  --map maps/sample_map.json \
  --players examples/players.yaml
```

This creates a new game in `games/mygame/` with initial state.

### 3. Prepare Order Files

```bash
mkdir -p games/mygame/orders
cp examples/orders_player1_turn1.txt games/mygame/orders/player_1_turn1.txt
cp examples/orders_player2_turn1.txt games/mygame/orders/player_2_turn1.txt
```

### 4. Process a Turn

```bash
python3 cli.py process-turn mygame --turn 1 --seed 42
```

### 5. View Reports

```bash
cat games/mygame/reports/player_1_turn1.txt
```

### 6. Continue Playing

Edit order files for turn 2:

```bash
# Edit games/mygame/orders/player_1_turn2.txt
python3 cli.py process-turn mygame --turn 2 --seed 123
```

## Order Syntax

Orders use English-like commands. Examples:

```
# Movement (Land)
Have Emperor Marcus go to Kitesta.
Go to Riverton.

# Sailing (Sea)
Have Captain Ahab sail to Island City.
Sail to Port Town.

# Flying (Magic)
Have Wizard Merlin fly to Distant City.
Fly to Enemy Territory.

# Recruiting
Recruit 20 soldiers in Madegi Doy.
Have Khan Tengri recruit 10 sailors.

# Buying ships
Buy 1 galley in Albatross City.

# Combat
Have Emperor Marcus attack Khan Tengri.

# Magic (Teleport)
Have Wizard Merlin teleport Emperor Marcus to Peshandi.

# Healing
Have Priest heal Hero One.
Heal wounded soldiers.

# Location Control
Secure Madegi Doy.
Have General secure this city.

# Diplomacy
Ally The Golden Empire.
Enemy The Dark Kingdom.
Neutral The Neutral Traders.

# Unit Transfers
Have General give 100 soldiers to Captain.
Assign 50 sailors to Admiral Jones.
Give 500 gold to Lord Marcus.

# Character Management
Name male soldier Joe Henley.
Name female sailor Donna Majesti.

# Titles
Promote Jim Thomas to Major.
Promote me to King.
Promote Joe Smith and Ken Jones to Captain.

# Taxation
Tax for 2 weeks.
Have Captain Jones tax for 14 days.

# Prisoners
Capture Jamu Penda and Billy The Kid.
Have Joe Flint capture Mary Tarrington.
Free Wizard Yemishoka.
Release all prisoners.

# Skill Training
Study magic.
Study combat for 3 weeks.
Have Joe study sailing to level 20.
Have Master teach combat to Student.
Teach Mike magic to level 10.

# Summoning
Summon 2 dragons.
Have Wizard summon 5 skeletons and 3 zombies.

# Resource Gathering
Collect wood for 7 days.
Gather stone.
Have Engineer collect wood.

# Mining
Mine iron.
Mine gold for 10 days.
Have Miner mine silver.

# Construction
Build 1 galley.
Have Engineer build 2 galleys.
Build 5 catapults.
Have Blacksmith build 10 weapons.
Make 20 armor.

# Labour, training, unnaming
Work for 18 hours.
Have Mike Foster work for 10 weeks.
Train 20 soldiers.
Have Admiral Bill Cunningham train 40 sailors.
Have Genghis Khan train soldiers.      # every worker in his group
Unname Joe Flint.
Have Mike Felton unname Charles Dickens.

# Elite troops
Create Gordy's Killers using 250 soldiers.
Have General Wazawaza create The Wazoo Troop with 1200 soldiers.

# Investing in towns
Invest 400 gold in Ostrina'o.
Have Bill Harrington invest all of his gold in Yodrina.
Have Jane invest 75 percent of her gold in Kitesta.

# Buying passage (sea travel without a ship)
Buy passage to Kitesta.
Have Jim Thomas buy passage to Amesbok.
Have Joe Flint definitely buy passage to Kitesta.

# Preaching
Have Bishop Jake Henderson preach for 2 weeks.
Preach for 6 days.

# Recruiting independent characters (from players.yaml)
Offer Bishop Nancy Lopenda 100 gold and have her come to Pomye.
Offer 1500 to Wizard Ojibenmi and have him summon 3 dragons and report.
Have Joe Bellin offer 75 percent of his gold to Engineer Tegwi Olafson.

# Conditional orders (scope: the rest of the sentence; never nested)
If Joe Flint has at least 100 gold, then take it from him and buy 10 horses;
otherwise wait 1 day.
Go to Kitesta and if Louise Sanders has any gold then take it from her and
fly to Umadosh.
Have Primate Melissa Davies repeatedly briefly report and if she has less
than 50 religious power, then have her preach for 1 week; otherwise have her
pray for me.

# Sequencing
Wait for 2 weeks and then go to Salem.

# Groups (an order to a leader carries their whole group)
Have Julia join Marcus.            # Julia and her people join his group
Have Marcus assign Gaius to Julia. # the same move, ordered from the other end
Have Marcus unload Julia.          # set her loose without ordering her about
Have Julia come to Carthage.       # COME is GO; this also makes her a leader
Have Marcus support Hannibal for 2 weeks.

# Waiting (holds everything queued behind it)
Wait for 3 days.
Have Marcus await 2 weeks.
Have Marcus wait for Julia.        # until she reaches him
Wait until turn 12.

# Repeating (everything after it, for that character, is the loop body)
Have Bill repeatedly tax 5 times.
Have Mike repeatedly mine silver.  # no count: runs until halted

# Cancelling
Have Marcus halt.                  # drop the backlog now
Have Marcus immediately halt.      # and abandon a wait already running
Have Julia stop.                   # planned: takes effect in sequence

# Magical items (always referred to by the enchantress's name)
Conjure a ring.                          # spends all your power for that % chance
Have Merlinus conjure a wand of teleport.
Conjure an amulet of trading.            # amulets never grant magic or religion
Search for 30 days.                      # dig uninhabited ruins for a permanent find
Recharge *Madingo*.                      # give it as much power as you can spare
Charge *Ampu* to 75 power and *Wasute* by 7 power.
Absorb 10 points from *Madingo*.
Have Merlinus absorb everything from *Umiki*.
Scan Kitesta using *Anomba*.             # an orb spends its own power on distance
Have McCoy teleport Joe Flint to Kitesta using *Opistama*.
Give *Wameka* to Joe Flint.

# Communication (a message keeps its exact text, case and punctuation)
Have Joe Flint say "Not on your life!" to John May.
Tell John May "Here is the gold I promised you."
Tell everyone "John May has declared himself ruler of the world!"
Tell Madegi Doy "All are welcome here."   # a town name broadcasts to everyone in it
Have Joe Flint post "Recruiting is forbidden here.".  # notice at a secured town
Have Joe Flint post "".                   # take the notice down
Report.                                   # what can my leader see?
Query Bill Johnson and Joe Flint.
Have Jane Edwards briefly report.
Address "player@example.com"
Password "a good long password"

# Pronouns (referents carry from one sentence to the next)
Have Joe Flint give me 100 gold.   # me/I/you are always your leader
Have Mark Bolton study combat.
Have Donald Nap give him 100 gold. # him = Mark Bolton, not the agent
Recruit 5 soldiers. Assign them to me.
Charge *Ampu* to 75 power. Give it to Merlinus.
Have Bishop Linda bless herself.   # reflexives mean the agent

# Comments (ignored)
# This is a comment
Have Hero go to City.  # End-of-line comment
```

### Order Parsing Notes

- Commands are case-insensitive
- Commas, colons, semicolons are ignored
- Periods delimit sentences (important for error recovery)
- `#` starts a comment (to end of line)
- Plural 's' is optional for unit types
- Orders go on a per-character queue. With nothing in front of them they run in
  the turn you sent them; behind a wait or a repeat loop they run later.
- A repeat loop swallows the rest of that character's orders in the submission,
  so put anything you want done first *before* the `repeatedly`
- Naming a character with `have` makes them a group leader, so they stop
  following whoever they were with. That is the rules' behaviour, not a bug —
  use `join` to put them back.
- Magical items are referred to by name. The asterisks are part of the name but
  optional when typing: `*Wameka*` and `Wameka` both work.
- A wand is never used automatically. To cast with one, end the spell order with
  `with` or `using` and the wand's name.
- Pronouns resolve against what you named in earlier sentences of the same
  submission. `him`/`her` never mean your leader (use `me` or `you`) and never
  mean the character acting in that same order.
- Text in double quotes is left exactly as you typed it — case, commas and
  periods included — and pronouns inside a message are never rewritten. Put the
  sentence-ending period *after* the closing quote, as the rules' examples do.

## Web Server (beta) — humans in the browser, agents over JSON

The engine is playable online. Link-based rooms: a 5-character code plus a
4-digit PIN is all it takes to join. No accounts, no passwords — the room PIN
and per-player agent keys are the credentials.

```bash
pip install -r requirements.txt
set SOE_BETA_ACCESS_CODE=<private-invite-code>
set SOE_OPERATOR_KEY=<operator-secret>
set SOE_COOKIE_SECURE=1
python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

For the controlled beta, prefer `scripts/start_beta.ps1` (requires
`SOE_BETA_ACCESS_CODE` and `SOE_OPERATOR_KEY`) and put HTTPS termination in
front of the loopback server. Production proxy: [`deploy/Caddyfile`](deploy/Caddyfile).
Local trusted drill: `scripts/start_https.ps1` then
`.\scripts\check_https.ps1 -BetaHostname 127.0.0.2 -HttpsPort 8443`.
The archived
[`controlled_beta_runbook.md`](docs/archive/pre-agent-competition-2026-08-11/controlled_beta_runbook.md)
still describes the stop/restore sequence. Open the HTTPS host to create or join a game. The host resolves each turn
after every joined player has submitted orders, or may explicitly force an early
resolution where missing players count as empty orders. Every turn runs with a
seed derived from the room code and turn number, so results are reproducible.

Games live in `games/room_<code>/` — the CLI can still inspect and process the
same games, and rooms are tracked in `server_data/rooms.json`.

### Master dashboard

The host browser session gets a **Master dashboard** link in the room header.
It opens `/room/<code>/master`, which is host-cookie protected and shows turn
readiness, faction resources, full city authority, recent gameplay events, and
the all-visible live map. A redacted structured event stream is written to
`games/room_<code>/turn_events.jsonl` after each successful resolution so the
dashboard can explain what happened without exposing order text or credentials.
The dashboard's gameplay feed is a per-turn **timeline** with engine-phase
tags and filters, and the **auto-play** card runs every enabled bot and
resolves turn after turn in the background (turns, delay, force, wait-for-
humans options, cooperative stop). The same loop is available headless as
`workflows/bot_loop.py`.

For a small human gameplay check, run:

```bash
python scripts/gameplay_smoke.py
```

The command writes `games/gameplay_smoke/GAMEPLAY_REPORT.md`, exact orders,
player reports, final state, and the same structured event format used by the
master dashboard. It is a three-turn golden-path check, not a balance test.

### Agent API

A player key (the `agent_key` from joining) is the only credential. Send it in
the `X-Agent-Key` header. Query-string keys remain supported for compatibility,
but should not be used because URLs are commonly retained in logs and browser
history.

| Endpoint | What it does |
|---|---|
| `POST /api/rooms` `{name, slots, map}` | Create a room → `code`, `pin`, `host_key`, slots |
| `POST /api/join` `{code, pin, name}` | Claim a slot → `faction_id`, `faction_name`, `agent_key` |
| `GET /api/rooms/{code}/status` | Turn number, players, who has submitted |
| `POST /api/rooms/{code}/orders` `{orders: "..."}` | Submit orders; returns parse feedback |
| `GET /api/rooms/{code}/state` | Structured fog-of-war view (your characters, units, cities) |
| `GET /api/rooms/{code}/report?turn=N` | Your text report for a resolved turn |
| `POST /api/rooms/{code}/resolve` (host key) | Force the next turn (`force: true` skips the all-submitted check) |
| `GET /api/rooms/{code}/agents` (host key) | Bot profiles per faction slot |
| `PUT/DELETE /api/rooms/{code}/agents/{faction_id}` (host key) | Configure / remove a bot profile |
| `POST /api/rooms/{code}/agents/{faction_id}/run` (host key) | One bot decides and submits a turn |
| `POST /api/rooms/{code}/agents/run-all` (host key) | Every enabled bot plays its turn |
| `GET /api/rooms/{code}/map?format=json\|svg\|png&turn=N` | Fog-of-war board for agents: json (coordinates + observed flags), svg, or png for vision models; `turn` rewinds to a resolved turn |

Example agent loop:

```python
import requests

room = requests.post("http://localhost:8000/api/rooms",
                     json={"name": "Agent War", "slots": 2}).json()
me = requests.post("http://localhost:8000/api/join",
                   json={"code": room["code"], "pin": room["pin"], "name": "alpha-bot"}).json()
key = me["agent_key"]

while True:
    state = requests.get(f"http://localhost:8000/api/rooms/{room['code']}/state",
                         headers={"X-Agent-Key": key}).json()
    # decide orders from state...
    resp = requests.post(f"http://localhost:8000/api/rooms/{room['code']}/orders",
                         headers={"X-Agent-Key": key},
                         json={"orders": "Recruit 20 soldiers in Madegi Doy."})
    report = requests.get(f"http://localhost:8000/api/rooms/{room['code']}/report",
                          headers={"X-Agent-Key": key}).json()["report"]
```

Note: a room currently resolves only when the host presses the button (or an
agent calls `/resolve`). Scheduled auto-resolution is a natural next step.

### Managed bots (war-room)

The host can assign **AI bot players** to faction seats from the setup page
(`/room/<code>/setup`, host session) or the agents API. A bot profile carries
a model, a persona, and a temperature; enabling one on an empty seat claims it.
The host can then run one bot (`POST .../agents/{faction_id}/run`) or all
enabled bots (`.../agents/run-all`): each bot reads its fog-of-war state and
latest report, asks the LLM for orders, and submits them through the normal
pipeline — the same validation, the same readiness tracking.

The LLM is configured by environment, never by the UI:

```bash
set SOE_LLM_BASE=https://openrouter.ai/api/v1   # default; any OpenAI-compatible endpoint works
set SOE_LLM_KEY=<your key>                      # bots refuse to run without it
set SOE_LLM_MODEL=openai/gpt-4o-mini            # default model
```

The strategist reply convention is: reasoning first, then a `--- ORDERS ---`
marker line, then one order per line. Orders are submitted verbatim from the
marker onward. Set `SOE_BOT_VISION=1` and use a vision-capable model (e.g.
`openai/gpt-4o-mini`) to let the strategist also see a rendered PNG of its
fog-of-war map each turn. See the current product direction in
[`docs/AGENT_COMPETITION.md`](docs/AGENT_COMPETITION.md); the implementation
roadmap is archived under `docs/archive/pre-agent-competition-2026-08-11/`.

For beta readiness, known constraints, and the tester protocol, see
the archived
[`beta_readiness_2026-08.md`](docs/archive/pre-agent-competition-2026-08-11/beta_readiness_2026-08.md).

## CLI Commands

### `soe init-game <game_id>`

Initialize a new game.

**Options:**
- `--map PATH` - Path to map JSON file (optional, creates sample if omitted)
- `--players PATH` - Path to players YAML file (optional, creates 2 default factions if omitted)

**Example:**
```bash
soe init-game campaign1 --map my_map.json --players my_players.yaml
```

### `soe show-state <game_id>`

Display current game state summary.

**Example:**
```bash
soe show-state campaign1
```

### `soe process-turn <game_id> --turn <N> --seed <SEED>`

Process a game turn.

**Options:**
- `--turn N` or `-t N` - Turn number to process (required)
- `--seed SEED` or `-s SEED` - Random seed for determinism (required)

**Example:**
```bash
soe process-turn campaign1 --turn 5 --seed 12345
```

### `soe example-setup`

Create example maps, players, and order files for testing.

**Example:**
```bash
soe example-setup
```

## Project Structure

```
SOE/
├── soe/         # Core engine package
│   ├── __init__.py
│   ├── models.py          # Domain models (City, Character, etc.)
│   ├── config.py          # Game balance parameters
│   ├── orders.py          # Order class definitions
│   ├── parser.py          # English-like order parser
│   ├── order_queue.py     # Per-character order queue (AWAIT/REPEAT/HALT/STOP)
│   ├── groups.py          # Groups and group leaders (JOIN/ASSIGN/UNLOAD)
│   ├── fog.py             # Fog of war (position, LURK odds, sightings)
│   ├── items.py           # Magical items (amulet/crystal/orb/ring/wand)
│   ├── pronouns.py        # me/him/her/it/them resolution before dispatch
│   ├── engine.py          # Turn processing engine
│   ├── reporting.py       # Report generation
│   ├── storage.py         # Save/load game state
│   └── map_loader.py      # Map file handling
├── cli.py                 # CLI entrypoint
├── tests/                 # Test suite
│   ├── test_parser.py
│   ├── test_engine_basic.py
│   ├── test_upkeep.py
│   ├── test_regressions.py  # Pins the defects fixed in the v0.7.1 audit
│   ├── test_gap_closures.py # Pins the design debt closed in v0.7.2
│   ├── test_v08.py          # Cheap-gap commands and per-character gold
│   ├── test_v09.py          # The persistent order queue
│   ├── test_v10_groups.py   # Groups and group leaders
│   ├── test_v10_fog.py      # Fog of war, PROBE, SEARCH, SCAN
│   ├── test_v10_items.py    # Magical items, CONJURE/CHARGE/ABSORB, SCAN
│   ├── test_v10_pronouns.py # Pronoun resolution
│   └── test_v10_communication.py # SAY/TELL, POST, REPORT/QUERY, ADDRESS
├── maps/                  # Map files
│   └── sample_map.json
├── examples/              # Example data
│   ├── players.yaml
│   ├── orders_player1_turn1.txt
│   └── orders_player2_turn1.txt
├── games/                 # Runtime game directories
│   └── <game_id>/
│       ├── state.json
│       ├── orders/
│       │   └── player_*_turn*.txt
│       └── reports/
│           └── player_*_turn*.txt
├── docs/
│   ├── alpha_scope.md     # Detailed alpha scope document
│   └── audit_2025-11.md   # Consolidation, defect audit, design debt
├── MECHANICS.md           # Rules reference, derived from the engine
├── pyproject.toml         # Package configuration
├── requirements.txt       # Dependencies
└── README.md              # This file
```

## Game Mechanics (Alpha)

### Map & Cities

Cities have **population bands** that determine:
- **Income per turn**: <1k=10g, 1k-9k=50g, 10k-99k=200g, 100k+=500g
- **Recruit cap per turn**: <1k=10, 1k-9k=50, 10k-99k=200, 100k+=500

A map may also give a city an exact `population` (as in the original SOE map
index); it is then used for INVEST growth, taxes and wages, and the band is
derived from it when none is given. Cities can carry `grid_ref` (e.g. "A6"),
`is_magic_free` (drains all magic power, per the rules) and `is_ruin`.

Income is **not** paid straight into the treasury. It accumulates in a per-city
tax pool (capped at four turns' worth) and reaches your treasury only when a
character with soldiers present issues a `TAX` order. Upkeep, by contrast, is
deducted from the treasury every turn — so an empire that never taxes goes broke.

Roads have **quality** affecting movement cost:
- Excellent: 0.5x cost
- Good: 1.0x cost
- Fair: 1.5x cost
- Poor: 2.0x cost
- Sea: 1.0x (requires ship, sea lanes only)

A road with `distance_miles` (from the gamemaster's map) costs quality-multiplier
x miles/10 movement points — 100 miles on a good road is one turn — and
mileage also prices TELEPORT and orb SCAN (one power per ten miles). Roads
without mileages keep the quality-only cost.

Land and sea form **separate networks**: a marching character cannot cross a sea
lane, and a ship cannot sail up a road. Every hop costs at least one movement
point regardless of road quality.

### Characters

- **Combat skill** (0-100): Multiplies faction combat power by (1 + skill/100)
- **Magic skill** (0-100): Max magic power, used for teleport
- **Movement points**: 10 per turn, reset each turn

### Units

- **Soldiers**: 1 attack, 1 defense
- **Sailors**: Required for ships (10 min crew + 40 rowers for galley)
- **Workers**: No combat value

### Ships

- **Galley**: Costs 1000g, carries 550 encumbrance, built at ports

### Combat (Simplified)

1. Calculate power: `sum(unit_attack) * (1 + best_combat_skill/100)`
2. Add randomness (0.8x to 1.2x)
3. Higher power wins
4. Casualties: Winner 10%, Loser 30%

### Determinism

All randomness uses a seeded RNG. Same game state + orders + seed = identical outcome. This ensures:
- Reproducible testing
- Fair adjudication
- Debugging capability

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Test Coverage

```bash
pytest tests/ --cov=soe --cov-report=html
```

### Adding New Order Types

1. Define order class in `soe/orders.py`
2. Add parser in `soe/parser.py`
3. Add processing logic in `soe/engine.py` (appropriate phase)
4. Update `soe/reporting.py` for event logging
5. Write tests in `tests/`

## Mapping to Original Rules

This alpha implements a **simplified subset** of the full design:

| Feature | Rules Section | Alpha Status | Notes |
|---------|---------------|--------------|-------|
| Movement (land) | GO/MOVE/TRAVEL | ✅ Implemented | Simplified: no encumbrance, horses |
| Movement (sea) | SAIL | ✅ Implemented | Sea lanes require a ship |
| Recruiting | RECRUIT | ✅ Implemented | Simplified: instant, fixed caps |
| Combat | ATTACK | ✅ Implemented | Simplified: no retreat logic, morale |
| Magic | TELEPORT/FLY/SUMMON | ✅ Implemented | Flat costs; no encumbrance |
| Income | TAX | ✅ Implemented | Per-city pools collected by a TAX order |
| Ships | BUY | ✅ Implemented | Galleys only |
| Skills | SKILLS | ✅ Partial | Combat, magic, religion, trading, sailing |
| Diplomacy | ALLY/ENEMY | ✅ Partial | Decides combat sides, not movement rights |
| Religion | PRAY/BLESS/CURSE | ✅ Implemented | Skill-based rolls on religious power |
| Magical items | AMULET/CRYSTAL/ORB/RING/WAND | ✅ Implemented | No weight or encumbrance |
| Equipment | Armor/Weapons | ✅ Partial | BUILD output affects combat |
| Construction | BUILD | ✅ Implemented | No partial progress if interrupted |
| Resources | MINE/COLLECT | ✅ Implemented | Yields scale with city richness |
| Communication | SAY/TELL/POST | ✅ Implemented | QUERY not yet more immediate than REPORT |
| Elite troops | CREATE | ✅ Implemented | Train ~1 level/5 weeks, salary by size × level |
| Conditional orders | IF | ✅ Implemented | Evaluated at turn start; never nested |
| Sequencing | THEN | ✅ Implemented | Chains clauses in order |
| Hiring | OFFER | ✅ Implemented | Deterministic acceptance; NPCs from players.yaml |

[`MECHANICS.md`](MECHANICS.md) is the authoritative and current
breakdown; the archived `docs/archive/pre-agent-competition-2026-08-11/alpha_scope.md`
records the original alpha simplifications.

## Design Philosophy

1. **Engine-first**: the implementation is the authoritative source
2. **Simplify, don't break**: Alpha simplifies but maintains core mechanics
3. **Clean architecture**: Easy to extend toward full implementation
4. **Test-driven**: Core functionality has test coverage
5. **Deterministic**: No hidden state, no non-reproducible randomness
6. **File-based**: Human-readable state, easy to inspect/debug

## Where we are

**All 89 command verbs** are now recognised, and 8 of the 9
order-language features. See [`MECHANICS.md`](MECHANICS.md) for the
full breakdown, including what each new command still simplifies.

The rules describe an **asynchronous** game where orders queue and execute as
game time passes. v0.9 closed most of that gap: orders live on a persistent
per-character queue (`soe/order_queue.py`) that survives save/load and
carries work between turns. What remains is granularity — the queue advances one
pass per turn, so it measures time in weeks where the rules measure it in hours.

Engine-internal design debt is clear as of v0.7.2. What remains is rules
fidelity, not cleanup.

## Future Roadmap

### v0.8 — Close the cheap gaps ✅

- Prisoner operations: `ENSLAVE`, `KILL`/`EXECUTE`, `INTERROGATE`
- Status and stealth: `COMBATANT`/`NONCOM`, `LURK`/`UNLURK`
- Inventory: `GET`/`OBTAIN`/`TAKE`, `TRANSFER`, `UNLOAD`
- Finance: `PAY`, `HIRE` (synonym of `RECRUIT`), `BORROW`/`REPAY`
- Per-character gold purses (legacy treasury migrates to the leader on load)

### v0.9 — The order queue ✅

Shipped in this release:

- Persistent per-character order queue, saved and reloaded with the game state
- `AWAIT`/`WAIT FOR` executes: a timed wait, or a wait for another character to
  arrive, with the duration acting as the deadline it gives up on
- `REPEAT`/`repeatedly` executes: the loop body runs one pass per turn, for a
  given count or until halted
- `HALT` and `STOP`, and `immediately` as their modifier
- Queued orders are validated when they execute, not when they were written

Deliberately still open: sub-turn timing (a wait of one hour and a wait of one
day both cost a turn), `until <date>` as a loop terminator, `THEN` sequencing,
and `immediately` as a general interrupt.

### v1.0 — Rules fidelity

**Groups and group leaders ✅** — shipped: `JOIN`, `COME`, `SUPPORT`, a real
`UNLOAD`, group travel, unit ownership, and the `HAVE`-promotes-to-leader rule.

**Fog of war ✅** — position bands, end-of-turn sightings, real `LURK` odds,
`PROBE`, `SEARCH`/`EXPLORE`.

**Pronouns ✅** — shipped: `me`/`I`/`you`, `him`/`her`, `it`, `them` and the
reflexives, resolved before verb dispatch with referents carrying between the
sentences of a submission. Each pronoun binds to the person or thing most
recently named *before it*, so a sentence can use the same pronoun twice for
two different people.

**And-chained commands ✅** — one sentence can carry several orders:
`Assign 20 soldiers and 23 horses to Bill Jenkins, and have him go to Riverton
and attack Mike May` is three commands. `and` also joins items inside a
command, so a clause only breaks where the command so far is complete and the
tail starts a new one. The HAVE form's actor stays on the clauses that follow
it (`have him go to Riverton and tax for 3 weeks, and go to Ennistown and
tax`), and a counted continuation inherits the previous verb (`give 50 gold to
Nancy Myers and 20 horses to Bill Fenton`, `recruit 5 soldiers and 3 workers`).
Mass resources move by GIVE and TAKE (`Give 50 armor to Thomas Ames`, `Take 10
copper and 20 silver from Bill Hawthorne`), and a bare `give stone to X` after
a `gather` hands over whatever was collected. `PURCHASE` now parses as a
synonym of `BUY` per the rules.

**Communication ✅** — shipped: `SAY`/`TELL` to a person, a town or everyone,
`POST` at the gates of a secured town, `REPORT`/`QUERY` with the `briefly`
form, and `ADDRESS`/`PASSWORD`. Quoted message bodies keep their exact text.

**Magical items ✅** — shipped: all five kinds from the rules (amulet, crystal,
orb, ring, wand), `CONJURE`, `CHARGE`/`RECHARGE`, `ABSORB`, a real `SCAN` that
spends orb power, ruins that yield permanent items instead of gold stubs, and
magic-free zones. Items are named in the enchantress's `*Starred*` style and
given by name: `Give *Wameka* to Joe Flint`.

Still ahead, in no fixed order:

- Sub-turn game time, so a wait can cost hours rather than a whole turn, and
  `UNTIL <date>` and interrupted-BUILD accounting become possible
- Encumbrance and item weight, so `FLY`/`TELEPORT`/`BUY PASSAGE` cost what is
  carried and IF encumbrance checks become real
- Retreat and morale in combat
- Group-level possession of ships, resources and gold, and combat resolved
  group by group rather than by faction total
- Retire or justify the three non-rules verbs (`TRADE`, `SCRY`, `RESURRECT`)

## Contributing

This is an alpha implementation. Contributions welcome:

1. Bug fixes
2. Test coverage improvements
3. Documentation enhancements
4. Feature implementations from the archived alpha scope

## License

Engine implementation: [Specify license]

The mechanics this engine implements were inspired by an earlier
play-by-email design. Game systems are not covered by copyright, but that
project's rules text, map and title are, so the engine's own rules reference
([`MECHANICS.md`](MECHANICS.md)) is written from the implementation rather
than from any source document, and the world map is being replaced by a
seeded generator. See the archived
[`ip_cleanroom.md`](docs/archive/pre-agent-competition-2026-08-11/ip_cleanroom.md).

## Acknowledgments

- **Far Horizons**: Architectural inspiration for PBEM engine design

---

**Built with Python 3.11+ | Typer | pytest**

For the current product direction, see
[`docs/AGENT_COMPETITION.md`](docs/AGENT_COMPETITION.md). Historical implementation
notes are under `docs/archive/pre-agent-competition-2026-08-11/`.
