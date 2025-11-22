"""
Domain models for the Spoils of Empire game.

This module defines all core game entities: cities, roads, factions,
characters, units, ships, and the overall game state.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class PopulationBand(str, Enum):
    """Population size categories for cities."""
    TINY = "< 10k"           # Less than 10,000
    SMALL = "10k-99k"        # 10,000 to 99,999
    MEDIUM = "100k-999k"     # 100,000 to 999,999
    LARGE = "1M+"            # 1 million or more


class RoadQuality(str, Enum):
    """Quality of roads and sea lanes affecting movement cost."""
    EXCELLENT = "excellent"  # Movement cost multiplier: 0.5
    GOOD = "good"            # Movement cost multiplier: 1.0
    FAIR = "fair"            # Movement cost multiplier: 1.5
    POOR = "poor"            # Movement cost multiplier: 2.0
    SEA = "sea"              # Sea lane (requires ship)


class UnitType(str, Enum):
    """Types of unnamed characters/units."""
    SOLDIER = "soldier"      # Combat skill 1
    SAILOR = "sailor"        # Sailing skill 1
    WORKER = "worker"        # No skills


class ShipType(str, Enum):
    """Types of ships."""
    GALLEY = "galley"        # Basic war/transport ship


# ============================================================================
# MAP & GEOGRAPHY
# ============================================================================

@dataclass
class City:
    """
    A location on the map (city, town, or ruin).

    Attributes:
        id: Unique identifier (e.g., "madegi_doy")
        name: Human-readable name (e.g., "Madegi Doy")
        population_band: Size category of the city
        terrain: Set of terrain features (e.g., {"plains", "river"})
        region: Optional region/island name
        is_port: Whether ships can dock/be built here
    """
    id: str
    name: str
    population_band: PopulationBand
    terrain: set[str] = field(default_factory=set)
    region: Optional[str] = None
    is_port: bool = False

    def __hash__(self):
        return hash(self.id)


@dataclass
class Road:
    """
    A connection between two cities (road or sea lane).

    Attributes:
        id: Unique identifier
        from_city_id: Source city ID
        to_city_id: Destination city ID
        quality: Quality/condition of the route
        bidirectional: If True, can travel both ways with same cost
    """
    id: str
    from_city_id: str
    to_city_id: str
    quality: RoadQuality
    bidirectional: bool = True


@dataclass
class WorldMap:
    """
    The game world map containing all cities and roads.

    Attributes:
        cities: Dict mapping city_id -> City
        roads: Dict mapping road_id -> Road
    """
    cities: dict[str, City] = field(default_factory=dict)
    roads: dict[str, Road] = field(default_factory=dict)

    def neighbors(self, city_id: str) -> list[tuple[City, Road]]:
        """
        Get all cities directly connected to the given city.

        Returns:
            List of (neighbor_city, connecting_road) tuples
        """
        neighbors = []
        for road in self.roads.values():
            if road.from_city_id == city_id:
                neighbor = self.cities.get(road.to_city_id)
                if neighbor:
                    neighbors.append((neighbor, road))
            elif road.bidirectional and road.to_city_id == city_id:
                neighbor = self.cities.get(road.from_city_id)
                if neighbor:
                    neighbors.append((neighbor, road))
        return neighbors

    def get_city_by_name(self, name: str) -> Optional[City]:
        """Find a city by its name (case-insensitive)."""
        name_lower = name.lower()
        for city in self.cities.values():
            if city.name.lower() == name_lower:
                return city
        return None


# ============================================================================
# GAME ENTITIES
# ============================================================================

@dataclass
class Faction:
    """
    A player faction/empire.

    Attributes:
        id: Unique identifier (e.g., "player_1")
        name: Faction name (e.g., "The Golden Empire")
        controlled_city_ids: Set of city IDs under faction control
        secured_city_ids: Set of city IDs this faction has secured
        treasury: Gold amount
        allies: Set of faction IDs that are allies
        enemies: Set of faction IDs that are enemies
    """
    id: str
    name: str
    controlled_city_ids: set[str] = field(default_factory=set)
    secured_city_ids: set[str] = field(default_factory=set)
    treasury: int = 0
    allies: set[str] = field(default_factory=set)
    enemies: set[str] = field(default_factory=set)


@dataclass
class Character:
    """
    A named character/hero with skills and abilities.

    Attributes:
        id: Unique identifier
        name: Character name (must be unique across game)
        faction_id: Owning faction
        location_city_id: Current location
        gender: Gender of character (male/female)
        title: Optional title (e.g., "primate", "bishop")
        movement_points: Movement remaining this turn
        combat_skill: Combat skill level (0-100)
        magic_skill: Magic skill level (0-100)
        magic_power_current: Current magic power available
        religion_skill: Religion skill level (0-100)
        religious_power_current: Current religious power available
        health: Health (0-100, 100 = perfect health)
        is_dead: Whether character is dead (health = 0)
    """
    id: str
    name: str
    faction_id: str
    location_city_id: str
    gender: str = "male"  # "male" or "female"
    title: str = ""  # Optional title (e.g., "primate", "bishop")
    movement_points: int = 10  # Reset each turn
    combat_skill: int = 0
    magic_skill: int = 0
    magic_power_current: int = 0  # Max = magic_skill
    religion_skill: int = 0
    religious_power_current: int = 0  # Max = religion_skill
    health: int = 100  # 0-100, 0 = dead
    is_dead: bool = False

    @property
    def max_magic_power(self) -> int:
        """Maximum magic power equals magic skill level."""
        return self.magic_skill

    @property
    def max_religious_power(self) -> int:
        """Maximum religious power equals religion skill level."""
        return self.religion_skill

    def effective_skill(self, base_skill: int) -> int:
        """Calculate effective skill based on current health."""
        if self.health >= 100:
            return base_skill
        return int(base_skill * self.health / 100)


@dataclass
class UnitStack:
    """
    A group of unnamed units (soldiers, sailors, workers).

    Attributes:
        id: Unique identifier
        faction_id: Owning faction
        location_city_id: Current location
        unit_type: Type of units in this stack
        count: Number of units
    """
    id: str
    faction_id: str
    location_city_id: str
    unit_type: UnitType
    count: int

    @property
    def attack_value(self) -> int:
        """Total attack value (only soldiers contribute)."""
        if self.unit_type == UnitType.SOLDIER:
            return self.count * 1  # Each soldier = 1 attack
        return 0

    @property
    def defense_value(self) -> int:
        """Total defense value (only soldiers contribute)."""
        if self.unit_type == UnitType.SOLDIER:
            return self.count * 1  # Each soldier = 1 defense
        return 0


@dataclass
class Ship:
    """
    A ship (currently only galleys in alpha).

    Attributes:
        id: Unique identifier
        faction_id: Owning faction
        location_city_id: Current location (must be port)
        ship_type: Type of ship
        capacity: Cargo/passenger capacity
    """
    id: str
    faction_id: str
    location_city_id: str
    ship_type: ShipType
    capacity: int = 550  # Galley default

    @property
    def attack_value(self) -> int:
        """Ship attack value (simplified)."""
        if self.ship_type == ShipType.GALLEY:
            return 5
        return 0

    @property
    def defense_value(self) -> int:
        """Ship defense value (simplified)."""
        if self.ship_type == ShipType.GALLEY:
            return 5
        return 0


# ============================================================================
# GAME STATE
# ============================================================================

@dataclass
class GameState:
    """
    Complete state of the game at a point in time.

    This is the root object that gets serialized to/from JSON.

    Attributes:
        turn_number: Current turn (starts at 0)
        world_map: The game map
        factions: Dict mapping faction_id -> Faction
        characters: Dict mapping character_id -> Character
        unit_stacks: Dict mapping unit_stack_id -> UnitStack
        ships: Dict mapping ship_id -> Ship
    """
    turn_number: int = 0
    world_map: WorldMap = field(default_factory=WorldMap)
    factions: dict[str, Faction] = field(default_factory=dict)
    characters: dict[str, Character] = field(default_factory=dict)
    unit_stacks: dict[str, UnitStack] = field(default_factory=dict)
    ships: dict[str, Ship] = field(default_factory=dict)

    def get_character_by_name(self, name: str, faction_id: Optional[str] = None) -> Optional[Character]:
        """
        Find a character by name (case-insensitive).

        Args:
            name: Character name to search for
            faction_id: If provided, only search within this faction

        Returns:
            Character if found, None otherwise
        """
        name_lower = name.lower()
        for char in self.characters.values():
            if faction_id and char.faction_id != faction_id:
                continue
            if char.name.lower() == name_lower:
                return char
        return None

    def get_faction_units_at_city(self, faction_id: str, city_id: str) -> list[UnitStack]:
        """Get all unit stacks for a faction at a specific city."""
        return [
            stack for stack in self.unit_stacks.values()
            if stack.faction_id == faction_id and stack.location_city_id == city_id
        ]

    def get_faction_characters_at_city(self, faction_id: str, city_id: str) -> list[Character]:
        """Get all characters for a faction at a specific city."""
        return [
            char for char in self.characters.values()
            if char.faction_id == faction_id and char.location_city_id == city_id
        ]

    def get_faction_ships_at_city(self, faction_id: str, city_id: str) -> list[Ship]:
        """Get all ships for a faction at a specific city."""
        return [
            ship for ship in self.ships.values()
            if ship.faction_id == faction_id and ship.location_city_id == city_id
        ]
