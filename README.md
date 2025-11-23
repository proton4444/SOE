# Spoils of Empire

A fantasy, strategy game designed for play-by-email (PBEM) by Rick Morneau.

This is a Python implementation of the Spoils of Empire game engine.

## Project Status

**Phase 1 (Core Systems) - In Progress**
- ✅ Project structure
- 🔄 Core data models
- 🔄 Game state management
- 🔄 Command parser
- 🔄 Character management commands
- 🔄 Basic movement commands
- 🔄 Resource handling commands

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

### Phase 1 Commands

- NAME - Name or rename characters
- PROMOTE - Change character titles
- GO/MOVE/TRAVEL - Move characters between locations
- HALT/STOP - Cancel pending orders
- ASSIGN/GIVE - Assign resources to characters
- GET/TAKE - Take resources from characters

## License

Original game design Copyright © 2001 by Richard A. Morneau
