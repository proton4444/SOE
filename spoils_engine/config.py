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

# Upkeep costs per turn (simplified from rules)
# Rules: 1 gold per 2 months = ~0.1 gold per turn (assume 1 turn = ~1 week)
UPKEEP_PER_UNIT = {
    UnitType.SOLDIER: 0,  # Simplified: no upkeep in alpha
    UnitType.SAILOR: 0,
    UnitType.WORKER: 0,
}

UPKEEP_PER_SHIP = {
    ShipType.GALLEY: 0,  # Simplified: no upkeep in alpha
}


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
