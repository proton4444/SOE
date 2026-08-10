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
        explicit_actor: True when the order named its actor rather than falling
            back to the faction leader -- the HAVE form. `rules.md` makes that
            character a group leader, so the engine has to know which it was.
    """
    player_id: str
    original_text: str = ""
    warnings: list[str] = field(default_factory=list)
    explicit_actor: bool = False
    # True when the order was written with `quietly`/`silently`, meaning the
    # rules want its results suppressed on the status report. Parsed and
    # recorded; report suppression is not implemented yet.
    silent: bool = False
    # True when the parser filled `city_id` from wherever the actor happened to
    # be standing, because the order named no city. That fill is only a guess:
    # "go to Kitesta and recruit 10 soldiers" is parsed before the move runs,
    # so execution re-reads the actor's real location. Default False keeps an
    # order built in code, or restored from an older save, taken at its word.
    city_implicit: bool = False

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
        destination_position: inside / outside / near on arrival
        path: Optional explicit path (list of city IDs)
    """
    actor_id: str = ""
    destination_city_id: str = ""
    destination_position: str = "inside"  # LocationPosition value
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
    target_character_id: str = ""
    stance: str = "normal"
    definitely: bool = False

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
        wand_name: Wand named with `with`/`using`. rules.md: a wand is never
            used automatically, so an empty name means the caster's own power.
    """
    actor_id: str = ""
    target_character_id: str = ""
    destination_city_id: str = ""
    target_name: str = ""
    wand_name: str = ""

    def order_type(self) -> str:
        return "TELEPORT"


@dataclass
class FlyOrder(Order):
    """
    Order a magic user to fly (self and group) to a destination.

    Attributes:
        actor_id: Magic user who will cast the spell (must be group leader)
        destination_city_id: Destination city ID
        wand_name: Wand named with `with`/`using`, if any.
    """
    actor_id: str = ""
    destination_city_id: str = ""
    wand_name: str = ""

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


@dataclass
class PrayOrder(Order):
    """Pray for divine intervention or donations."""

    actor_id: str = ""
    intent: str = ""  # donation, protection, miracle

    def order_type(self) -> str:
        return "PRAY"


@dataclass
class BlessOrder(Order):
    """Bless allies at a location to improve their morale and combat."""

    actor_id: str = ""
    city_id: str = ""
    bonus: int = 5

    def order_type(self) -> str:
        return "BLESS"


@dataclass
class CurseOrder(Order):
    """Curse enemies at a location to weaken their combat."""

    actor_id: str = ""
    city_id: str = ""
    penalty: int = 5

    def order_type(self) -> str:
        return "CURSE"


@dataclass
class ResurrectOrder(Order):
    """Attempt to resurrect a fallen character."""

    actor_id: str = ""
    target_id: str = ""
    target_name: str = ""

    def order_type(self) -> str:
        return "RESURRECT"


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


@dataclass
class FortifyOrder(Order):
    """Build or improve fortifications at the current location."""

    actor_id: str = ""
    city_id: str = ""
    percent: int = 10

    def order_type(self) -> str:
        return "FORTIFY"


@dataclass
class UnfortifyOrder(Order):
    """Remove fortifications from a location."""

    actor_id: str = ""
    city_id: str = ""
    percent: int = 10

    def order_type(self) -> str:
        return "UNFORTIFY"


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
        character_ids: Named characters being assigned into the recipient's
            group. They bring their own subordinates with them.
        character_names: The names those ids were resolved from, for reporting
        item_ids: Magical items being handed over. rules.md gives items by
            name -- "Give Wameka to Joe Flint" -- so a GIVE may name an item
            where it would otherwise name a character.
        item_names: The names those ids were resolved from, for reporting
        resources: Mass-noun quantities moving with the transfer -- "Give 50
            armor to Thomas Ames" is 50 armor, and "give 10 stone to Carl
            Higgins" is 10 stone. Wood, stone, iron, silver, copper, gems
            and armor, keyed by name.
    """
    donor_id: str = ""
    recipient_id: str = ""
    unit_type: str = ""  # UnitType or empty string
    unit_count: int = 0
    gold_amount: int = 0
    character_ids: list[str] = field(default_factory=list)
    character_names: list[str] = field(default_factory=list)
    item_ids: list[str] = field(default_factory=list)
    item_names: list[str] = field(default_factory=list)
    resources: dict[str, int] = field(default_factory=dict)
    elite_unit_ids: list[str] = field(default_factory=list)
    elite_unit_names: list[str] = field(default_factory=list)

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


