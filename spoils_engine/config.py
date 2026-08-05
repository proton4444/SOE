"""
Configuration constants and tuning parameters for the game engine.

All game balance knobs and rules are centralized here for easy tuning.
"""

from spoils_engine.models import PopulationBand, RoadQuality, UnitType, ShipType


# ============================================================================
# MOVEMENT COSTS
# ============================================================================

# Base movement cost multipliers by road quality
ROAD_QUALITY_COST = {
    RoadQuality.EXCELLENT: 0.5,
    RoadQuality.GOOD: 1.0,
    RoadQuality.FAIR: 1.5,
    RoadQuality.POOR: 2.0,
    RoadQuality.SEA: 1.0,  # Sea lanes (requires ship)
}

# Base movement cost per "hop" between cities
BASE_MOVEMENT_COST = 1

# Movement points characters get per turn (simplified for alpha)
CHARACTER_MOVEMENT_POINTS_PER_TURN = 10


# ============================================================================
# ECONOMY
# ============================================================================

# Income per turn by population band (simplified from taxation rules)
# Based on rules: ~1 gold per 4 residents per year, converted to per-turn
INCOME_PER_POPULATION_BAND = {
    PopulationBand.TINY: 10,       # < 10k residents
    PopulationBand.SMALL: 50,      # 10k-99k residents
    PopulationBand.MEDIUM: 200,    # 100k-999k residents
    PopulationBand.LARGE: 500,     # 1M+ residents
}

# Recruitment caps per turn by population band
# Rules: Larger cities have more recruits available
RECRUIT_CAP_PER_POPULATION_BAND = {
    PopulationBand.TINY: 10,
    PopulationBand.SMALL: 50,
    PopulationBand.MEDIUM: 200,
    PopulationBand.LARGE: 500,
}

# Recruitment costs (gold per unit)
# From rules: 1 gold for soldier/sailor, 0.25 for worker (round up)
RECRUIT_COST = {
    UnitType.SOLDIER: 1,
    UnitType.SAILOR: 1,
    UnitType.WORKER: 1,  # Simplified from 0.25 for alpha
}

# Ship costs (gold per ship)
# From rules Appendix B: Galley = 1000 gold
SHIP_COST = {
    ShipType.GALLEY: 1000,
}

# Upkeep costs per turn (based on rules)
# Rules: 1 gold per 2 months for soldiers = ~0.125 gold per week
# Assuming 1 turn = 1 week for the alpha
UPKEEP_PER_UNIT = {
    UnitType.SOLDIER: 0.1,   # ~1g per 2.5 months
    UnitType.SAILOR: 0.1,    # ~1g per 2.5 months
    UnitType.WORKER: 0.025,  # ~1g per 10 months
}

UPKEEP_PER_SHIP = {
    ShipType.GALLEY: 2.0,  # Ship maintenance (crew, repairs)
}

# Named character salary formula (per turn)
# Rules: 5 gold + effective_level per month, we divide by ~4 for weekly
NAMED_CHARACTER_BASE_SALARY = 1.25  # 5g / 4 weeks
NAMED_CHARACTER_SKILL_MULTIPLIER = 0.25  # per effective level / 4


# ============================================================================
# TRADE
# ============================================================================

# Base market value per unit of a resource, in gold.
# Prices are set here rather than taken from the order text so that a player
# cannot name the price at which their own goods are bought or sold.
RESOURCE_BASE_PRICE = {
    "wood": 4,
    "stone": 5,
    "iron": 8,
    "copper": 10,
    "silver": 25,
    "gold": 40,
    "gems": 60,
    "weapon": 15,
    "armor": 20,
    "catapult": 120,
}

RESOURCE_DEFAULT_PRICE = 5

# Gap between the market's buy and sell quotes, as a fraction of base price.
# Trading skill narrows this spread but never closes it, so round-tripping a
# purchase through a sale always loses a little gold.
RESOURCE_MARKET_SPREAD = 0.4


# ============================================================================
# COMBAT
# ============================================================================

# Combat power formula:
# faction_power = sum(unit_attack) * (1 + best_combat_skill/100)
# winner if attacker_power > defender_power (with some randomness)

# Casualty rates (% of losing side destroyed)
COMBAT_CASUALTY_RATE_WINNER = 0.1   # 10% casualties for winner
COMBAT_CASUALTY_RATE_LOSER = 0.3    # 30% casualties for loser

# Combat skill bonus: each point of combat skill adds 1% to faction power
COMBAT_SKILL_BONUS_PER_POINT = 0.01

# Minimum attack power ratio to actually attack (simplified)
COMBAT_MINIMUM_ATTACK_RATIO = 0.5  # Attack if at least 50% of defender power


# ============================================================================
# MAGIC
# ============================================================================

# Magic power costs
# Teleport: cost = distance / TELEPORT_DISTANCE_PER_POWER
TELEPORT_DISTANCE_PER_POWER = 10  # 1 magic power per 10 distance units

# Magic power regeneration (not implemented in alpha - instant refill)
MAGIC_POWER_REGEN_PER_TURN = 0  # Simplified: magic refills to max each turn


# ============================================================================
# STARTING CONDITIONS
# ============================================================================

# Starting resources for new factions
STARTING_TREASURY = 1000

# Starting character combat skill
STARTING_COMBAT_SKILL = 10

# Starting character magic skill
STARTING_MAGIC_SKILL = 5


# ============================================================================
# VALIDATION
# ============================================================================

# Maximum orders per player per turn (prevents abuse)
MAX_ORDERS_PER_PLAYER = 100

# Maximum path length for movement (prevents pathfinding issues)
MAX_PATH_LENGTH = 20


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_movement_cost(road_quality: RoadQuality) -> float:
    """Get the movement cost multiplier for a road quality."""
    return ROAD_QUALITY_COST.get(road_quality, 1.0) * BASE_MOVEMENT_COST


def get_income_for_city(pop_band: PopulationBand) -> int:
    """Get the income per turn for controlling a city."""
    return INCOME_PER_POPULATION_BAND.get(pop_band, 0)


def get_recruit_cap_for_city(pop_band: PopulationBand) -> int:
    """Get the recruitment cap per turn for a city."""
    return RECRUIT_CAP_PER_POPULATION_BAND.get(pop_band, 0)


def get_recruit_cost(unit_type: UnitType) -> int:
    """Get the gold cost to recruit a unit."""
    return RECRUIT_COST.get(unit_type, 1)


def get_ship_cost(ship_type: ShipType) -> int:
    """Get the gold cost to buy a ship."""
    return SHIP_COST.get(ship_type, 1000)


def get_resource_price(resource_type: str) -> int:
    """Get the base market value of one unit of a resource."""
    return RESOURCE_BASE_PRICE.get(resource_type, RESOURCE_DEFAULT_PRICE)


def calculate_character_salary(combat_skill: int, magic_skill: int) -> float:
    """
    Calculate salary for a named character per turn.

    Formula from rules: 5 + sqrt(combat^2 + magic^2) per month
    Divided by 4 for weekly turns.
    """
    import math
    effective_level = math.sqrt(combat_skill**2 + magic_skill**2)
    monthly_salary = 5 + effective_level
    return monthly_salary / 4  # Convert to per-turn (weekly)
