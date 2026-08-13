# SOE PBEM Engine - Alpha Scope

## Overview

This document defines the scope of the **alpha version** of the SOE  PBEM engine. The alpha will implement a coherent, simplified-but-faithful subset of the full game mechanics described in `rules.md`, focusing on core gameplay loops while deferring complex features for future releases.

## Reference: Core SoE Concepts from rules.md

Based on the official rules, SOE includes:

### World & Geography
- **Cities/Locations**: Named locations with populations, can be secured, taxed, and serve as recruitment centers
- **Roads & Sea Lanes**: Pre-defined travel routes with quality ratings (excellent, good, fair, poor)
- **Terrain**: Various terrain types (forest, plains, desert, mountains, rivers, ports)
- **Population Bands**: Cities have different population sizes affecting recruitment caps and tax revenue

### Characters & Entities
- **Named Characters**: Heroes/leaders with multiple skills (0-100), complex abilities, unique names
- **Unnamed Characters**: Basic units - soldiers (combat 1), sailors (sailing 1), workers (no skills)
- **Skills**: Combat, Sailing, Magic, Religion, Engineering, Mining, Trading
- **Health**: 0-100, affects skill effectiveness, auto-recovers 1 point/day

### Core Mechanics
- **Movement**:
  - GO/MOVE/TRAVEL for land (affected by road quality, horses, encumbrance)
  - SAIL for sea (requires galleys, sailors, rowers)
  - FLY for air (magic)
- **Combat**: ATTACK command with odds calculation, morale, retreats, casualties
- **Recruiting**: RECRUIT soldiers/sailors/workers (availability based on population)
- **Economy**:
  - Taxation: ~1 gold per 4 residents/year, max 30-day accumulation
  - Salaries: Unnamed = 1g/2 months, Workers = 0.25g/2 months, Named = 5g + effective_level
  - Buying/Selling: Items, ships, equipment
- **Magic System**: Teleport, Summon creatures, Fly, Conjure items (power = magic skill level, 1 pt/day regen)
- **Religion System**: Pray for miracles (probabilistic), Bless/Curse, Preach for donations
- **Magical Items**: Amulets, Crystals, Orbs, Rings, Wands

### Advanced Features
- **Diplomacy**: Ally/Enemy/Neutral status, Support in combat
- **Location Control**: SECURE command (requires soldiers, can deny entry)
- **Item Management**: Armor, weapons, horses, wagons, siege equipment
- **Resource Gathering**: Mining (iron, copper, silver, gold, gems), Collecting (wood, stone)
- **Construction**: BUILD command (galleys, catapults, battering rams, etc.)
- **Advanced Orders**: Conditional "IF" statements, AWAIT, complex sequencing

## Alpha Implementation Scope

### ✅ IMPLEMENTED in Alpha

#### 1. World & Map System
- **Cities**:
  - Unique ID, name, population band (<1k, 1k-9k, 10k-99k, 100k+)
  - Terrain flags (plains, forest, mountains, river, coastal)
  - Port status (can build/dock ships)
  - Region grouping (islands, continents)
- **Roads & Sea Lanes**:
  - Directed connections between cities
  - Quality: excellent, good, fair, poor, sea
  - Movement cost calculation
- **JSON Map Format**: Simple, editable map files

#### 2. Factions & Characters
- **Factions**: ID, name, controlled cities, treasury
- **Named Characters**:
  - ID, name, faction, location, movement points
  - Basic skills: combat, magic (0-100)
  - Can act as leaders for groups
- **Unit Stacks**: Groups of unnamed soldiers/sailors
  - Type, count, location, attack/defense values
- **Ships**: Galleys with capacity, location, owner

#### 3. Core Orders
- **MoveOrder**: Character moves to destination city
- **RecruitOrder**: Hire soldiers/sailors/workers in a city
- **BuyShipOrder**: Purchase galleys at ports
- **AttackOrder**: Simple combat between factions
- **TeleportOrder**: Magic users teleport characters (basic)

#### 4. Order Parser (Rule-Based)
- Parse English-like commands from text files
- Pattern matching for:
  - "Have <char> go to <city>"
  - "Have <char> recruit <num> <type> in <city>"
  - "Have <char> buy <num> galley in <city>"
  - "Have <char> attack <target>"
  - "Have <char> teleport <target> to <city>"
- Entity resolution (character names → IDs, city names → IDs)
- Error handling and warnings

#### 5. Turn Processing Engine
**Phase 1: Validation**
- Verify actor exists and belongs to player
- Check cities/targets exist
- Validate basic preconditions (e.g., only ports can build ships)

**Phase 2: Movement**
- Process MoveOrder
- Calculate movement cost based on roads
- Update character locations
- Simple pathfinding (shortest path)

**Phase 3: Recruit & Buy**
- Process RecruitOrder: enforce population-based caps, deduct gold
- Process BuyShipOrder: verify port, deduct gold, create ships

**Phase 4: Magic (Simplified)**
- Process TeleportOrder: deduct magic power, move instantly

**Phase 5: Combat (Simplified)**
- Identify conflicts at each city
- Calculate total attack/defense per side
- Apply simple deterministic formula with RNG
- Apply casualties, remove destroyed units

**Phase 6: Income & Upkeep**
- Award tax income based on controlled cities (simplified: fixed per pop band)
- Deduct unit/ship upkeep
- Update treasuries

#### 6. Deterministic RNG
- All random operations use `random.Random(seed)`
- Same seed + same inputs = same outputs
- Seed passed to `run_turn()` function

#### 7. Reporting System
- Per-player text reports showing:
  - Turn number, treasury, controlled cities
  - Character movements and actions
  - Combat results
  - Recruitment/purchases
  - Warnings for invalid/failed orders

