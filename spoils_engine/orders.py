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
# UNIT MANAGEMENT ORDERS
# ============================================================================

@dataclass
class AssignOrder(Order):
    """
    Assign/Give units or gold to another character.

    Attributes:
        donor_id: Character giving the units/gold
        recipient_id: Character receiving the units/gold
        unit_type: Type of unit to transfer (soldier/sailor/worker) or None for gold
        unit_count: Number of units to transfer
        gold_amount: Amount of gold to transfer
    """
    donor_id: str = ""
    recipient_id: str = ""
    unit_type: str = ""  # UnitType or empty string
    unit_count: int = 0
    gold_amount: int = 0

    def order_type(self) -> str:
        return "ASSIGN"


# ============================================================================
# CHARACTER MANAGEMENT ORDERS
# ============================================================================

@dataclass
class NameOrder(Order):
    """
    Name an unnamed unit, converting it to a character.

    Attributes:
        actor_id: Character issuing the order (group leader)
        unit_type: Type of unit to name (soldier/sailor/worker)
        gender: Gender of the new character (male/female)
        new_name: Name to give the character (8-32 chars)
    """
    actor_id: str = ""
    unit_type: str = ""  # UnitType
    gender: str = ""  # male or female
    new_name: str = ""

    def order_type(self) -> str:
        return "NAME"


@dataclass
class PromoteOrder(Order):
    """
    Promote/change the title of a named character.

    Attributes:
        character_ids: List of character IDs to promote
        character_names: Original names from text (for reporting)
        new_title: New title for the character(s)
    """
    character_ids: list[str] = field(default_factory=list)
    character_names: list[str] = field(default_factory=list)
    new_title: str = ""

    def order_type(self) -> str:
        return "PROMOTE"


# ============================================================================
# PRISONER/COMBAT ORDERS
# ============================================================================

@dataclass
class CaptureOrder(Order):
    """
    Attempt to capture enemy characters as prisoners.

    Similar to ATTACK but tries to capture rather than kill.

    Attributes:
        actor_id: Character doing the capturing
        target_ids: List of target character IDs to capture
        target_names: Original names from text (for reporting)
    """
    actor_id: str = ""
    target_ids: list[str] = field(default_factory=list)
    target_names: list[str] = field(default_factory=list)

    def order_type(self) -> str:
        return "CAPTURE"


@dataclass
class FreeOrder(Order):
    """
    Free prisoners held by this character.

    Attributes:
        actor_id: Character freeing the prisoners
        prisoner_ids: List of prisoner IDs to free
        prisoner_names: Original names from text (for reporting)
    """
    actor_id: str = ""
    prisoner_ids: list[str] = field(default_factory=list)
    prisoner_names: list[str] = field(default_factory=list)

    def order_type(self) -> str:
        return "FREE"


# ============================================================================
# ECONOMIC ORDERS
# ============================================================================

@dataclass
class TaxOrder(Order):
    """
    Collect taxes from a location.

    Attributes:
        actor_id: Character collecting taxes
        city_id: City where taxes are collected (actor's location)
        duration_days: Number of days to collect (alpha: simplified to 1 turn)
    """
    actor_id: str = ""
    city_id: str = ""
    duration_days: int = 7  # Default 1 week

    def order_type(self) -> str:
        return "TAX"


# ============================================================================
# TRAINING ORDERS
# ============================================================================

@dataclass
class StudyOrder(Order):
    """
    Study a skill to increase its level.

    Costs 1 gold per week. Skills increase by 1-5 partial points per week.

    Attributes:
        actor_id: Character studying
        skill_name: Skill to study (combat, magic, religion)
        duration_weeks: Number of weeks to study (default 1)
        target_level: Optional target level to reach
    """
    actor_id: str = ""
    skill_name: str = ""  # "combat", "magic", "religion"
    duration_weeks: int = 1
    target_level: int = 0  # 0 means not set

    def order_type(self) -> str:
        return "STUDY"


