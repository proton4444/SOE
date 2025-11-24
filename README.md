# Spoils of Empire

A fantasy, strategy game designed for play-by-email (PBEM) by Rick Morneau.

This is a Python implementation of the Spoils of Empire game engine.

## Project Status

**Phase 1 (Core Systems) - ✅ Complete**
- ✅ Project structure
- ✅ Core data models
- ✅ Game state management
- ✅ Command parser
- ✅ Character management commands
- ✅ Basic movement commands
- ✅ Resource handling commands

**Phase 2 (Combat & Military) - ✅ Complete**
- ✅ Combat system with damage calculation
- ✅ Attack and capture mechanics
- ✅ Fortification system
- ✅ Status commands (combatant, lurk)
- ✅ Advanced movement (fly, sail, teleport)
- ✅ Location control system

## Installation

```bash
pip install -r requirements.txt
```

## Running Tests

```bash
pytest
```

## Documentation

See `rules.md` for complete game rules and command reference.

## Development

### Project Structure

```
src/soe/
├── models/          # Data models (Character, Location, etc.)
├── commands/        # Command implementations
├── parser/          # Natural language command parser
├── game/            # Game state management
└── engine/          # Core game engine
```

### Commands Implemented

**Phase 1 - Core Systems (8 commands)**
- NAME - Name or rename characters
- PROMOTE - Change character titles
- GO/MOVE/TRAVEL - Move characters between locations
- HALT/STOP - Cancel pending orders
- ASSIGN - Assign resources to subordinates
- GIVE - Give resources to other characters
- GET/TAKE - Obtain resources from locations

**Phase 2 - Combat & Military (14 commands)**
- ATTACK - Attack another character
- CAPTURE - Capture weakened enemies
- ENSLAVE - Enslave captured prisoners
- KILL/EXECUTE - Execute prisoners or slaves
- FORTIFY/UNFORTIFY - Defensive positioning
- SECURE - Take control of locations
- COMBATANT/NONCOM - Set combat status
- LURK/UNLURK - Hide from observation
- FLY - Magical flight (requires magic skill)
- SAIL - Naval travel (requires ship)
- TELEPORT - Instant magical transport (requires high magic skill)

**Progress: 22 of 81 commands (27%)**

### Examples

Run Phase 1 demo:
```bash
python example.py
```

Run Phase 2 combat demo:
```bash
python example_phase2.py
```

## License

Original game design Copyright © 2001 by Richard A. Morneau
