# Spoils of Empire PBEM Engine (Alpha)

A deterministic play-by-email (PBEM) game engine for the fantasy strategy game **"Spoils of Empire"** by Rick Morneau.

## Overview

This is an alpha implementation of a turn-based engine that processes English-like orders and generates per-player reports. The engine is designed to be:

- **Deterministic**: Same inputs + same seed = identical outputs
- **File-based**: No databases, pure JSON/YAML persistence
- **Modular**: Clean separation of parsing, game logic, and reporting
- **Extensible**: Easy to add deferred features from the full rules

> **v1.0.0b — fog of war.** Characters stand *inside*, *outside*, or *near* a
> city; end-of-turn sightings only report people your side can actually notice.
> `LURK` finally changes those odds (×¼). `PROBE`, `SEARCH`/`EXPLORE` ship;
> `SCAN` parses but waits on magical orbs. Groups (v1.0.0a) still travel as a
> party and arrive at the same position band. Communication, magical items,
> `IF`, and sub-turn time remain. See [`docs/rules_gap.md`](docs/rules_gap.md).

## Features (Alpha v1.0.0b)

### Implemented

✅ **World & Map**
- Cities with population bands (<10k, 10k-99k, 100k-999k, 1M+)
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
- Conditional orders (`IF`) and `THEN` sequencing
- Sub-turn game time — the queue's smallest unit is one weekly turn
- Retreat and morale in combat
- Encumbrance and item weight
- Group-level possession of ships, resources and gold
- Resource depletion (accumulation and its cap are in; depletion is not)
- 9 of the 89 command verbs in `rules.md`

[`docs/rules_gap.md`](docs/rules_gap.md) has the command-by-command breakdown
and [`docs/alpha_scope.md`](docs/alpha_scope.md) records what the alpha
deliberately left out.

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
├── spoils_engine/         # Core engine package
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
│   ├── rules_gap.md       # Coverage of rules.md mechanics
│   └── audit_2025-11.md   # Consolidation, defect audit, design debt
├── rules.md               # Official game rules (authoritative)
├── pyproject.toml         # Package configuration
├── requirements.txt       # Dependencies
└── README.md              # This file
```

## Game Mechanics (Alpha)

### Map & Cities

Cities have **population bands** that determine:
- **Income per turn**: <10k=10g, 10k-99k=50g, 100k-999k=200g, 1M+=500g
- **Recruit cap per turn**: <10k=10, 10k-99k=50, 100k-999k=200, 1M+=500

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
pytest tests/ --cov=spoils_engine --cov-report=html
```

### Adding New Order Types

1. Define order class in `spoils_engine/orders.py`
2. Add parser in `spoils_engine/parser.py`
3. Add processing logic in `spoils_engine/engine.py` (appropriate phase)
4. Update `spoils_engine/reporting.py` for event logging
5. Write tests in `tests/`

## Mapping to Original Rules

This alpha implements a **simplified subset** of the official `rules.md`:

| Feature | Rules Section | Alpha Status | Notes |
|---------|---------------|--------------|-------|
| Movement (land) | GO/MOVE/TRAVEL | ✅ Implemented | Simplified: no encumbrance, horses |
| Movement (sea) | SAIL | ✅ Implemented | Sea lanes require a ship |
| Recruiting | RECRUIT | ✅ Implemented | Simplified: instant, fixed caps |
| Combat | ATTACK | ✅ Implemented | Simplified: no retreat logic, morale |
| Magic | TELEPORT/FLY/SUMMON | ✅ Implemented | Flat costs; no encumbrance |
| Income | TAX | ✅ Implemented | Per-city pools collected by a TAX order |
| Ships | BUY | ✅ Implemented | Galleys only |
| Skills | SKILLS | ✅ Partial | Combat, magic, religion, trading |
| Diplomacy | ALLY/ENEMY | ✅ Partial | Decides combat sides, not movement rights |
| Religion | PRAY/BLESS/CURSE | ✅ Implemented | Skill-based rolls on religious power |
| Magical items | AMULET/CRYSTAL/ORB/RING/WAND | ✅ Implemented | No weight or encumbrance |
| Equipment | Armor/Weapons | ✅ Partial | BUILD output affects combat |
| Construction | BUILD | ✅ Implemented | No partial progress if interrupted |
| Resources | MINE/COLLECT | ✅ Implemented | Yields scale with city richness |
| Communication | SAY/TELL/POST | ✅ Implemented | QUERY not yet more immediate than REPORT |
| Elite troops | CREATE | ⏸️ Deferred | |

[`docs/rules_gap.md`](docs/rules_gap.md) is the authoritative and current
breakdown; `docs/alpha_scope.md` records the original alpha simplifications.

## Design Philosophy

1. **Rules-first**: `rules.md` is the authoritative source
2. **Simplify, don't break**: Alpha simplifies but maintains core mechanics
3. **Clean architecture**: Easy to extend toward full implementation
4. **Test-driven**: Core functionality has test coverage
5. **Deterministic**: No hidden state, no non-reproducible randomness
6. **File-based**: Human-readable state, easy to inspect/debug

## Where we are

**81 of 89 command verbs (91%)** from `rules.md` are recognised, and 6 of its 9
order-language features. See [`docs/rules_gap.md`](docs/rules_gap.md) for the
full breakdown, including which commands are missing and why.

The rules describe an **asynchronous** game where orders queue and execute as
game time passes. v0.9 closes most of that gap: orders live on a persistent
per-character queue (`spoils_engine/order_queue.py`) that survives save/load and
carries work between turns. What remains is granularity — the queue advances one
pass per turn, so it measures time in weeks where the rules measure it in hours.

Engine-internal design debt is clear as of v0.7.2. What remains is rules
coverage, not cleanup.

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

- `CREATE` elite troop units — continuously training named units that cannot
  TAX, SECURE or work. (Previously listed here under magical items by mistake;
  the rules put it with recruitment.)
- `IF` conditional orders (the queue they needed now exists)
- `THEN` sequencing, which would let a chain pause between its clauses — the
  rules write `Charge Ampu to 75 power and give it to Merlinus`, which one
  sentence can now carry (though not yet sequence on its own)
- Encumbrance and item weight, so `FLY` and `TELEPORT` cost what is carried
- Sub-turn game time, so a wait can cost hours rather than a whole turn
- Group-level possession of ships, resources and gold, and combat resolved
  group by group rather than by faction total
- Retire or justify the three remaining non-rules verbs (`TRADE`, `SCRY`,
  `RESURRECT`)

## Contributing

This is an alpha implementation. Contributions welcome:

1. Bug fixes
2. Test coverage improvements
3. Documentation enhancements
4. Feature implementations from `docs/alpha_scope.md`

## License

Based on "Spoils of Empire" rules by Rick Morneau.
Engine implementation: [Specify license]

## Acknowledgments

- **Rick Morneau**: Original Spoils of Empire game design and rules
- **Far Horizons**: Architectural inspiration for PBEM engine design

---

**Built with Python 3.11+ | Typer | pytest**

For questions and issues, see `docs/alpha_scope.md` for detailed implementation notes.