@dataclass
class TeachOrder(Order):
    """
    Have one character teach another a skill.

    No cost, but teacher must have higher skill level.

    Attributes:
        teacher_id: Character teaching
        student_id: Character learning
        skill_name: Skill to teach (combat, magic, religion)
        duration_weeks: Number of weeks to teach (default 1)
        target_level: Optional target level for student
    """
    teacher_id: str = ""
    student_id: str = ""
    skill_name: str = ""  # "combat", "magic", "religion"
    duration_weeks: int = 1
    target_level: int = 0  # 0 means not set

    def order_type(self) -> str:
        return "TEACH"


# ============================================================================
# MAGIC SUMMONING ORDERS
# ============================================================================

@dataclass
class SummonOrder(Order):
    """
    Summon magical creatures.

    Attributes:
        summoner_id: Character summoning creatures
        creature_counts: Dict mapping creature type name to count
    """
    summoner_id: str = ""
    creature_counts: dict[str, int] = field(default_factory=dict)  # e.g., {"dragon": 2, "griffin": 1}

    def order_type(self) -> str:
        return "SUMMON"


# ============================================================================
# RESOURCE GATHERING ORDERS
# ============================================================================

@dataclass
class CollectOrder(Order):
    """
    Collect/gather resources (wood or stone).

    Attributes:
        actor_id: Character supervising the gathering
        resource_type: Type of resource to gather ("wood" or "stone")
        duration_days: Number of days to gather (default 7)
        target_amount: Optional target amount to gather (0 = use duration)
    """
    actor_id: str = ""
    resource_type: str = ""  # "wood" or "stone"
    duration_days: int = 7  # Default 1 week
    target_amount: int = 0  # 0 means use duration instead

    def order_type(self) -> str:
        return "COLLECT"


@dataclass
class BuildOrder(Order):
    """
    Build/construct items from raw materials.

    Attributes:
        actor_id: Character supervising the construction (lead engineer)
        item_type: Type of item to build ("galley", "catapult", etc.)
        count: Number of items to build
        duration_days: Optional duration limit (0 = build until complete)
    """
    actor_id: str = ""
    item_type: str = ""  # "galley", "catapult", etc.
    count: int = 1
    duration_days: int = 0  # 0 means no time limit (alpha: instant)

    def order_type(self) -> str:
        return "BUILD"


@dataclass
class MineOrder(Order):
    """
    Mine for minerals (iron, gold, silver, copper, gems).

    Attributes:
        actor_id: Character supervising the mining (lead miner)
        resource_type: Type of mineral to mine ("iron", "gold", "silver", "copper", "gems")
        duration_days: Number of days to mine (default 7)
        target_amount: Optional target amount to mine (0 = use duration)
    """
    actor_id: str = ""
    resource_type: str = ""  # "iron", "gold", "silver", "copper", "gems"
    duration_days: int = 7  # Default 1 week
    target_amount: int = 0  # 0 means use duration instead

    def order_type(self) -> str:
        return "MINE"


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
        "CAPTURE": CaptureOrder,
        "TELEPORT": TeleportOrder,
        "FLY": FlyOrder,
        "HEAL": HealOrder,
        "SECURE": SecureOrder,
        "ALLY": AllyOrder,
        "ENEMY": EnemyOrder,
        "NEUTRAL": NeutralOrder,
        "ASSIGN": AssignOrder,
        "GIVE": AssignOrder,  # GIVE is synonym for ASSIGN
        "NAME": NameOrder,
        "PROMOTE": PromoteOrder,
        "TAX": TaxOrder,
        "FREE": FreeOrder,
        "RELEASE": FreeOrder,  # RELEASE is synonym for FREE
        "DISCARD": FreeOrder,  # DISCARD is synonym for FREE
        "DISMISS": FreeOrder,  # DISMISS is synonym for FREE
        "STUDY": StudyOrder,
        "TEACH": TeachOrder,
        "SUMMON": SummonOrder,
        "COLLECT": CollectOrder,
        "GATHER": CollectOrder,  # GATHER is synonym for COLLECT
        "BUILD": BuildOrder,
        "CONSTRUCT": BuildOrder,  # CONSTRUCT is synonym for BUILD
        "MAKE": BuildOrder,  # MAKE is synonym for BUILD
        "MINE": MineOrder,
    }

    order_class = order_map.get(order_type.upper())
    if order_class:
        return order_class(player_id=player_id, original_text=original_text)
    return None