@dataclass
class TradeOrder(Order):
    """
    Buy or sell goods leveraging trading skill.

    Note there is deliberately no price field: unit prices are set by
    `config.RESOURCE_BASE_PRICE` and adjusted by the trader's skill. Letting an
    order carry its own price would let a player name what their goods sell for.
    """

    actor_id: str = ""
    city_id: str = ""
    resource_type: str = ""
    amount: int = 0
    action: str = "buy"  # buy or sell

    def order_type(self) -> str:
        return "TRADE"


@dataclass
class AwaitOrder(Order):
    """
    Hold this character's queue until a wait is satisfied.

    `duration_days` is how long to wait. `target_id`, when set, waits instead for
    another character to reach the actor's city (`WAIT FOR <person>`), and the
    duration becomes a deadline: the wait ends early if the target arrives, and
    gives up when the deadline passes (`WAIT ... UNTIL`).
    """

    actor_id: str = ""
    duration_days: int = 7
    target_id: str = ""
    duration_hours: int = 0

    def order_type(self) -> str:
        return "AWAIT"


@dataclass
class RepeatOrder(Order):
    """
    Repeat the orders that follow it, for the same character, in a loop.

    `times` is the total number of passes. Zero or less means loop until a HALT
    or STOP, which is what a bare `repeatedly` means in `rules.md`.
    """

    actor_id: str = ""
    times: int = 0

    def order_type(self) -> str:
        return "REPEAT"


@dataclass
class JoinOrder(Order):
    """
    Join another character's group, bringing your own subordinates along.

    `rules.md`: JOIN does the same thing as ASSIGN, but is given to the
    character being assigned rather than to the one doing the assigning, so
    they can finish other work first.
    """

    actor_id: str = ""
    target_id: str = ""
    target_name: str = ""

    def order_type(self) -> str:
        return "JOIN"


@dataclass
class SupportOrder(Order):
    """
    Fight alongside somebody when they attack.

    `rules.md`: the supporter joins the battle "as if they had given the same
    ATTACK/CAPTURE order at exactly the same time", but stays a separate group,
    so their leadership does not benefit the person they are supporting. With no
    duration the agreement stands until a HALT or STOP.
    """

    actor_id: str = ""
    target_ids: list[str] = field(default_factory=list)
    target_names: list[str] = field(default_factory=list)
    duration_days: int = 0  # 0 = until halted

    def order_type(self) -> str:
        return "SUPPORT"


@dataclass
class HaltOrder(Order):
    """
    Unplanned stop: drop this character's queued orders as soon as it arrives.

    `immediate` also abandons a wait that is already running, matching the
    "immediately halt" form in `rules.md`.
    """

    actor_id: str = ""
    immediate: bool = False

    def order_type(self) -> str:
        return "HALT"


@dataclass
class StopOrder(Order):
    """
    Planned stop: queued in sequence, and clears whatever is behind it.

    Unlike HALT this waits its turn, so it stops the character at a point the
    player planned for rather than the moment the order was written.
    """

    actor_id: str = ""
    immediate: bool = False

    def order_type(self) -> str:
        return "STOP"


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


@dataclass
class KillOrder(Order):
    """Kill / execute a prisoner held by the actor."""

    actor_id: str = ""
    prisoner_ids: list[str] = field(default_factory=list)
    prisoner_names: list[str] = field(default_factory=list)

    def order_type(self) -> str:
        return "KILL"


@dataclass
class EnslaveOrder(Order):
    """Convert a prisoner into an unnamed slave labour unit."""

    actor_id: str = ""
    prisoner_ids: list[str] = field(default_factory=list)
    prisoner_names: list[str] = field(default_factory=list)

    def order_type(self) -> str:
        return "ENSLAVE"


@dataclass
class InterrogateOrder(Order):
    """Torture a prisoner for information about their faction / leader."""

    actor_id: str = ""
    prisoner_ids: list[str] = field(default_factory=list)
    prisoner_names: list[str] = field(default_factory=list)
    duration_days: int = 7

    def order_type(self) -> str:
        return "INTERROGATE"


@dataclass
class NoncomOrder(Order):
    """Mark characters as non-combatants (or restore combatant status)."""

    character_ids: list[str] = field(default_factory=list)
    character_names: list[str] = field(default_factory=list)
    set_noncom: bool = True  # False => COMBATANT

    def order_type(self) -> str:
        return "NONCOM" if self.set_noncom else "COMBATANT"


