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

# Miles one movement point covers on a good road. When a road carries a
# `distance_miles` from the gamemaster's map, a hop costs
# quality_multiplier * (miles / MILES_PER_MOVE_POINT), so a 100-mile good
# road is one full turn of walking (~14 miles/day). Roads without miles keep
# the old quality-only cost.
MILES_PER_MOVE_POINT = 10


# ============================================================================
# GAME TIME
# ============================================================================

# One turn is one game week. rules.md's default game-to-real-time ratio is 7,
# and the natural healing rate already assumes a seven-day turn. Order-queue
# waits expressed in days are converted with this.
DAYS_PER_TURN = 7

# rules.md: "1 month in Spoils of Empire is exactly 30 days."
DAYS_PER_MONTH = 30

# How long "wait for <person>" holds when the order names no deadline. The
# rules let such a wait run indefinitely; a bound keeps a character from being
# stranded forever by a target who never arrives.
AWAIT_DEFAULT_DEADLINE_DAYS = 90


# ============================================================================
# ECONOMY
# ============================================================================

# Income per turn by population band (simplified from taxation rules)
# Based on rules: ~1 gold per 4 residents per year, converted to per-turn
INCOME_PER_POPULATION_BAND = {
    PopulationBand.TINY: 10,       # < 1k residents
    PopulationBand.SMALL: 50,      # 1k-9,999 residents
    PopulationBand.MEDIUM: 200,    # 10k-99,999 residents
    PopulationBand.LARGE: 500,     # 100k+ residents
}

# Numeric population used when a city has never been measured (INVEST makes
# the measurement concrete). Midpoints of the bands, for income purposes.
# LARGE is open-ended; 150,000 sits just above the world's largest town.
POPULATION_BAND_MIDPOINT = {
    PopulationBand.TINY: 500,
    PopulationBand.SMALL: 5_000,
    PopulationBand.MEDIUM: 55_000,
    PopulationBand.LARGE: 150_000,
}

# Population at which a city's band (and therefore its income and recruit
# cap) steps up. Crossed only by INVEST-driven growth.
POPULATION_BAND_THRESHOLD = [
    (PopulationBand.TINY, 1_000),
    (PopulationBand.SMALL, 10_000),
    (PopulationBand.MEDIUM, 100_000),
]


def city_population(city) -> int:
    """The city's numeric population, from measurement or band midpoint."""
    if city.population:
        return city.population
    return POPULATION_BAND_MIDPOINT.get(city.population_band, 500)


def population_band_for(population: int) -> PopulationBand:
    """The band a given numeric population belongs to."""
    if population >= 100_000:
        return PopulationBand.LARGE
    if population >= 10_000:
        return PopulationBand.MEDIUM
    if population >= 1_000:
        return PopulationBand.SMALL
    return PopulationBand.TINY

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
    UnitType.SLAVE: 0,   # Created by ENSLAVE, not recruited
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
    UnitType.SLAVE: 0.01,    # Cheaper labour; still needs food
}

# Banking guild: TRANSFER fee = fixed + percent of principal (rounded up)
TRANSFER_FEE_FIXED = 10
TRANSFER_FEE_PERCENT = 0.01

# BORROW: alpha success odds and interest
BORROW_BASE_CHANCE = 0.55
BORROW_INTEREST_RATE = 0.01  # 1% of balance per turn (game week)
BORROW_GRACE_TURNS = 4
BORROW_MIN_PAYMENT_FRACTION = 0.10
BORROW_MAX_AMOUNT = 500  # Cap when amount is omitted


# ============================================================================
# WORK
# ============================================================================

# Daily wages for common labour, by population band. rules.md: work is easy
# to find in heavily populated areas and may not exist at all in lightly
# populated ones -- the TINY rate is zero, so those characters volunteer.
WORK_WAGE_DAILY_PER_BAND = {
    PopulationBand.TINY: 0.0,
    PopulationBand.SMALL: 1.0,
    PopulationBand.MEDIUM: 2.0,
    PopulationBand.LARGE: 3.0,
}

