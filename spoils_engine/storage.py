"""
Storage system for persisting game state to/from disk.

Uses JSON for human-readable persistence. All game state is saved
to a single state.json file in the game directory.

Serialization is driven by the dataclass field definitions in `models`,
so a field added to a model is persisted automatically. This matters for a
PBEM game: every turn is a save/load cycle, so a field that the decoder
forgets is a field that silently resets to its default every turn.
"""

import json
import os
import tempfile
import types
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union, get_args, get_origin

from spoils_engine.models import (
    GameState, WorldMap, Faction, Character, UnitStack, Ship,
    City, Road, SummonedCreature
)


# ============================================================================
# CUSTOM JSON ENCODER
# ============================================================================

class GameStateEncoder(json.JSONEncoder):
    """Custom JSON encoder for game state objects."""

    def default(self, obj):
        """Convert dataclasses, enums and sets to JSON-serializable formats."""
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, (set, frozenset)):
            # Sorted so saved files diff cleanly between turns.
            return sorted(obj)
        return super().default(obj)


# ============================================================================
# GENERIC DATACLASS RECONSTRUCTION
# ============================================================================

def _coerce(value: Any, target_type: Any) -> Any:
    """
    Coerce a JSON-decoded value back into the type declared on a dataclass field.

    Handles the type forms actually used by the models: enums, sets, dicts,
    lists, Optional[...] and plain scalars.
    """
    origin = get_origin(target_type)

    # Optional[X] / Union[X, None] -- both the typing and PEP 604 (`X | None`) spellings
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(target_type) if a is not type(None)]
        if value is None:
            return None
        return _coerce(value, args[0]) if len(args) == 1 else value

    # set[X] -- JSON has no sets, so they round-trip as lists
    if origin in (set, frozenset):
        item_args = get_args(target_type)
        item_type = item_args[0] if item_args else Any
        return {_coerce(v, item_type) for v in (value or [])}

    if origin is list:
        item_args = get_args(target_type)
        item_type = item_args[0] if item_args else Any
        return [_coerce(v, item_type) for v in (value or [])]

    if origin is dict:
        dict_args = get_args(target_type)
        val_type = dict_args[1] if len(dict_args) == 2 else Any
        return {k: _coerce(v, val_type) for k, v in (value or {}).items()}

    # Enum members are stored by value
    if isinstance(target_type, type) and issubclass(target_type, Enum):
        return target_type(value)

    if is_dataclass(target_type) and isinstance(value, dict):
        return rebuild_dataclass(target_type, value)

    return value


def rebuild_dataclass(cls: type, data: dict) -> Any:
    """
    Rebuild a dataclass instance from a plain dict.

    Fields missing from `data` fall back to the dataclass default, and unknown
    keys are ignored, so old save files stay loadable as the models evolve.
    """
    kwargs = {}
    for f in fields(cls):
        if f.name in data:
            kwargs[f.name] = _coerce(data[f.name], f.type)
    return cls(**kwargs)


def _rebuild_registry(data: dict, key: str, cls: type) -> dict:
    """Rebuild a dict of id -> dataclass from the saved payload."""
    return {
        entity_id: rebuild_dataclass(cls, entity_data)
        for entity_id, entity_data in (data.get(key) or {}).items()
    }


def decode_game_state(data: dict) -> GameState:
    """
    Decode a dict back into a GameState object.

    Args:
        data: Dictionary loaded from JSON

    Returns:
        Reconstructed GameState
    """
    world_map_data = data.get('world_map') or {}
    world_map = WorldMap(
        cities=_rebuild_registry(world_map_data, 'cities', City),
        roads=_rebuild_registry(world_map_data, 'roads', Road),
    )

    game_state = GameState(
        turn_number=data.get('turn_number', 0),
        world_map=world_map,
        factions=_rebuild_registry(data, 'factions', Faction),
        characters=_rebuild_registry(data, 'characters', Character),
        unit_stacks=_rebuild_registry(data, 'unit_stacks', UnitStack),
        ships=_rebuild_registry(data, 'ships', Ship),
        summoned_creatures=_rebuild_registry(data, 'summoned_creatures', SummonedCreature),
        tax_pools={k: float(v) for k, v in (data.get('tax_pools') or {}).items()},
        location_blessings=dict(data.get('location_blessings') or {}),
        location_curses=dict(data.get('location_curses') or {}),
    )
    _migrate(game_state, data)
    return game_state