@dataclass
class LurkOrder(Order):
    """Start or stop lurking (stealth)."""

    actor_id: str = ""
    set_lurking: bool = True  # False => UNLURK

    def order_type(self) -> str:
        return "LURK" if self.set_lurking else "UNLURK"


@dataclass
class ProbeOrder(Order):
    """
    Magically learn a full report of another player's character.

    Costs 25 magic power whether it succeeds or not. Base success chance is
    the caster's magic skill; the target resists with their effective skill.
    """
    actor_id: str = ""
    target_id: str = ""
    target_name: str = ""
    wand_name: str = ""

    def order_type(self) -> str:
        return "PROBE"


@dataclass
class SearchOrder(Order):
    """
    Search/explore uninhabited ruins at the actor's current location.

    EXPLORE is a synonym. Duration is recorded for future sub-turn time; the
    alpha engine treats every search as one turn of effort.
    """
    actor_id: str = ""
    duration_days: int = 7

    def order_type(self) -> str:
        return "SEARCH"


@dataclass
class ScanOrder(Order):
    """
    Use a magical orb to report who is at a distant city.

    The orb must be named in the order and possessed by the actor. It spends
    its own power on the distance and reports everyone inside or outside the
    city — but never those merely near it.
    """
    actor_id: str = ""
    city_ids: list[str] = field(default_factory=list)
    city_names: list[str] = field(default_factory=list)
    orb_name: str = ""

    def order_type(self) -> str:
        return "SCAN"


@dataclass
class MessageOrder(Order):
    """
    SAY or TELL: give a message to other players.

    The two verbs differ only in word order -- `tell <who> "..."` against
    `say "..." to <who>` -- so they share one order type. A message may go to
    named characters of any faction, to everyone at a city, or to every player
    in the game.

    Attributes:
        message: The text, exactly as the player typed it. Quoted spans are
            protected from the parser's lowercasing, so case survives.
        recipient_ids: Named characters, who may belong to any faction.
        recipient_city_id: Set when the message is broadcast to a town.
        to_everyone: Set by the `everyone` form, which reaches all players.
    """
    actor_id: str = ""
    message: str = ""
    recipient_ids: list[str] = field(default_factory=list)
    recipient_names: list[str] = field(default_factory=list)
    recipient_city_id: str = ""
    recipient_city_name: str = ""
    to_everyone: bool = False

    def order_type(self) -> str:
        return "SAY"


@dataclass
class PostOrder(Order):
    """
    Nail a message to the gates of a city your faction has secured.

    An empty message takes the posting down, which is the rules' way of
    clearing one. The posting also lapses on its own when the faction stops
    securing the location.
    """
    actor_id: str = ""
    message: str = ""

    def order_type(self) -> str:
        return "POST"


@dataclass
class ReportOrder(Order):
    """
    REPORT or QUERY: ask a character what they can see.

    rules.md: QUERY does exactly what REPORT does, except that it reaches a
    subordinate who is busy -- so `immediate` is what separates the two verbs.
    `brief` is the `briefly` adverb, which drops skills and the list of other
    people at the location.
    """
    actor_id: str = ""
    subject_ids: list[str] = field(default_factory=list)
    subject_names: list[str] = field(default_factory=list)
    brief: bool = False
    immediate: bool = False

    def order_type(self) -> str:
        return "QUERY" if self.immediate else "REPORT"


@dataclass
class AddressOrder(Order):
    """Change where this player's reports are sent."""
    address: str = ""

    def order_type(self) -> str:
        return "ADDRESS"


@dataclass
class PasswordOrder(Order):
    """
    Change this player's password.

    rules.md: between 8 and 64 characters. Anything shorter is replaced by a
    generated one, and anything longer is truncated.
    """
    password: str = ""
    generated: bool = False

    def order_type(self) -> str:
        return "PASSWORD"


@dataclass
class ConjureOrder(Order):
    """
    Attempt to conjure a magical item for temporary use.

    Spends *all* of the caster's magic power, including anything in their
    crystals, and the chance of success as a percentage equals the power
    expended. Requires magic skill 25. `skill` is set when conjuring an amulet
    and `spell` when conjuring a wand; the rules require naming those.
    """
    actor_id: str = ""
    item_type: str = ""   # ItemType value
    skill: str = ""       # amulet only
    spell: str = ""       # wand only

    def order_type(self) -> str:
        return "CONJURE"