# High-level characters try to sell their own skills rather than labour for
# common wages; the bonus is per day per point of their best skill.
WORK_SKILL_BONUS_PER_LEVEL_PER_DAY = 0.02


# ============================================================================
# TRAIN
# ============================================================================

# rules.md: a trainer needs the appropriate skill at least 10 (combat to
# train soldiers, sailing to train sailors).
TRAIN_MIN_TRAINER_SKILL = 10

# rules.md: a level 50 trainer trains 5 workers to level 1 in a week, i.e.
# 70 * trainees / skill days, never less than a week. The engine has no
# sub-turn clock, so a TRAIN order converts what one week can produce and
# leaves the rest to train another turn. TRAIN_DAYS_FOR_5_AT_50 = 7 days.
TRAIN_WORKERS_PER_WEEK_FROM_SKILL = 50 / 7  # level-50 trainer: 5 in 7 days
TRAIN_MIN_DAYS = 7


# ============================================================================
# PREACH
# ============================================================================

# Daily donations a level-100 preacher can collect, by population band. The
# actual take scales with the preacher's religion skill and some randomness.
PREACH_DONATION_DAILY_PER_BAND = {
    PopulationBand.TINY: 1,
    PopulationBand.SMALL: 3,
    PopulationBand.MEDIUM: 8,
    PopulationBand.LARGE: 20,
}

# Chance per week that a preacher attracts followers: the chance is
# religion_skill/100 times this, and 1-3 workers join when it succeeds.
PREACH_FOLLOWER_CHANCE = 0.25


# ============================================================================
# INVEST
# ============================================================================

# rules.md: each week the computer spends about population/100 gold from the
# invested pool and raises the population by the same amount, with some
# randomness. INVEST_SPEND_SCATTER is the random fraction either way.
INVEST_SPEND_SCATTER = 0.5
INVEST_POPULATION_GAIN_MAX = 2_000  # cap per week so a huge pool cannot explode


# ============================================================================
# BUY PASSAGE
# ============================================================================

# rules.md: passage costs the group's total encumbrance in gold. The engine
# has no encumbrance, so every person (character, soldier, sailor, worker,
# slave) counts as one gold. Rules Appendix B: horses would be 2 each.
PASSAGE_COST_PER_PERSON = 1

# Passage may fail, most likely for large groups. "definitely" keeps trying.
PASSAGE_BASE_CHANCE = 0.95
PASSAGE_SIZE_PENALTY_PER_100 = 0.25
PASSAGE_DEFINITELY_BONUS = 0.25


# ============================================================================
# OFFER
# ============================================================================

# rules.md: an independent character accepts an offer of at least half the
# square of his highest level, plus the value of items in his possession.
# Item value is approximated from the item fields the engine tracks.
OFFER_ACCEPT_FRACTION_OF_LEVEL_SQUARE = 0.5
OFFER_ITEM_VALUE_POWER_PER_POINT = 0.5
OFFER_ITEM_VALUE_SKILL_PER_POINT = 0.5
OFFER_ITEM_VALUE_PROTECTION_PER_POINT = 10.0


# ============================================================================
# ELITE TROOPS (CREATE)
# ============================================================================

# rules.md: an elite unit's level rises about 1 partial point per week, from
# constant training. The engine gives one partial point per turn (a turn is a
# week); every ELITE_PARTIAL_PER_LEVEL partial points become one level.
ELITE_PARTIAL_PER_WEEK = 1.0
ELITE_PARTIAL_PER_LEVEL = 5

# rules.md: salary is the number of soldiers times the combat level per
# month; a weekly turn costs that times 7/30.
ELITE_SALARY_FRACTION_OF_MONTH = 7 / 30


def transfer_fee(principal: float) -> int:
    """Banking guild fee: fixed + 1% of principal, rounded up."""
    import math
    return TRANSFER_FEE_FIXED + math.ceil(principal * TRANSFER_FEE_PERCENT)

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

# Casualty rates at parity. These are the rates for an evenly matched fight;
# a lopsided battle scales them by the margin of victory (see combat.py).
COMBAT_CASUALTY_RATE_WINNER = 0.1   # 10% casualties for winner
COMBAT_CASUALTY_RATE_LOSER = 0.3    # 30% casualties for loser

