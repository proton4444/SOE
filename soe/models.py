"""
Domain models for the SOE game.

This module defines all core game entities: cities, roads, factions,
characters, units, ships, and the overall game state.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from soe.orders import QueueEntry


# ============================================================================
# ENUMS
# ============================================================================

class PopulationBand(str, Enum):
    """Population size categories for cities.

    The tiers are the gamemaster's own, from the legend of the original
    map: >100k / 10k-99,999 / 1k-9,999 / <1k. The world's largest town is
    134,000, so bands pitched at real-world city sizes left ``1M+`` empty
    and lumped 128 of the 154 towns into a single bottom band.
    """
    TINY = "< 1k"            # Less than 1,000 -- a village
    SMALL = "1k-9k"          # 1,000 to 9,999
    MEDIUM = "10k-99k"       # 10,000 to 99,999
    LARGE = "100k+"          # 100,000 or more

    @classmethod
    def _missing_(cls, value):
        """Accept the pre-retier band names found in saved games.

        Each legacy band is mapped to the band its old midpoint now falls
        in, so a city loaded from an old save keeps the size it had.
        """
        return _LEGACY_POPULATION_BANDS.get(value)


# Old value -> new band, by where the old band's midpoint lands.
_LEGACY_POPULATION_BANDS = {
    "< 10k": PopulationBand.SMALL,        # old midpoint 5,000
    "100k-999k": PopulationBand.LARGE,    # old midpoint 550,000
    "1M+": PopulationBand.LARGE,
}


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
    SLAVE = "slave"          # Former prisoner; labour only


class ShipType(str, Enum):
    """Types of ships."""
    GALLEY = "galley"        # Basic war/transport ship


class CreatureType(str, Enum):
    """Types of summoned magical creatures."""
    SKELETON = "skeleton"    # 1 magic power
    ZOMBIE = "zombie"        # 2 magic power
    HARPY = "harpy"          # 5 magic power
    MINOTAUR = "minotaur"    # 10 magic power
    GRIFFIN = "griffin"      # 20 magic power
    CHIMERA = "chimera"      # 30 magic power
    DRAGON = "dragon"        # 40 magic power
    DEMON = "demon"          # 50 magic power


class ResourceType(str, Enum):
    """Types of resources that can be gathered or mined."""
    WOOD = "wood"      # Gathered in forests
    STONE = "stone"    # Gathered in hills/mountains
    IRON = "iron"      # Mined in hills/mountains
    GOLD = "gold"      # Mined in hills/mountains
    SILVER = "silver"  # Mined in hills/mountains
    COPPER = "copper"  # Mined in hills/mountains
    GEMS = "gems"      # Mined in hills/mountains


# Design: "Titles are ignored except in the NAME and PROMOTE commands, where
# they are mandatory." A player writes "Assign 200 soldiers to Captain Bill
# Jones" and means Bill Jones, so a leading title word is dropped before the
# name lookup. Defined here (rather than in the parser) so the pronoun pass,
# which runs before the parsers, can strip them too.
TITLE_WORDS = frozenset((
    "captain", "wizard", "bishop", "engineer", "trader", "adept", "king",
    "queen", "prince", "princess", "lord", "lady", "baron", "baroness",
    "major", "sergeant", "primate", "abbot", "duke", "earl", "count",
    "countess", "chief", "priest", "priestess", "sage", "master", "doctor",
))


class ItemType(str, Enum):
    """
    The five kinds of magical item in the design.

    All were made by one enchantress long ago and are indestructible, so items
    are never destroyed — they change hands, or (if conjured) expire.
    """
    AMULET = "amulet"    # Grants a skill up to a level
    CRYSTAL = "crystal"  # Stores magic power; tapped before natural power
    ORB = "orb"          # SCAN a distant location; provides its own power
    RING = "ring"        # Divides an attacker's hit chance in combat
    WAND = "wand"        # Provides both the skill and the power for one spell


class LocationPosition(str, Enum):
    """
    Where a character stands relative to a city's gates.

    Design: inside (default), outside the gates, or near (hiding in the
    countryside). Visibility between people depends on both positions.
    """
    INSIDE = "inside"
    OUTSIDE = "outside"
    NEAR = "near"


# ============================================================================
# MAP & GEOGRAPHY
# ============================================================================

@dataclass
class City:
    """
    A location on the map (city, town, or ruin).

    Attributes:
        id: Unique identifier (e.g., "highfell")
        name: Human-readable name (e.g., "Highfell")
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
    is_ruin: bool = False  # Uninhabited ruins: SEARCH/EXPLORE may find items
    is_magic_free: bool = False  # Magic power cannot exist here, in people or items
    # Grid reference from the gamemaster's map, e.g. "A6" (original SOE map
    # index style). Display only; movement uses the roads graph.
    grid_ref: Optional[str] = None
    fortification_level: int = 0  # 0-100 defensive bonus
    resource_richness: dict[str, float] = field(default_factory=dict)
    # Numeric population, set from the map or by INVEST growth. None means
    # "not measured yet": helpers fall back to the population-band midpoint,
    # and the first weekly investment check makes it concrete.
    population: Optional[int] = None
    # Optional presentation coordinates (0..1 fractions of the map). Used by
    # the web map view; the engine ignores them for movement and rules.
    x: Optional[float] = None
    y: Optional[float] = None
    # Renewable stock remaining for each gatherable resource. Missing entries
    # are initialized from richness on first extraction for old maps/saves.
    resource_reserves: dict[str, float] = field(default_factory=dict)

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
        distance_miles: Length of the route in miles, from the gamemaster's
            map. The rules price travel time and scan/teleport power from
            this; when absent the engine falls back to quality-only cost.
    """
    id: str
    from_city_id: str
    to_city_id: str
    quality: RoadQuality
    bidirectional: bool = True
    distance_miles: Optional[float] = None


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
        treasury: Legacy faction-level gold pool. New gold lives on
            Character.gold; this field is kept so old saves and dual-debit
            spending still work until fully migrated.
        wage_debt: Unpaid wages owed to subordinates (settled with PAY).
        loan_balance: Outstanding bankers-guild debt (BORROW / REPAY).
        loan_grace_turns: Turns remaining before minimum repayments are due.
        allies: Set of faction IDs that are allies
        enemies: Set of faction IDs that are enemies
        email: Where reports are sent. Changed with ADDRESS.
        password: Proves a submission really came from this player. Changed
            with PASSWORD. Stored as given; the rules make it case-insensitive,
            so comparisons must fold case rather than this field.

    Fortifications are *not* stored here. They belong to the city and are held
    on City.fortification_level, so they survive the city changing hands.
    """
    id: str
    name: str
    controlled_city_ids: set[str] = field(default_factory=set)
    secured_city_ids: set[str] = field(default_factory=set)
    treasury: float = 0.0
    wage_debt: float = 0.0
    loan_balance: float = 0.0
    loan_grace_turns: int = 0
    allies: set[str] = field(default_factory=set)
    enemies: set[str] = field(default_factory=set)
    email: str = ""
    password: str = ""
    # True for a computer-controlled faction (independent characters the
    # players can make offers to). NPC factions are never iterated as players.
    is_npc: bool = False


