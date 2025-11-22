"""
Order definitions for player commands.

All orders inherit from a base Order class and represent structured
commands that the engine can process.
"""

from dataclasses import dataclass, field
from typing import Optional
from abc import ABC, abstractmethod


# ============================================================================
# BASE ORDER
# ============================================================================

@dataclass
class Order(ABC):
    """
    Abstract base class for all orders.

    Attributes:
        player_id: ID of the player issuing this order
        original_text: Original text snippet for debugging
        warnings: List of warnings generated during parsing/validation
    """
    player_id: str
    original_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @abstractmethod
    def order_type(self) -> str:
        """Return the type name of this order (for reporting)."""
        pass


# ============================================================================
# MOVEMENT ORDERS
# ============================================================================

@dataclass
class MoveOrder(Order):
    """
    Order a character to move to a destination city.

    Attributes:
        actor_id: Character ID who will move
        destination_city_id: Target city ID
        path: Optional explicit path (list of city IDs)
    """
    actor_id: str = ""
    destination_city_id: str = ""
    path: list[str] = field(default_factory=list)

    def order_type(self) -> str:
        return "MOVE"


@dataclass
class SailOrder(Order):
    """
    Order a character to sail a ship to a destination city via sea.

    Attributes:
        actor_id: Character ID who will be the captain
        destination_city_id: Target city ID
        ship_id: ID of ship to sail (optional, auto-selects if omitted)
    """
    actor_id: str = ""
    destination_city_id: str = ""
    ship_id: str = ""  # Optional: will auto-select a ship if empty

    def order_type(self) -> str:
        return "SAIL"


# ============================================================================
# RECRUITMENT & PURCHASE ORDERS
# ============================================================================

@dataclass
class RecruitOrder(Order):
    """
    Order a character to recruit units in a city.

    Attributes:
        actor_id: Character ID who will recruit
        city_id: City where recruitment happens
        unit_type: Type of unit to recruit ("soldier", "sailor", "worker")
        count: Number of units to recruit
    """
    actor_id: str = ""
    city_id: str = ""
    unit_type: str = ""  # Will be validated against UnitType enum
    count: int = 0

    def order_type(self) -> str:
        return "RECRUIT"


@dataclass
class BuyShipOrder(Order):
    """
    Order a character to buy ships in a port city.

    Attributes:
        actor_id: Character ID who will buy
        city_id: City where purchase happens (must be port)
        ship_type: Type of ship to buy ("galley")
        count: Number of ships to buy
    """
    actor_id: str = ""
    city_id: str = ""
    ship_type: str = ""  # Will be validated against ShipType enum
    count: int = 0

    def order_type(self) -> str:
        return "BUY_SHIP"


# ============================================================================
# COMBAT ORDERS
# ============================================================================

@dataclass
class AttackOrder(Order):
    """
    Order a character to attack enemies at a location.

    Attributes:
        actor_id: Character ID who will lead the attack
        location_city_id: City where the attack happens
        target_faction_id: Target faction ID (resolved from target name)
        target_name: Original target name from text (for reporting)
    """
    actor_id: str = ""
    location_city_id: str = ""
    target_faction_id: str = ""
    target_name: str = ""

    def order_type(self) -> str:
        return "ATTACK"


# ============================================================================
# MAGIC ORDERS
# ============================================================================

@dataclass
class TeleportOrder(Order):
    """
    Order a magic user to teleport a character to a destination.

    Attributes:
        actor_id: Magic user who will cast the spell
        target_character_id: Character to teleport (can be self)
        destination_city_id: Destination city ID
        target_name: Original target name from text (for reporting)
    """
    actor_id: str = ""
    target_character_id: str = ""
    destination_city_id: str = ""
    target_name: str = ""

    def order_type(self) -> str:
        return "TELEPORT"


@dataclass
class FlyOrder(Order):
    """
    Order a magic user to fly (self and group) to a destination.

    Attributes:
        actor_id: Magic user who will cast the spell (must be group leader)
        destination_city_id: Destination city ID
    """
    actor_id: str = ""
    destination_city_id: str = ""

    def order_type(self) -> str:
        return "FLY"


@dataclass
class HealOrder(Order):
    """
    Order a healer to heal wounded characters.

    Attributes:
        actor_id: Healer who will cast the spell (religion skill required)
        target_character_ids: List of character IDs to heal
        heal_amounts: Dict mapping character_id -> heal amount
        heal_to_levels: Dict mapping character_id -> target health level
    """
    actor_id: str = ""
    target_character_ids: list[str] = field(default_factory=list)
    heal_amounts: dict[str, int] = field(default_factory=dict)  # character_id -> heal by X points
    heal_to_levels: dict[str, int] = field(default_factory=dict)  # character_id -> heal to level X

    def order_type(self) -> str:
        return "HEAL"


# ============================================================================
# LOCATION CONTROL ORDERS
# ============================================================================

@dataclass
class SecureOrder(Order):
    """
    Order a character to secure/control a location.

    Attributes:
        actor_id: Character ID who will secure the location
        city_id: City to secure (usually actor's current location)
    """
    actor_id: str = ""
    city_id: str = ""

    def order_type(self) -> str:
        return "SECURE"


# ============================================================================
# DIPLOMACY ORDERS
# ============================================================================

@dataclass
class AllyOrder(Order):
    """
    Declare another faction as an ally.

    Attributes:
        target_faction_id: Faction ID to ally with
        target_faction_name: Original faction name from text
    """
    target_faction_id: str = ""
    target_faction_name: str = ""

    def order_type(self) -> str:
        return "ALLY"


@dataclass
class EnemyOrder(Order):
    """
    Declare another faction as an enemy.

    Attributes:
        target_faction_id: Faction ID to declare as enemy
        target_faction_name: Original faction name from text
    """
    target_faction_id: str = ""
    target_faction_name: str = ""

    def order_type(self) -> str:
        return "ENEMY"


@dataclass
class NeutralOrder(Order):
    """
    Set diplomatic stance to neutral with another faction.

    Attributes:
        target_faction_id: Faction ID to set neutral
        target_faction_name: Original faction name from text
    """
    target_faction_id: str = ""
    target_faction_name: str = ""

    def order_type(self) -> str:
        return "NEUTRAL"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_order_from_type(order_type: str, player_id: str, original_text: str = "") -> Optional[Order]:
    """
    Factory function to create an order of the given type.

    Args:
        order_type: Type of order to create
        player_id: Player issuing the order
        original_text: Original text for debugging

    Returns:
        Order instance or None if type unknown
    """
    order_map = {
        "MOVE": MoveOrder,
        "SAIL": SailOrder,
        "RECRUIT": RecruitOrder,
        "BUY_SHIP": BuyShipOrder,
        "ATTACK": AttackOrder,
        "TELEPORT": TeleportOrder,
        "FLY": FlyOrder,
        "HEAL": HealOrder,
        "SECURE": SecureOrder,
        "ALLY": AllyOrder,
        "ENEMY": EnemyOrder,
        "NEUTRAL": NeutralOrder,
    }

    order_class = order_map.get(order_type.upper())
    if order_class:
        return order_class(player_id=player_id, original_text=original_text)
    return None