# Margin scaling. margin = winning roll / losing roll, clamped to
# [1, COMBAT_MARGIN_CAP]. The winner's losses fall as the margin grows; the
# loser's rise. Without this a 10:1 rout cost the winner exactly as much as a
# coin-flip battle.
COMBAT_MARGIN_CAP = 10.0            # Beyond this, extra advantage changes nothing
COMBAT_CASUALTY_MIN_WINNER = 0.01   # A rout still costs the winner something
COMBAT_CASUALTY_MAX_LOSER = 0.95    # A rout still leaves a few survivors
COMBAT_LOSER_MARGIN_EXPONENT = 0.5  # Loser rate grows with sqrt(margin)

# Combat skill bonus: each point of combat skill adds 1% to faction power
COMBAT_SKILL_BONUS_PER_POINT = 0.01

# Minimum attack power ratio to actually attack (simplified)
COMBAT_MINIMUM_ATTACK_RATIO = 0.5  # Attack if at least 50% of defender power


# ============================================================================
# MAGIC
# ============================================================================

# Magic power costs.
# TELEPORT and FLY are priced by encumbrance, not distance -- rules.md gives
# teleport "no limit on distance" -- so see `encumbrance.py` for their costs.

# Magic power regeneration (not implemented in alpha - instant refill)
MAGIC_POWER_REGEN_PER_TURN = 0  # Simplified: magic refills to max each turn


# ============================================================================
# COMMUNICATION
# ============================================================================

# rules.md: a message is "limited to a maximum of 2500 bytes (about 1 full page
# of dense print)"; a posting at the gates to 256 characters.
MESSAGE_MAX_LENGTH = 2500
POST_MAX_LENGTH = 256

# rules.md: "A password must contain between 8 and 64 characters". Shorter and
# the computer generates one for you; longer and it is truncated.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64


# ============================================================================
# MAGICAL ITEMS
# ============================================================================

# rules.md fixes none of an item's strength -- "there is no way to specify the
# power or skill level of the item obtained" -- so every item is rolled from
# these ranges when it is found or conjured. The example items in the rules
# (*Wameka* trading 72, *Nashi* power 51/60, *Fidula* prot 3, *Opistama*
# teleport 62/75) sit inside them.
ITEM_AMULET_SKILL_RANGE = (40, 85)
ITEM_CRYSTAL_MAX_RANGE = (20, 80)
ITEM_ORB_POWER_RANGE = (10, 60)
ITEM_RING_PROTECTION_RANGE = (2, 5)
ITEM_WAND_MAX_RANGE = (30, 90)
ITEM_WAND_SKILL_RANGE = (40, 90)

# CONJURE: minimum magic skill to attempt the spell, per rules.md.
CONJURE_MIN_MAGIC_SKILL = 25

# SCAN: an orb spends one power per ten miles to the scanned location
# (rules.md). When the route carries `distance_miles` from the map the miles
# are used directly; this converts movement cost into power for maps without
# mileages.
ORB_POWER_PER_HOP = 5

# SEARCH: chance a dig in ruins turns up an item at all, and the relative
# weights of what it turns up. Rings and orbs are the rarest finds.
RUIN_ITEM_BASE_CHANCE = 0.10
RUIN_ITEM_CHANCE_PER_DAY = 0.015
RUIN_ITEM_MAX_CHANCE = 0.60
RUIN_ITEM_WEIGHTS = {
    "crystal": 30,
    "amulet": 25,
    "wand": 20,
    "orb": 15,
    "ring": 10,
}


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


def get_hop_cost(road) -> float:
    """
    Movement cost of crossing one route.

    With `distance_miles` on the map (rules.md: travel time depends on the
    distance and the quality of the roads) the cost is the quality multiplier
    times miles per movement point. Without it, the old quality-only hop cost
    keeps hand-built maps working.
    """
    multiplier = get_movement_cost(road.quality)
    if road.distance_miles:
        return multiplier * (road.distance_miles / MILES_PER_MOVE_POINT)
    return multiplier


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
