"""
Storage system for persisting game state to/from disk.

Uses JSON for human-readable persistence. All game state is saved
to a single state.json file in the game directory.
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import asdict, is_dataclass

from spoils_engine.models import (
    GameState, WorldMap, Faction, Character, UnitStack, Ship,
    City, Road, PopulationBand, RoadQuality, UnitType, ShipType
)


# ============================================================================
# CUSTOM JSON ENCODER/DECODER
# ============================================================================

class GameStateEncoder(json.JSONEncoder):
    """Custom JSON encoder for game state objects."""

    def default(self, obj):
        """Convert dataclasses and enums to JSON-serializable formats."""
        if is_dataclass(obj):
            # Convert dataclass to dict
            data = asdict(obj)
            # Add type information for reconstruction
            data['__type__'] = obj.__class__.__name__
            return data
        elif isinstance(obj, (PopulationBand, RoadQuality, UnitType, ShipType)):
            # Enums: just use their value
            return obj.value
        elif isinstance(obj, set):
            # Sets to lists
            return list(obj)
        return super().default(obj)


def decode_game_state(data: dict) -> GameState:
    """
    Decode a dict back into a GameState object.

    Args:
        data: Dictionary loaded from JSON

    Returns:
        Reconstructed GameState
    """
    # Reconstruct WorldMap
    world_map_data = data.get('world_map', {})
    cities = {}
    for city_id, city_data in world_map_data.get('cities', {}).items():
        cities[city_id] = City(
            id=city_data['id'],
            name=city_data['name'],
            population_band=PopulationBand(city_data['population_band']),
            terrain=set(city_data.get('terrain', [])),
            region=city_data.get('region'),
            is_port=city_data.get('is_port', False)
        )

    roads = {}
    for road_id, road_data in world_map_data.get('roads', {}).items():
        roads[road_id] = Road(
            id=road_data['id'],
            from_city_id=road_data['from_city_id'],
            to_city_id=road_data['to_city_id'],
            quality=RoadQuality(road_data['quality']),
            bidirectional=road_data.get('bidirectional', True)
        )

    world_map = WorldMap(cities=cities, roads=roads)

    # Reconstruct Factions
    factions = {}
    for faction_id, faction_data in data.get('factions', {}).items():
        factions[faction_id] = Faction(
            id=faction_data['id'],
            name=faction_data['name'],
            controlled_city_ids=set(faction_data.get('controlled_city_ids', [])),
            treasury=faction_data.get('treasury', 0)
        )

    # Reconstruct Characters
    characters = {}
    for char_id, char_data in data.get('characters', {}).items():
        characters[char_id] = Character(
            id=char_data['id'],
            name=char_data['name'],
            faction_id=char_data['faction_id'],
            location_city_id=char_data['location_city_id'],
            movement_points=char_data.get('movement_points', 10),
            combat_skill=char_data.get('combat_skill', 0),
            magic_skill=char_data.get('magic_skill', 0),
            magic_power_current=char_data.get('magic_power_current', 0),
            health=char_data.get('health', 100)
        )

    # Reconstruct UnitStacks
    unit_stacks = {}
    for stack_id, stack_data in data.get('unit_stacks', {}).items():
        unit_stacks[stack_id] = UnitStack(
            id=stack_data['id'],
            faction_id=stack_data['faction_id'],
            location_city_id=stack_data['location_city_id'],
            unit_type=UnitType(stack_data['unit_type']),
            count=stack_data['count']
        )

    # Reconstruct Ships
    ships = {}
    for ship_id, ship_data in data.get('ships', {}).items():
        ships[ship_id] = Ship(
            id=ship_data['id'],
            faction_id=ship_data['faction_id'],
            location_city_id=ship_data['location_city_id'],
            ship_type=ShipType(ship_data['ship_type']),
            capacity=ship_data.get('capacity', 550)
        )

    return GameState(
        turn_number=data.get('turn_number', 0),
        world_map=world_map,
        factions=factions,
        characters=characters,
        unit_stacks=unit_stacks,
        ships=ships
    )


# ============================================================================
# SAVE/LOAD FUNCTIONS
# ============================================================================

def save_game_state(game_state: GameState, game_dir: Path) -> None:
    """
    Save game state to disk.

    Args:
        game_state: The game state to save
        game_dir: Directory for the game (e.g., games/my_game/)
    """
    game_dir = Path(game_dir)
    game_dir.mkdir(parents=True, exist_ok=True)

    state_file = game_dir / "state.json"
    with open(state_file, 'w') as f:
        json.dump(asdict(game_state), f, cls=GameStateEncoder, indent=2)


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

    with open(state_file, 'r') as f:
        data = json.load(f)

    return decode_game_state(data)


def game_exists(game_dir: Path) -> bool:
    """Check if a game directory exists with a valid state file."""
    state_file = Path(game_dir) / "state.json"
    return state_file.exists()
