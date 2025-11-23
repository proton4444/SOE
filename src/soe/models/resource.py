"""
Resource model for Spoils of Empire
"""

from enum import Enum
from dataclasses import dataclass


class ResourceType(Enum):
    """Types of resources in the game"""
    GOLD = "gold"
    SOLDIER = "soldier"
    WORKER = "worker"
    HORSE = "horse"
    SHIP = "ship"
    FOOD = "food"
    WOOD = "wood"
    STONE = "stone"
    IRON = "iron"


@dataclass
class Resource:
    """
    Represents a quantity of a specific resource type.
    """
    resource_type: ResourceType
    quantity: int = 0

    def add(self, amount: int):
        """Add to resource quantity"""
        self.quantity += amount

    def remove(self, amount: int) -> bool:
        """
        Remove from resource quantity.
        Returns True if successful, False if insufficient quantity.
        """
        if self.quantity >= amount:
            self.quantity -= amount
            return True
        return False

    def has_enough(self, amount: int) -> bool:
        """Check if there is enough of this resource"""
        return self.quantity >= amount

    def transfer_to(self, other: 'Resource', amount: int) -> bool:
        """
        Transfer amount to another Resource instance.
        Returns True if successful.
        """
        if self.resource_type != other.resource_type:
            return False
        if self.remove(amount):
            other.add(amount)
            return True
        return False


@dataclass
class ResourceInventory:
    """
    Manages multiple resource types for a character or location.
    """
    resources: dict[ResourceType, int] = None

    def __post_init__(self):
        """Initialize resources dict if not provided"""
        if self.resources is None:
            self.resources = {resource_type: 0 for resource_type in ResourceType}

    def get(self, resource_type: ResourceType) -> int:
        """Get quantity of a resource type"""
        return self.resources.get(resource_type, 0)

    def set(self, resource_type: ResourceType, amount: int):
        """Set quantity of a resource type"""
        self.resources[resource_type] = max(0, amount)

    def add(self, resource_type: ResourceType, amount: int):
        """Add to resource quantity"""
        current = self.get(resource_type)
        self.set(resource_type, current + amount)

    def remove(self, resource_type: ResourceType, amount: int) -> bool:
        """
        Remove from resource quantity.
        Returns True if successful.
        """
        current = self.get(resource_type)
        if current >= amount:
            self.set(resource_type, current - amount)
            return True
        return False

    def has_enough(self, resource_type: ResourceType, amount: int) -> bool:
        """Check if there is enough of a resource"""
        return self.get(resource_type) >= amount

    def transfer_to(self, other: 'ResourceInventory', resource_type: ResourceType, amount: int) -> bool:
        """
        Transfer resources to another inventory.
        Returns True if successful.
        """
        if self.remove(resource_type, amount):
            other.add(resource_type, amount)
            return True
        return False