@dataclass
class ItemPowerTransfer:
    """
    One item named by a CHARGE or ABSORB order, and how much power to move.

    A single order may name several items with different quantities each --
    "Charge Ampu to 75 power and Wasute by 7 power" -- so the quantity and the
    preposition that set it belong to the item, not to the order.

    Attributes:
        amount: Points to move, or -1 for as much as possible (which is what an
            unqualified order, `all` and `everything` all mean).
        to_level: CHARGE only. False for `by` (add this much), True for `to`
            (bring the item up to this level).
    """
    item_id: str = ""
    item_name: str = ""
    amount: int = -1
    to_level: bool = False


@dataclass
class ChargeOrder(Order):
    """
    Transfer magic power from a magic-user into crystals, orbs or wands.

    RECHARGE is a synonym. The actor need not possess the items, as long as
    whoever does is in the same location and the same faction.
    """
    actor_id: str = ""
    targets: list[ItemPowerTransfer] = field(default_factory=list)

    def order_type(self) -> str:
        return "CHARGE"


@dataclass
class AbsorbOrder(Order):
    """
    Transfer magic power from crystals, orbs or wands back to a magic-user.

    The mirror of CHARGE, with the same reach rule about items held by another
    character in the same place.
    """
    actor_id: str = ""
    targets: list[ItemPowerTransfer] = field(default_factory=list)

    def order_type(self) -> str:
        return "ABSORB"


@dataclass
class GetOrder(Order):
    """
    Take gold/units from a donor (inverse of ASSIGN/GIVE).

    Actor is the recipient. Donor must be the same faction (or a prisoner
    under the actor's control).
    """
    actor_id: str = ""  # recipient
    donor_id: str = ""
    unit_type: str = ""
    unit_count: int = 0
    gold_amount: int = 0
    resources: dict[str, int] = field(default_factory=dict)

    def order_type(self) -> str:
        return "GET"


@dataclass
class TransferOrder(Order):
    """Transfer gold via the banking guild (fee applied)."""

    actor_id: str = ""
    recipient_id: str = ""
    gold_amount: int = 0  # 0 means transfer all

    def order_type(self) -> str:
        return "TRANSFER"


@dataclass
class UnloadOrder(Order):
    """
    Detach a co-located character so they act as their own group leader.

    Full group mechanics are still thin in alpha; this records independence
    for reporting and future queue work.
    """
    actor_id: str = ""
    target_ids: list[str] = field(default_factory=list)
    target_names: list[str] = field(default_factory=list)

    def order_type(self) -> str:
        return "UNLOAD"


@dataclass
class PayOrder(Order):
    """Pay down wage debt (or create a surplus credit)."""

    actor_id: str = ""
    gold_amount: int = 0  # 0 means pay as much debt as gold allows

    def order_type(self) -> str:
        return "PAY"


@dataclass
class BorrowOrder(Order):
    """Borrow gold from the bankers guild."""

    actor_id: str = ""
    gold_amount: int = 0  # 0 means borrow as much as possible (alpha cap)

    def order_type(self) -> str:
        return "BORROW"


@dataclass
class RepayOrder(Order):
    """Repay bankers-guild debt."""

    actor_id: str = ""
    gold_amount: int = 0  # 0 means repay as much as gold allows

    def order_type(self) -> str:
        return "REPAY"


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
        stated_city_id: The city the player wrote into the order, if any. TAX
            always collects where the character stands, so this is not a target
            -- it is what the order claimed, and execution refuses when the
            character turns out to be somewhere else.
    """
    actor_id: str = ""
    city_id: str = ""
    duration_days: int = 7  # Default 1 week
    stated_city_id: str = ""

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
        wand_name: Wand named with `with`/`using`, if any.
    """
    summoner_id: str = ""
    creature_counts: dict[str, int] = field(default_factory=dict)  # e.g., {"dragon": 2, "griffin": 1}
    wand_name: str = ""

    def order_type(self) -> str:
        return "SUMMON"


@dataclass
class ScryOrder(Order):
    """Use magic to scout a location and reveal information."""

    actor_id: str = ""
    city_id: str = ""

    def order_type(self) -> str:
        return "SCRY"


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
# V1.1 ORDERS: WORK, TRAIN, UNNAME, CREATE, INVEST, PASSAGE, PREACH, OFFER, IF
# ============================================================================

@dataclass
class WorkOrder(Order):
    """Work for wages. The actor and their group do common labour for the
    location's daily rate; high-skill characters also sell their skills.

    Attributes:
        actor_id: Character doing the work
        duration_days: How long to work (default 7)
    """
    actor_id: str = ""
    duration_days: int = 7

    def order_type(self) -> str:
        return "WORK"


