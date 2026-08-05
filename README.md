# Spoils of Empire PBEM Engine (Alpha)

A deterministic play-by-email (PBEM) game engine for the fantasy strategy game **"Spoils of Empire"** by Rick Morneau.

## Overview

This is an alpha implementation of a turn-based engine that processes English-like orders and generates per-player reports. The engine is designed to be:

- **Deterministic**: Same inputs + same seed = identical outputs
- **File-based**: No databases, pure JSON/YAML persistence
- **Modular**: Clean separation of parsing, game logic, and reporting
- **Extensible**: Easy to add deferred features from the full rules

> **v0.8.0 — cheap gaps closed.** Prisoner ops, status/stealth, inventory
> transfers, finance (`PAY`/`HIRE`/`BORROW`/`REPAY`), and per-character gold
> land on top of the v0.7.2 design-debt cleanup. The order queue (`AWAIT`/
> `REPEAT` execution) remains v0.9. See [`docs/rules_gap.md`](docs/rules_gap.md).

## Features (Alpha v0.8.0)

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

✅ **Turn Processing**
- Phase 1: Validation
- Phase 2: Movement (land), then sailing (sea)
- Phase 3: Recruit & buy
- Phase 4: Magic (teleport, fly, heal), summoning, religion
- Phase 5: Combat (with character casualties), then capture
- Phase 6: Income & upkeep (wage debt + loan interest)
- Phase 7: Location control, diplomacy, taxation, trade, gathering, mining,
  construction, transfers, get/unload, naming, promotion, prisoner ops,
  status flags, finance, study & teach
- Phase 8: Cleanup — prisoner escape and natural healing

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
- Conditional orders (`IF`) and the rest of the order language — these wait on
  the cross-turn order queue
- Retreat and morale in combat
- Per-character gold (gold is currently held per faction)
- Fog of war
- Resource depletion (accumulation and its cap are in; depletion is not)
- 48 of the 89 command verbs in `rules.md`

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
│   └── test_v08.py          # Cheap-gap commands and per-character gold
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
| Movement (sea) | SAIL | ⏸️ Deferred | Ships exist but sailing not yet impl. |
| Recruiting | RECRUIT | ✅ Implemented | Simplified: instant, fixed caps |
| Combat | ATTACK | ✅ Implemented | Simplified: no retreat logic, morale |
| Magic | TELEPORT | ✅ Basic | Only teleport, no summon/fly |
| Income | TAX | ✅ Simplified | Auto per-turn, not TAX command |
| Ships | BUY | ✅ Implemented | Galleys only |
| Skills | SKILLS | ✅ Partial | Combat, magic only |
| Diplomacy | ALLY/ENEMY | ⏸️ Deferred | |
| Religion | PRAY/BLESS | ⏸️ Deferred | |
| Items | Armor/Weapons | ⏸️ Deferred | |
| Construction | BUILD | ⏸️ Deferred | |
| Resources | MINE/COLLECT | ⏸️ Deferred | |

See `docs/alpha_scope.md` for comprehensive mapping.

## Design Philosophy

1. **Rules-first**: `rules.md` is the authoritative source
2. **Simplify, don't break**: Alpha simplifies but maintains core mechanics
3. **Clean architecture**: Easy to extend toward full implementation
4. **Test-driven**: Core functionality has test coverage
5. **Deterministic**: No hidden state, no non-reproducible randomness
6. **File-based**: Human-readable state, easy to inspect/debug

## Where we are

**41 of 89 command verbs (46%)** from `rules.md` are recognised, and 2 of its 9
order-language features. See [`docs/rules_gap.md`](docs/rules_gap.md) for the
full breakdown, including which commands are missing and why.

The largest divergence is structural: the rules describe an **asynchronous**
game where orders queue and execute as game time passes, while the engine runs
fixed synchronous turns. That gap is why `AWAIT` and `REPEAT` are accepted but
report that they will not run until v0.9 brings the queue.

Engine-internal design debt is clear as of v0.7.2. What remains is rules
coverage, not cleanup.

## Future Roadmap

### v0.8 — Close the cheap gaps ✅

Shipped in this release:

- Prisoner operations: `ENSLAVE`, `KILL`/`EXECUTE`, `INTERROGATE`
- Status and stealth: `COMBATANT`/`NONCOM`, `LURK`/`UNLURK`
- Inventory: `GET`/`OBTAIN`/`TAKE`, `TRANSFER`, `UNLOAD`
- Finance: `PAY`, `HIRE` (synonym of `RECRUIT`), `BORROW`/`REPAY`
- Per-character gold purses (legacy treasury migrates to the leader on load)

### v0.9 — The order queue

The structural change everything else waits on:

- Persistent order queue surviving across turns, with game-time costs per order
- `HALT`/`STOP` to cancel orders in progress
- Make `AWAIT` and `REPEAT` actually execute
- `UNTIL`, `REPEATEDLY`, `IMMEDIATELY` adverbs
- `THEN` sequencing and `and`-chained commands

### v1.0 — Rules fidelity

- `IF` conditional orders (needs the queue)
- Communication: `SAY`/`TELL`, `POST`, `ADDRESS`, `REPORT`, `QUERY`
- Exploration and intel: `EXPLORE`, `SCAN`, `SEARCH`, `PROBE`
- Magical items: `CONJURE`, `CREATE`, `CHARGE`/`RECHARGE`, `ABSORB`
- Groups and group leaders: `JOIN`, `COME`, `SUPPORT`
- Fog of war
- Retire or justify the five non-rules verbs (`TRADE`, `SCRY`, `RESURRECT`,
  `REPEAT`, `WAIT`)

### Also outstanding

**Fog of war** remains a v1.0 feature. Per-character gold shipped with v0.8.

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
