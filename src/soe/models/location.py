"""
Location model for Spoils of Empire
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum
import uuid


class LocationType(Enum):
    """Types of locations"""
    CITY = "city"
    TOWN = "town"
    VILLAGE = "village"
    WILDERNESS = "wilderness"
    DUNGEON = "dungeon"
    CASTLE = "castle"
    TEMPLE = "temple"
    MINE = "mine"


@dataclass
class Location:
    """
    Represents a location on the game map.

    Locations can be cities, towns, wilderness areas, etc.
    Characters travel between locations.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    location_type: LocationType = LocationType.WILDERNESS
    description: str = ""

    # Map coordinates (optional)
    x: Optional[int] = None
    y: Optional[int] = None

    # Connected locations (for travel)
    connections: Dict[str, int] = field(default_factory=dict)  # location_id: distance

    # Characters at this location
    character_ids: List[str] = field(default_factory=list)

    # Resources available at location
    available_resources: Dict[str, int] = field(default_factory=dict)

    # Location properties
    is_fortified: bool = False
    fortification_level: int = 0
    is_magic_free_zone: bool = False

    # Ownership
    owner_id: Optional[str] = None

    # Population
    population: int = 0

    def add_character(self, character_id: str):
        """Add a character to this location"""
        if character_id not in self.character_ids:
            self.character_ids.append(character_id)

    def remove_character(self, character_id: str):
        """Remove a character from this location"""
        if character_id in self.character_ids:
            self.character_ids.remove(character_id)

    def add_connection(self, location_id: str, distance: int):
        """Add a connection to another location"""
        self.connections[location_id] = distance

    def get_distance_to(self, location_id: str) -> Optional[int]:
        """Get distance to another location"""
        return self.connections.get(location_id)

    def is_connected_to(self, location_id: str) -> bool:
        """Check if this location is connected to another"""
        return location_id in self.connections