@dataclass
class Character:
    """
    A named character/hero with skills and abilities.

    Attributes:
        id: Unique identifier
        name: Character name (must be unique across game)
        faction_id: Owning faction
        location_city_id: Current location
        is_leader: Whether this character is the faction leader. The leader
            draws no salary and receives orders that name no actor. Exactly one
            character per faction should carry this flag.
        gender: Gender of character (male/female)
        title: Optional title (e.g., "primate", "bishop")
        is_prisoner: Whether this character is a prisoner
        captor_id: ID of character holding this prisoner (empty if not prisoner)
        group_leader_id: The character this one is assigned to. Empty means they
            lead their own group. Orders given to a leader carry their group
            along; see `groups`.
        supporting_id: Character this one has agreed to fight alongside, and
            `support_until_turn` is the turn that agreement lapses.
        gold: Personal purse. Rules track gold per character, not per faction.
        is_noncom: If True, stays out of combat unless named in ATTACK/CAPTURE.
        is_lurking: If True, trying to avoid detection; odds live in `fog`.
        location_position: inside / outside / near the current city.
        movement_points: Movement remaining this turn
        combat_skill: Combat skill level (0-100)
        magic_skill: Magic skill level (0-100)
        magic_power_current: Current magic power available
        religion_skill: Religion skill level (0-100)
        religious_power_current: Current religious power available
        health: Health (0-100, 100 = perfect health)
        is_dead: Whether character is dead (health = 0)
        resources: Dict mapping resource type to quantity (e.g., {"wood": 10, "stone": 5})
    """
    id: str
    name: str
    faction_id: str
    location_city_id: str
    is_leader: bool = False
    gender: str = "male"  # "male" or "female"
    title: str = ""  # Optional title (e.g., "primate", "bishop")
    is_prisoner: bool = False
    captor_id: str = ""  # ID of character holding this prisoner
    group_leader_id: str = ""  # Empty = leads their own group
    supporting_id: str = ""  # Character being fought alongside
    support_until_turn: int = -1  # Turn the support agreement lapses
    gold: float = 0.0
    is_noncom: bool = False
    is_lurking: bool = False
    location_position: LocationPosition = LocationPosition.INSIDE
    movement_points: int = 10  # Reset each turn
    combat_skill: int = 0
    magic_skill: int = 0
    magic_power_current: int = 0  # Max = magic_skill
    religion_skill: int = 0
    religious_power_current: int = 0  # Max = religion_skill
    trading_skill: int = 0
    sailing_skill: int = 0  # Rules: sailing proficiency, TRAIN sailors, etc.
    health: int = 100  # 0-100, 0 = dead
    is_dead: bool = False
    resources: dict[str, int] = field(default_factory=dict)  # Resource inventory
    morale: int = 100

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