@dataclass
class TrainOrder(Order):
    """Train workers into soldiers or sailors. The trainer needs combat or
    sailing skill (respectively) of at least 10.

    Attributes:
        actor_id: The trainer
        unit_type: What to train ("soldier" or "sailor")
        count: How many workers to convert; 0 means every worker in the group
    """
    actor_id: str = ""
    unit_type: str = "soldier"
    count: int = 0

    def order_type(self) -> str:
        return "TRAIN"


@dataclass
class UnnameOrder(Order):
    """Convert a named character back to a common worker. The character must
    be part of a group and have nothing of their own; the resulting worker is
    assigned to the group leader.

    Attributes:
        actor_id: The character giving the order (the group leader)
        target_id: The character to unname
    """
    actor_id: str = ""
    target_id: str = ""

    def order_type(self) -> str:
        return "UNNAME"


@dataclass
class CreateOrder(Order):
    """Create an elite troop unit from soldiers of the actor's group.

    Attributes:
        actor_id: The character forming the unit (its group leader)
        unit_name: The unit's name, e.g. "gordy's killers"
        count: Number of soldiers to fold into the unit
    """
    actor_id: str = ""
    unit_name: str = ""
    count: int = 0

    def order_type(self) -> str:
        return "CREATE"


@dataclass
class DisbandOrder(Order):
    """Return an elite unit's surviving soldiers to its leader's group."""
    actor_id: str = ""
    elite_unit_id: str = ""
    elite_unit_name: str = ""

    def order_type(self) -> str:
        return "DISBAND"


@dataclass
class InvestOrder(Order):
    """Invest gold in a town's growth. The investor need not be present.

    Attributes:
        actor_id: The character spending the gold
        city_id: The town to invest in
        amount: Gold to invest; -1 means everything the actor has
    """
    actor_id: str = ""
    city_id: str = ""
    amount: float = 0.0

    def order_type(self) -> str:
        return "INVEST"


@dataclass
class PassageOrder(Order):
    """Buy passage on a merchant ship: travel one direct sealane hop without
    owning a galley.

    Attributes:
        actor_id: The traveller (their group comes along)
        destination_city_id: One-hop destination connected by a sealane
        definitely: The `definitely` adverb, which improves the odds
    """
    actor_id: str = ""
    destination_city_id: str = ""
    definitely: bool = False

    def order_type(self) -> str:
        return "PASSAGE"


@dataclass
class PreachOrder(Order):
    """Preach and collect tithes. Donations scale with religion skill and
    location population; followers sometimes join.

    Attributes:
        actor_id: The preacher
        duration_days: How long to preach (default 7)
    """
    actor_id: str = ""
    duration_days: int = 7

    def order_type(self) -> str:
        return "PREACH"


@dataclass
class OfferOrder(Order):
    """Offer gold to an independent character (or one of your prisoners) to
    join your faction.

    Attributes:
        actor_id: The character making the offer
        target_id: The offeree
        amount: Gold offered; -1 means everything the actor has
    """
    actor_id: str = ""
    target_id: str = ""
    amount: float = 0.0

    def order_type(self) -> str:
        return "OFFER"