#### 8. Storage System
- Save/Load GameState to JSON
- Game directory structure: `games/<game_id>/state.json`
- Persistent campaigns

#### 9. CLI (Typer-based)
- `soe init-game <game_id>`: Initialize new game
- `soe show-state <game_id>`: Display current game state
- `soe process-turn <game_id> --turn N --seed SEED`: Process turn
- `soe example-setup`: Create demo game

#### 10. Configuration
- Costs: recruitment, ships, items
- Income rates by population band
- Recruit caps by population band
- Combat formulas
- Movement costs by road quality

### ⏸️ DEFERRED (Not in Alpha)

#### 1. Advanced Character Features
- Health system (always 100 in alpha)
- Death and resurrection
- Character experience/skill progression
- Multiple skills beyond combat/magic
- Named character creation beyond initial setup
- Elite troops (summoned creatures treated as special units if implemented)

#### 2. Complex Magic
- Full spell system (Summon, Fly, Conjure, Scry)
- Magical items (amulets, crystals, orbs, rings, wands)
- Magic-free zones
- Power regeneration (simplified to instant in alpha)
- Charging/absorbing items

#### 3. Religion System
- Religion skill
- Pray, Bless, Curse, Preach commands
- Probabilistic miracles

#### 4. Diplomacy & Politics
- Ally/Enemy/Neutral declarations
- Support in combat
- Player IDs and public figures
- Messaging (SAY/TELL commands)

#### 5. Location Control
- SECURE command
- Fortifications
- Access control to cities
- Inside/outside/near positioning

#### 6. Economy Deep Dive
- TAX command (detailed collection mechanics)
- Trading skill and discounts
- BUY/SELL with variable prices
- INVEST command (city growth)
- Lending/borrowing

#### 7. Resource Management
- Mining (MINE command)
- Collecting (wood, stone)
- Item production (BUILD for weapons, armor, siege equipment)
- Encumbrance system (simplified in alpha)
- Horses, wagons, and transport

#### 8. Advanced Orders
- "IF" conditionals
- AWAIT command
- Queued orders and order cancellation
- HALT/STOP with immediate execution
- REPEATEDLY adverb
- Complex order chaining

#### 9. Advanced Combat
- Detailed combat modifiers (armor, weapons, rings)
- Siege equipment (catapults, battering rams, siege towers)
- Naval combat
- Combatant/Noncom status
- Capture and enslavement
- Desertion mechanics
- Attack modifiers (cravenly, cautiously, bravely, recklessly, suicidally)

#### 10. Other Commands
- NAME, PROMOTE (character management)
- ASSIGN/GIVE (complex transfers)
- JOIN (group management)
- TEACH/STUDY (skill training)
- EXPLORE/SEARCH (ruins, magic items)
- OFFER/HIRE (recruiting skilled NPCs)
- PASSWORD (access control)
- PROBE (spying)
- EXECUTE/KILL
- ENSLAVE/FREE

## Alpha Simplifications

### Movement
- **Simplified**: Fixed movement costs, no encumbrance details, no horses/wagons
- **Deferred**: Complex encumbrance, horse speed bonuses, wagon capacity

### Combat
- **Simplified**: Basic attack/defense calculation, simple casualties, no retreat logic
- **Formula**: `combat_power = sum(unit_attack) * (1 + leader_combat_skill/100)`
- **Deferred**: Retreat conditions, morale, armor/weapons bonuses, detailed combat reporting

### Economy
- **Simplified**: Fixed income per pop band, fixed recruitment costs, no trading skill
- **Income**: <1k=10g/turn, 1k-9k=50g/turn, 10k-99k=200g/turn, 100k+=500g/turn
- **Deferred**: TAX command, variable prices, trading discounts

### Magic
- **Simplified**: Only Teleport (instant, costs magic power = distance/10)
- **Deferred**: Summon, Fly, Conjure, Scry, magical items

### Recruiting
- **Simplified**: Fixed caps per pop band, instant recruitment
- **Caps**: <1k=10/turn, 1k-9k=50/turn, 10k-99k=200/turn, 100k+=500/turn
- **Deferred**: Time-based recruitment, availability fluctuations

## Alpha Design Principles

1. **Deterministic**: Fixed seed = fixed outcome for testing and fairness
2. **Modular**: Clean separation between models, engine, parser, reporting
3. **Extensible**: Easy to add deferred features in future versions
4. **Testable**: Clear interfaces, unit tests for core logic
5. **Readable**: English-like orders, human-readable reports
6. **File-based**: No databases, pure JSON/YAML persistence

## Success Criteria for Alpha

The alpha is considered successful if:

1. ✅ A player can initialize a game with 2+ factions on a map
2. ✅ Players can submit text order files with English-like commands
3. ✅ The engine can parse orders and produce structured Order objects
4. ✅ The engine processes a full turn deterministically
5. ✅ Combat occurs and produces clear winners/losers
6. ✅ Factions can recruit units and buy ships
7. ✅ Movement between cities works correctly
8. ✅ Per-player reports are generated showing all relevant actions
9. ✅ Game state persists to disk and can be resumed
10. ✅ Same seed produces identical results for regression testing

## Next Steps After Alpha

1. Add health and character progression
2. Implement SECURE and location control
3. Add TAX command with detailed mechanics
4. Expand magic system (Summon, Fly)
5. Add diplomacy (Ally/Enemy, messaging)
6. Implement resource gathering and construction
7. Add complex combat modifiers
8. Implement conditional orders and queuing
9. Add character training (TEACH/STUDY)
10. Full integration testing with larger scenarios
