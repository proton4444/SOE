"""
Game state management system
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import os

from ..models import (
    Character, Location, Item, Group, Order,
    ResourceInventory, OrderStatus
)


@dataclass
class GameState:
    """
    Central game state manager.

    Stores all game entities and provides methods to access and modify them.
    """
    # Game metadata
    game_id: str = "default"
    current_turn: int = 0
    game_week: int = 0
    game_day: int = 0

    # Time ratio (real days to game weeks, default 1:1)
    time_ratio: int = 7

    # Entity storage
    characters: Dict[str, Character] = field(default_factory=dict)
    locations: Dict[str, Location] = field(default_factory=dict)
    items: Dict[str, Item] = field(default_factory=dict)
    groups: Dict[str, Group] = field(default_factory=dict)
    orders: Dict[str, Order] = field(default_factory=dict)

    # Player management
    players: Dict[str, Dict] = field(default_factory=dict)  # player_id: player_data

    # Resource inventories
    character_inventories: Dict[str, ResourceInventory] = field(default_factory=dict)
    location_inventories: Dict[str, ResourceInventory] = field(default_factory=dict)

    # Game settings
    settings: Dict[str, any] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # === Character Management ===

    def add_character(self, character: Character) -> str:
        """Add a character to the game"""
        self.characters[character.id] = character
        # Initialize resource inventory for character
        if character.id not in self.character_inventories:
            self.character_inventories[character.id] = ResourceInventory()
        self.update_timestamp()
        return character.id

    def get_character(self, character_id: str) -> Optional[Character]:
        """Get a character by ID"""
        return self.characters.get(character_id)

    def get_character_by_name(self, name: str, player_id: Optional[str] = None) -> Optional[Character]:
        """
        Get a character by name, optionally filtered by player.
        Matches against both name alone and full name with title.
        """
        name_lower = name.lower()
        for char in self.characters.values():
            # Check if matches name or full name
            if char.name.lower() == name_lower or char.full_name.lower() == name_lower:
                if player_id is None or char.player_id == player_id:
                    return char
        return None

    def get_player_characters(self, player_id: str) -> List[Character]:
        """Get all characters belonging to a player"""
        return [char for char in self.characters.values() if char.player_id == player_id]

    def remove_character(self, character_id: str) -> bool:
        """Remove a character from the game"""
        if character_id in self.characters:
            del self.characters[character_id]
            if character_id in self.character_inventories:
                del self.character_inventories[character_id]
            self.update_timestamp()
            return True
        return False

    # === Location Management ===

    def add_location(self, location: Location) -> str:
        """Add a location to the game"""
        self.locations[location.id] = location
        if location.id not in self.location_inventories:
            self.location_inventories[location.id] = ResourceInventory()
        self.update_timestamp()
        return location.id

    def get_location(self, location_id: str) -> Optional[Location]:
        """Get a location by ID"""
        return self.locations.get(location_id)

    def get_location_by_name(self, name: str) -> Optional[Location]:
        """Get a location by name"""
        name_lower = name.lower()
        for loc in self.locations.values():
            if loc.name.lower() == name_lower:
                return loc
        return None

    def get_characters_at_location(self, location_id: str) -> List[Character]:
        """Get all characters at a specific location"""
        return [char for char in self.characters.values() if char.location_id == location_id]

    # === Item Management ===

    def add_item(self, item: Item) -> str:
        """Add an item to the game"""
        self.items[item.id] = item
        self.update_timestamp()
        return item.id

    def get_item(self, item_id: str) -> Optional[Item]:
        """Get an item by ID"""
        return self.items.get(item_id)

    def get_character_items(self, character_id: str) -> List[Item]:
        """Get all items owned by a character"""
        return [item for item in self.items.values() if item.owner_id == character_id]

    # === Group Management ===

    def add_group(self, group: Group) -> str:
        """Add a group to the game"""
        self.groups[group.id] = group
        self.update_timestamp()
        return group.id

    def get_group(self, group_id: str) -> Optional[Group]:
        """Get a group by ID"""
        return self.groups.get(group_id)

    def get_character_group(self, character_id: str) -> Optional[Group]:
        """Get the group a character belongs to"""
        char = self.get_character(character_id)
        if char and char.group_id:
            return self.get_group(char.group_id)
        return None

    def remove_group(self, group_id: str) -> bool:
        """Remove a group from the game"""
        if group_id in self.groups:
            del self.groups[group_id]
            self.update_timestamp()
            return True
        return False

    # === Order Management ===

    def add_order(self, order: Order) -> str:
        """Add an order to the queue"""
        self.orders[order.id] = order
        self.update_timestamp()
        return order.id

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get an order by ID"""
        return self.orders.get(order_id)

    def get_character_orders(self, character_id: str, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get all orders for a character, optionally filtered by status"""
        orders = [order for order in self.orders.values() if order.character_id == character_id]
        if status:
            orders = [order for order in orders if order.status == status]
        return sorted(orders, key=lambda o: o.created_at)

    def get_pending_orders(self) -> List[Order]:
        """Get all pending orders"""
        return [order for order in self.orders.values() if order.status == OrderStatus.PENDING]

    def cancel_character_orders(self, character_id: str) -> int:
        """Cancel all pending orders for a character. Returns count of cancelled orders."""
        orders = self.get_character_orders(character_id, OrderStatus.PENDING)
        for order in orders:
            order.mark_cancelled()
        self.update_timestamp()
        return len(orders)

    # === Resource Management ===

    def get_character_inventory(self, character_id: str) -> ResourceInventory:
        """Get a character's resource inventory"""
        if character_id not in self.character_inventories:
            self.character_inventories[character_id] = ResourceInventory()
        return self.character_inventories[character_id]

    def get_location_inventory(self, location_id: str) -> ResourceInventory:
        """Get a location's resource inventory"""
        if location_id not in self.location_inventories:
            self.location_inventories[location_id] = ResourceInventory()
        return self.location_inventories[location_id]

    # === Turn Management ===

    def advance_turn(self):
        """Advance the game by one turn"""
        self.current_turn += 1
        self.game_day += 1
        if self.game_day >= 7:
            self.game_day = 0
            self.game_week += 1
        self.update_timestamp()

    def update_timestamp(self):
        """Update the last modified timestamp"""
        self.updated_at = datetime.now()

    # === Persistence ===

    def save_to_file(self, filepath: str):
        """Save game state to a JSON file"""
        data = {
            "game_id": self.game_id,
            "current_turn": self.current_turn,
            "game_week": self.game_week,
            "game_day": self.game_day,
            "time_ratio": self.time_ratio,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Note: Actual serialization of entities would need custom serializers
            # This is a simplified version
        }
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> 'GameState':
        """Load game state from a JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        # Note: Actual deserialization would need custom deserializers
        # This is a simplified version
        game_state = cls(
            game_id=data["game_id"],
            current_turn=data["current_turn"],
            game_week=data["game_week"],
            game_day=data["game_day"],
            time_ratio=data["time_ratio"],
        )
        return game_state