@dataclass
class IfOrder(Order):
    """A conditional statement: `if <condition> then <orders>` with an
    optional `otherwise`/`else` branch. The condition is evaluated when the
    order is reached on the queue, and only the chosen branch runs.

    Attributes:
        actor_id: The character the condition is tested about (for the
            report); branch orders carry their own actors
        condition: The parsed condition being tested
        then_orders: Orders to run when the condition holds
        else_orders: Orders to run otherwise
    """
    actor_id: str = ""
    condition: dict = None
    then_orders: list = field(default_factory=list)
    else_orders: list = field(default_factory=list)

    def order_type(self) -> str:
        return "IF"


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
        "SCRY": ScryOrder,
        "COLLECT": CollectOrder,
        "GATHER": CollectOrder,  # GATHER is synonym for COLLECT
        "BUILD": BuildOrder,
        "CONSTRUCT": BuildOrder,  # CONSTRUCT is synonym for BUILD
        "MAKE": BuildOrder,  # MAKE is synonym for BUILD
        "MINE": MineOrder,
        "WORK": WorkOrder,
        "TRAIN": TrainOrder,
        "UNNAME": UnnameOrder,
        "CREATE": CreateOrder,
        "DISBAND": DisbandOrder,
        "INVEST": InvestOrder,
        "PASSAGE": PassageOrder,
        "PREACH": PreachOrder,
        "OFFER": OfferOrder,
        "IF": IfOrder,
        "FORTIFY": FortifyOrder,
        "UNFORTIFY": UnfortifyOrder,
        "PRAY": PrayOrder,
        "BLESS": BlessOrder,
        "CURSE": CurseOrder,
        "RESURRECT": ResurrectOrder,
        "TRADE": TradeOrder,
        "AWAIT": AwaitOrder,
        "WAIT": AwaitOrder,
        "REPEAT": RepeatOrder,
        "HALT": HaltOrder,
        "STOP": StopOrder,
        "JOIN": JoinOrder,
        "SUPPORT": SupportOrder,
        "COME": MoveOrder,  # rules.md: "COME -- see the GO command"
        "KILL": KillOrder,
        "EXECUTE": KillOrder,
        "ENSLAVE": EnslaveOrder,
        "INTERROGATE": InterrogateOrder,
        "NONCOM": NoncomOrder,
        "COMBATANT": NoncomOrder,
        "LURK": LurkOrder,
        "UNLURK": LurkOrder,
        "PROBE": ProbeOrder,
        "SEARCH": SearchOrder,
        "EXPLORE": SearchOrder,
        "SCAN": ScanOrder,
        "SAY": MessageOrder,
        "TELL": MessageOrder,
        "POST": PostOrder,
        "REPORT": ReportOrder,
        "QUERY": ReportOrder,
        "ADDRESS": AddressOrder,
        "PASSWORD": PasswordOrder,
        "CONJURE": ConjureOrder,
        "CHARGE": ChargeOrder,
        "RECHARGE": ChargeOrder,
        "ABSORB": AbsorbOrder,
        "GET": GetOrder,
        "OBTAIN": GetOrder,
        "TAKE": GetOrder,
        "TRANSFER": TransferOrder,
        "UNLOAD": UnloadOrder,
        "PAY": PayOrder,
        "BORROW": BorrowOrder,
        "REPAY": RepayOrder,
        "HIRE": RecruitOrder,
    }

    order_class = order_map.get(order_type.upper())
    if order_class:
        return order_class(player_id=player_id, original_text=original_text)
    return None


# ============================================================================
# ORDER QUEUE
# ============================================================================

@dataclass
class QueueEntry:
    """
    One slot in a character's persistent order queue.

    Most entries just carry an order. A REPEAT entry is a loop marker instead:
    `block` holds a pristine copy of the loop body and `repeat_remaining` counts
    the passes still owed (-1 for a loop that only HALT or STOP can end). An
    AWAIT entry records the turn its wait expires in `release_turn`.

    `order_class` is written on construction so the queue can be rebuilt from a
    save file: JSON keeps no record of which Order subclass a dict came from.
    """

    order: Optional[Order] = None
    order_class: str = ""
    release_turn: int = -1
    repeat_remaining: int = 0
    block: list["QueueEntry"] = field(default_factory=list)
    # Absolute hour deadline. ``release_turn`` remains for old save files and
    # is migrated when a queue entry is first examined.
    release_hour: int = -1
    check_hour: int = -1

    def __post_init__(self):
        if self.order is not None and not self.order_class:
            self.order_class = type(self.order).__name__


# Most orders name their acting character in `actor_id`; a few use a
# role-specific field because the order has two characters in it.
ACTOR_FIELDS: dict[str, str] = {
    "AssignOrder": "donor_id",
    "SummonOrder": "summoner_id",
    "TeachOrder": "teacher_id",
}


def actor_field(order: Order) -> str:
    """Name of the field holding this order's acting character."""
    return ACTOR_FIELDS.get(type(order).__name__, "actor_id")


def actor_id_of(order: Order) -> str:
    """The acting character's id, or "" for an order that names none."""
    return getattr(order, actor_field(order), "") or ""


def order_classes() -> dict[str, type]:
    """
    Every concrete Order subclass, keyed by class name.

    Used to rebuild queued orders from a save file. Keyed by class rather than
    by `order_type()` because several verbs share one class (KILL and EXECUTE,
    GET and TAKE), so `order_type` is not a round-trippable identity.
    """
    found: dict[str, type] = {}

    def walk(cls: type) -> None:
        for subclass in cls.__subclasses__():
            found[subclass.__name__] = subclass
            walk(subclass)

    walk(Order)
    return found