def _migrate(game_state: GameState, data: dict) -> None:
    """
    Bring a save written by an older version up to the current model.

    Kept separate from decoding so each migration is one readable block that can
    be deleted once no save that old is plausibly still in play.
    """
    # v0.7.1 and earlier kept fortification levels in up to three places:
    # GameState.city_fortifications, Faction.fortifications and
    # City.fortification_level. The city is now the only store; fold the others
    # in, taking the highest level any of them claimed.
    legacy: dict[str, int] = {}
    for city_id, level in (data.get('city_fortifications') or {}).items():
        legacy[city_id] = max(legacy.get(city_id, 0), int(level))
    for faction_data in (data.get('factions') or {}).values():
        for city_id, level in (faction_data.get('fortifications') or {}).items():
            legacy[city_id] = max(legacy.get(city_id, 0), int(level))

    for city_id, level in legacy.items():
        city = game_state.world_map.cities.get(city_id)
        if city:
            city.fortification_level = max(city.fortification_level, level)

    # Character.is_leader did not exist before v0.7.2; the leader was whichever
    # character happened to iterate first. Preserve that character's status so
    # an in-flight game does not suddenly change who draws a salary.
    for faction_id in game_state.factions:
        members = [c for c in game_state.characters.values() if c.faction_id == faction_id]
        if members and not any(c.is_leader for c in members):
            members[0].is_leader = True

    # v0.8: gold is per character. Legacy saves only had Faction.treasury and
    # never wrote a Character.gold field. Detect that case from the raw JSON
    # (not the rebuilt defaults) so a deliberate treasury buffer in a v0.8
    # save is left alone.
    raw_chars = data.get("characters") or {}
    legacy_gold = bool(raw_chars) and all(
        "gold" not in (cdata or {}) for cdata in raw_chars.values()
    )
    if legacy_gold:
        for faction_id, faction in game_state.factions.items():
            if faction.treasury <= 0:
                continue
            members = [c for c in game_state.characters.values()
                       if c.faction_id == faction_id]
            if not members:
                continue
            leader = next((c for c in members if c.is_leader), members[0])
            leader.gold += faction.treasury
            faction.treasury = 0.0


# ============================================================================
# SAVE/LOAD FUNCTIONS
# ============================================================================

def save_game_state(game_state: GameState, game_dir: Path) -> None:
    """
    Save game state to disk.

    The write is atomic: the state is written to a temporary file in the same
    directory and then moved into place, so an interrupted save cannot leave a
    half-written state.json behind.

    Args:
        game_state: The game state to save
        game_dir: Directory for the game (e.g., games/my_game/)
    """
    game_dir = Path(game_dir)
    game_dir.mkdir(parents=True, exist_ok=True)

    state_file = game_dir / "state.json"
    payload = json.dumps(asdict(game_state), cls=GameStateEncoder, indent=2)

    fd, tmp_path = tempfile.mkstemp(dir=str(game_dir), prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(payload)
        os.replace(tmp_path, state_file)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def load_game_state(game_dir: Path) -> Optional[GameState]:
    """
    Load game state from disk.

    Args:
        game_dir: Directory for the game (e.g., games/my_game/)

    Returns:
        GameState if found, None otherwise
    """
    game_dir = Path(game_dir)
    state_file = game_dir / "state.json"

    if not state_file.exists():
        return None

    with open(state_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return decode_game_state(data)


def game_exists(game_dir: Path) -> bool:
    """Check if a game directory exists with a valid state file."""
    state_file = Path(game_dir) / "state.json"
    return state_file.exists()
