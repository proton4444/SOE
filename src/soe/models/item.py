"""
Item model for Spoils of Empire
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict
import uuid


class ItemType(Enum):
    """Types of items in the game"""
    WEAPON = "weapon"
    ARMOR = "armor"
    MAGICAL_ITEM = "magical_item"
    TOOL = "tool"
    CONTAINER = "container"
    VEHICLE = "vehicle"
    BOOK = "book"
    POTION = "potion"


@dataclass
class Item:
    """
    Represents an item that can be carried by characters.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    item_type: ItemType = ItemType.TOOL
    description: str = ""

    # Value and weight
    value: int = 0
    weight: int = 0

    # Ownership
    owner_id: Optional[str] = None
    location_id: Optional[str] = None

    # Magical properties
    is_magical: bool = False
    magic_charges: int = 0
    max_charges: int = 0

    # Item attributes (flexible key-value storage)
    attributes: Dict[str, any] = field(default_factory=dict)

    # Condition
    durability: int = 100
    max_durability: int = 100

    def is_usable(self) -> bool:
        """Check if item can be used"""
        if self.is_magical and self.magic_charges <= 0:
            return False
        if self.durability <= 0:
            return False
        return True

    def use_charge(self) -> bool:
        """
        Use one magic charge.
        Returns True if successful.
        """
        if self.is_magical and self.magic_charges > 0:
            self.magic_charges -= 1
            return True
        return False

    def recharge(self, amount: int = 1):
        """Recharge magical item"""
        if self.is_magical:
            self.magic_charges = min(self.magic_charges + amount, self.max_charges)

    def repair(self, amount: int):
        """Repair item durability"""
        self.durability = min(self.durability + amount, self.max_durability)

    def damage(self, amount: int) -> bool:
        """
        Damage the item.
        Returns True if item is destroyed.
        """
        self.durability -= amount
        if self.durability <= 0:
            self.durability = 0
            return True
        return False