def available_gold(character: Optional["Character"], faction: Optional["Faction"]) -> float:
    """
    Spendable gold for an action.

    Character purse first; faction.treasury remains as a legacy fall-back so
    saves and tests that only funded the treasury still work.
    """
    total = 0.0
    if character is not None:
        total += character.gold
    if faction is not None:
        total += faction.treasury
    return total


def debit_gold(character: Optional["Character"], faction: Optional["Faction"],
               amount: float) -> bool:
    """
    Spend `amount` gold from the character purse, then the faction treasury.

    Returns False without changing balances if there is not enough combined
    gold. Amounts are not rounded here; callers that care about display
    rounding should do it themselves.
    """
    if amount <= 0:
        return True
    if available_gold(character, faction) < amount - 1e-9:
        return False

    remaining = amount
    if character is not None and character.gold > 0:
        take = min(character.gold, remaining)
        character.gold -= take
        remaining -= take
    if remaining > 1e-9 and faction is not None:
        faction.treasury -= remaining
    return True


def credit_gold(character: Optional["Character"], amount: float,
                faction: Optional["Faction"] = None) -> None:
    """
    Credit gold to a character's purse.

    If no character is given (should be rare), fall back to the faction
    treasury so gold is never destroyed silently.
    """
    if amount <= 0:
        return
    if character is not None:
        character.gold += amount
    elif faction is not None:
        faction.treasury += amount


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
        owner_character_id: Character these units are assigned to. Empty means
            they belong to the faction at this location rather than to anyone in
            particular, which is where recruits land until someone is given
            them. Owned units travel with their owner.
    """
    id: str
    faction_id: str
    location_city_id: str
    unit_type: UnitType
    count: int
    owner_character_id: str = ""

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
class EliteUnit:
    """
    An elite troop unit, created by the CREATE command (the design).

    A unit is any number of soldiers under a name ("Green Berets"), fighting
    at a combat level of its own. It trains continuously -- `partial_level`
    grows every turn and every `ELITE_PARTIAL_PER_LEVEL` points become one
    full level -- with no teacher and no gold cost. A unit must belong to a
    named character's group (`leader_character_id`) and travels wherever that
    leader goes.

    Attributes:
        id: Unique identifier
        name: The unit's name, e.g. "gordy's killers"
        faction_id: Owning faction
        leader_character_id: The character whose group the unit belongs to
        location_city_id: Where the unit currently stands (synced to the
            leader's location each turn)
        size: Number of soldiers in the unit
        combat_level: The level every soldier in the unit fights at
        partial_level: Fraction of a level earned by constant training
    """
    id: str
    name: str
    faction_id: str
    leader_character_id: str = ""
    location_city_id: str = ""
    size: int = 0
    combat_level: int = 1
    partial_level: float = 0.0

    @property
    def attack_value(self) -> float:
        """Soldiers fighting at the unit's level, like a named character."""
        return self.size * (1 + self.combat_level * 0.01)

    @property
    def defense_value(self) -> float:
        return self.size * (1 + self.combat_level * 0.01)


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
    owner_character_id: str = ""

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


@dataclass
class SummonedCreature:
    """
    A summoned magical creature.

    Attributes:
        id: Unique identifier
        summoner_id: Character who summoned this creature
        creature_type: Type of creature
        count: Number of creatures
        expires_turn: Turn number when creature(s) disappear (0 = never)
    """
    id: str
    summoner_id: str
    creature_type: CreatureType
    count: int
    expires_turn: int = 0  # 0 means never expires (for alpha simplification)

    @property
    def magic_cost(self) -> int:
        """Magic power cost per creature."""
        costs = {
            CreatureType.SKELETON: 1,
            CreatureType.ZOMBIE: 2,
            CreatureType.HARPY: 5,
            CreatureType.MINOTAUR: 10,
            CreatureType.GRIFFIN: 20,
            CreatureType.CHIMERA: 30,
            CreatureType.DRAGON: 40,
            CreatureType.DEMON: 50,
        }
        return costs.get(self.creature_type, 0)

    @property
    def attack_value(self) -> int:
        """Total attack value of all creatures."""
        # Creatures are powerful fighters
        values = {
            CreatureType.SKELETON: 2,
            CreatureType.ZOMBIE: 3,
            CreatureType.HARPY: 8,
            CreatureType.MINOTAUR: 15,
            CreatureType.GRIFFIN: 30,
            CreatureType.CHIMERA: 45,
            CreatureType.DRAGON: 60,
            CreatureType.DEMON: 75,
        }
        return values.get(self.creature_type, 0) * self.count

    @property
    def defense_value(self) -> int:
        """Total defense value of all creatures."""
        # Creatures are hard to kill
        values = {
            CreatureType.SKELETON: 1,
            CreatureType.ZOMBIE: 2,
            CreatureType.HARPY: 6,
            CreatureType.MINOTAUR: 12,
            CreatureType.GRIFFIN: 25,
            CreatureType.CHIMERA: 40,
            CreatureType.DRAGON: 55,
            CreatureType.DEMON: 70,
        }
        return values.get(self.creature_type, 0) * self.count


@dataclass
class MagicalItem:
    """
    One of the enchantress's five kinds of magical item.

    Which fields matter depends on `item_type`, and the unused ones stay at
    their defaults:

    - AMULET  -- `skill` and `skill_level`. Never magic or religion.
    - CRYSTAL -- `power_current` / `power_max`.
    - ORB     -- `power_current`; `power_max` of 0 means no ceiling.
    - RING    -- `protection`.
    - WAND    -- `spell`, `power_current` / `power_max`, and `skill_level` as
                 the magic skill it lends its user.

    Attributes:
        id: Unique identifier
        name: The item's own name, e.g. "*Sarema*". Orders must use
            this name; the asterisks keep it from colliding with human names.
        holder_character_id: Who carries it. Empty means it is lying in a ruin
            waiting to be found.
        expires_turn: -1 for a permanent item (everything found by SEARCH).
            A conjured item returns whence it came at this turn number.
    """
    id: str
    name: str
    item_type: ItemType
    holder_character_id: str = ""
    power_current: int = 0
    power_max: int = 0
    skill: str = ""
    skill_level: int = 0
    spell: str = ""
    protection: int = 0
    expires_turn: int = -1

    @property
    def is_temporary(self) -> bool:
        """True for conjured items, which expire; found items last forever."""
        return self.expires_turn >= 0

    @property
    def holds_power(self) -> bool:
        """Crystals, orbs and wands store power. Amulets and rings do not."""
        return self.item_type in (ItemType.CRYSTAL, ItemType.ORB, ItemType.WAND)

    @property
    def power_headroom(self) -> int:
        """
        How much more power this item can take.

        An orb has no maximum, so it reports a large-but-finite headroom rather
        than an infinity the arithmetic would have to special-case.
        """
        if not self.holds_power:
            return 0
        if self.item_type == ItemType.ORB:
            return 10_000
        return max(0, self.power_max - self.power_current)


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
        summoned_creatures: Dict mapping creature_id -> SummonedCreature
        posted_messages: Dict mapping city_id -> the message posted at its
            gates. Only a faction that has secured the city may post, and the
            posting lapses when they lose it. See `engine.process_post`.
        magical_items: Dict mapping item_id -> MagicalItem. Items are held here
            rather than on the character so that an item keeps its identity
            across owners, and so unfound items can sit in a ruin with no
            holder at all. See `items`.
        order_queues: Dict mapping character_id -> that character's pending
            orders. Orders survive between turns here; see `order_queue`.
    """
    turn_number: int = 0
    world_map: WorldMap = field(default_factory=WorldMap)
    factions: dict[str, Faction] = field(default_factory=dict)
    characters: dict[str, Character] = field(default_factory=dict)
    unit_stacks: dict[str, UnitStack] = field(default_factory=dict)
    ships: dict[str, Ship] = field(default_factory=dict)
    summoned_creatures: dict[str, SummonedCreature] = field(default_factory=dict)
    magical_items: dict[str, MagicalItem] = field(default_factory=dict)
    posted_messages: dict[str, str] = field(default_factory=dict)
    tax_pools: dict[str, float] = field(default_factory=dict)
    location_blessings: dict[str, int] = field(default_factory=dict)
    location_curses: dict[str, int] = field(default_factory=dict)
    order_queues: dict[str, list[QueueEntry]] = field(default_factory=dict)
    # Gold invested in a city's growth but not yet spent. INVEST adds to it;
    # the weekly check in engine.process_income_and_upkeep spends it on
    # population growth.
    invest_pools: dict[str, float] = field(default_factory=dict)
    # Named elite troop units, created by CREATE.
    elite_units: dict[str, EliteUnit] = field(default_factory=dict)
    # Absolute game time. A turn still defines the reporting/upkeep cadence,
    # but queued work can now wake at any hour inside that weekly window.
    game_time_hours: int = 0

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
