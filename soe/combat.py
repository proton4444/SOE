"""
Combat resolution module.

Handles all combat-related calculations and resolution.
"""

import random
from dataclasses import dataclass

from soe.models import GameState, UnitType
from soe import config, items, territory


# ============================================================================
# COMBAT DATA STRUCTURES
# ============================================================================

@dataclass
class FactionForces:
    """Forces of a faction at a location."""
    faction_id: str
    combat_power: float
    best_combat_skill: int
    unit_count: int
    ship_count: int


@dataclass
class CombatResult:
    """Result of a combat resolution."""
    attacker_id: str
    defender_id: str
    winner_id: str
    loser_id: str
    attacker_power: float
    defender_power: float
    attacker_casualties: float
    defender_casualties: float


# ============================================================================
# COMBAT CALCULATION
# ============================================================================

def calculate_faction_power(faction_id: str, city_id: str, game_state: GameState,
                            member_ids: set[str] | None = None,
                            fortification_authority: dict[str, str | None] | None = None) -> float:
    """
    Calculate total combat power of a faction at a location.

    Formula: base_power * (1 + best_combat_skill / 100)
    """
    base_power = 0.0
    best_combat_skill = 0
    best_religion_skill = 0
    morale_values = []
    soldier_count = 0
    weapon_count = 0
    armor_count = 0
    siege_power = 0

    # Add character combat skills (best one applies as multiplier).
    # Non-combatants stay out unless the fight is forced elsewhere; they do
    # not contribute leadership or personal equipment to the power total.
    for char in game_state.characters.values():
        if (char.faction_id == faction_id and char.location_city_id == city_id
                and (member_ids is None or char.id in member_ids)
                and not char.is_dead and not getattr(char, "is_noncom", False)):
            best_combat_skill = max(best_combat_skill, char.combat_skill)
            best_religion_skill = max(best_religion_skill, char.religion_skill)
            morale_values.append(char.morale)

    # Add unit attack values
    for stack in game_state.unit_stacks.values():
        if (stack.faction_id == faction_id and stack.location_city_id == city_id
                and (member_ids is None or stack.owner_character_id in member_ids
                     or not stack.owner_character_id)):
            base_power += stack.attack_value
            if stack.unit_type == UnitType.SOLDIER:
                soldier_count += stack.count

    # Add ship attack values
    for ship in game_state.ships.values():
        if (ship.faction_id == faction_id and ship.location_city_id == city_id
                and (member_ids is None or ship.owner_character_id in member_ids
                     or not ship.owner_character_id)):
            base_power += ship.attack_value

    # Add summoned creatures (they fight for their summoner)
    for creature in game_state.summoned_creatures.values():
        summoner = game_state.characters.get(creature.summoner_id)
        if (summoner and summoner.faction_id == faction_id
                and summoner.location_city_id == city_id
                and (member_ids is None or summoner.id in member_ids)):
            base_power += creature.attack_value

    # Add elite troop units (they fight at their own combat level)
    for unit in game_state.elite_units.values():
        if (unit.faction_id == faction_id and unit.location_city_id == city_id
                and (member_ids is None or unit.leader_character_id in member_ids)):
            base_power += unit.attack_value

    # Apply skill multiplier
    # Apply equipment bonuses present on combatant characters at this location
    for char in game_state.characters.values():
        if (char.faction_id == faction_id and char.location_city_id == city_id
                and (member_ids is None or char.id in member_ids)
                and not char.is_dead and not getattr(char, "is_noncom", False)):
            weapon_count += char.resources.get("weapon", 0)
            armor_count += char.resources.get("armor", 0)
            siege_power += char.resources.get("catapult", 0)

    if soldier_count > 0:
        base_power += min(weapon_count, soldier_count) * 0.5
        base_power += min(siege_power, soldier_count) * 3

    skill_multiplier = 1.0 + (best_combat_skill * config.COMBAT_SKILL_BONUS_PER_POINT)
    morale = sum(morale_values) / len(morale_values) if morale_values else 100
    morale_multiplier = max(0.5, morale / 100.0)
    religion_multiplier = 1.0 + best_religion_skill / 200.0

    blessing_bonus = 1.0 + (game_state.location_blessings.get(city_id, 0) / 100)
    curse_penalty = 1.0 - (game_state.location_curses.get(city_id, 0) / 100)

    total_power = (base_power * skill_multiplier * morale_multiplier
                   * religion_multiplier * blessing_bonus * max(0.5, curse_penalty))

    # Combat supplies a phase snapshot; other callers use current authority.
    city = game_state.world_map.cities.get(city_id)
    authority_id = (fortification_authority.get(city_id)
                    if fortification_authority is not None
                    else territory.administrative_faction_id(game_state, city_id))
    if city and authority_id == faction_id:
        total_power *= 1.0 + (city.fortification_level / 100)

    return total_power


def get_faction_forces(faction_id: str, city_id: str, game_state: GameState) -> FactionForces:
    """Get detailed force composition for a faction at a location."""
    power = calculate_faction_power(faction_id, city_id, game_state)

    # Get best combat skill
    best_skill = 0
    for char in game_state.characters.values():
        if char.faction_id == faction_id and char.location_city_id == city_id:
            best_skill = max(best_skill, char.combat_skill)

    # Count units
    unit_count = sum(
        stack.count for stack in game_state.unit_stacks.values()
        if stack.faction_id == faction_id and stack.location_city_id == city_id
    )

    # Count ships
    ship_count = sum(
        1 for ship in game_state.ships.values()
        if ship.faction_id == faction_id and ship.location_city_id == city_id
    )

    return FactionForces(
        faction_id=faction_id,
        combat_power=power,
        best_combat_skill=best_skill,
        unit_count=unit_count,
        ship_count=ship_count
    )


# ============================================================================
# COMBAT RESOLUTION
# ============================================================================

def casualty_rates(winning_roll: float, losing_roll: float) -> tuple[float, float]:
    """
    Casualty rates for both sides, scaled by the margin of victory.

    The rolls (not the raw powers) decide this, so an upset — a weaker force
    that wins on a lucky roll — is correctly costly, while a rout is cheap for
    the winner and near-annihilation for the loser. At parity the rates are
    exactly the config baselines, so an even fight behaves as it always has.

    Returns:
        (winner_rate, loser_rate)
    """
    if losing_roll <= 0:
        margin = config.COMBAT_MARGIN_CAP
    else:
        margin = max(1.0, min(config.COMBAT_MARGIN_CAP, winning_roll / losing_roll))

    winner_rate = max(
        config.COMBAT_CASUALTY_MIN_WINNER,
        config.COMBAT_CASUALTY_RATE_WINNER / margin,
    )
    loser_rate = min(
        config.COMBAT_CASUALTY_MAX_LOSER,
        config.COMBAT_CASUALTY_RATE_LOSER * (margin ** config.COMBAT_LOSER_MARGIN_EXPONENT),
    )
    return winner_rate, loser_rate


class CombatResolver:
    """Handles combat resolution between two factions."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def should_attack(self, attacker_power: float, defender_power: float) -> bool:
        """Check if attacker should proceed with attack based on power ratio."""
        if defender_power == 0:
            return False  # No valid target

        ratio = attacker_power / defender_power
        return ratio >= config.COMBAT_MINIMUM_ATTACK_RATIO

    def resolve_combat(self, attacker_id: str, defender_id: str,
                      attacker_power: float, defender_power: float) -> CombatResult:
        """
        Resolve combat between two factions.

        Returns CombatResult with winner/loser and casualties.
        """
        # Add randomness (0.8x to 1.2x)
        attacker_roll = attacker_power * (0.8 + self.rng.random() * 0.4)
        defender_roll = defender_power * (0.8 + self.rng.random() * 0.4)

        # Determine winner
        if attacker_roll > defender_roll:
            winner_id, loser_id = attacker_id, defender_id
            winning_roll, losing_roll = attacker_roll, defender_roll
        else:
            winner_id, loser_id = defender_id, attacker_id
            winning_roll, losing_roll = defender_roll, attacker_roll

        winner_casualties, loser_casualties = casualty_rates(winning_roll, losing_roll)

        # Swap if defender won (to track attacker/defender casualties)
        if winner_id == defender_id:
            attacker_casualties = loser_casualties
            defender_casualties = winner_casualties
        else:
            attacker_casualties = winner_casualties
            defender_casualties = loser_casualties

        return CombatResult(
            attacker_id=attacker_id,
            defender_id=defender_id,
            winner_id=winner_id,
            loser_id=loser_id,
            attacker_power=attacker_power,
            defender_power=defender_power,
            attacker_casualties=attacker_casualties,
            defender_casualties=defender_casualties
        )


# ============================================================================
# CASUALTY APPLICATION
# ============================================================================

def apply_casualties(faction_id: str, city_id: str, casualty_rate: float,
                     game_state: GameState, rng: random.Random,
                     member_ids: set[str] | None = None) -> dict[str, int]:
    """
    Apply casualties to a faction's forces at a location.

    Returns dict with counts of losses: {'units': X, 'ships': Y, 'characters_wounded': Z, 'characters_killed': W}
    """
    losses = {'units': 0, 'ships': 0, 'characters_wounded': 0, 'characters_killed': 0}

    # Armor reduces casualties modestly
    soldier_count = sum(
        stack.count for stack in game_state.unit_stacks.values()
        if stack.faction_id == faction_id and stack.location_city_id == city_id
        and (member_ids is None or stack.owner_character_id in member_ids
             or not stack.owner_character_id)
        and stack.unit_type == UnitType.SOLDIER
    )
    armor_available = sum(
        char.resources.get("armor", 0) for char in game_state.characters.values()
        if char.faction_id == faction_id and char.location_city_id == city_id
        and (member_ids is None or char.id in member_ids)
    )
    if soldier_count > 0:
        armor_mitigation = 1.0 - min(armor_available, soldier_count) / (soldier_count * 4)
    else:
        armor_mitigation = 1.0

    casualty_rate *= max(0.25, armor_mitigation)

    # Apply to characters (damage proportional to casualty rate)
    blessed_here = city_id in game_state.location_blessings
    for char in game_state.characters.values():
        if (char.faction_id == faction_id and char.location_city_id == city_id
                and (member_ids is None or char.id in member_ids) and not char.is_dead):
            # A magical ring divides the chance of being hit, and a blessing
            # adds a point to its protection factor. Someone with no ring is
            # unaffected either way.
            protection = items.ring_protection(char, game_state, blessed=blessed_here)
            char_rate = items.apply_ring_protection(casualty_rate, protection)

            # Damage: casualty_rate * 30 points (0.3 rate = ~9 damage, 0.1 rate = ~3 damage)
            damage = int(char_rate * 30)
            if damage > 0:
                char.health = max(0, char.health - damage)
                losses['characters_wounded'] += 1

                if char.health <= 0:
                    char.is_dead = True
                    losses['characters_killed'] += 1

    # Apply to unit stacks
    for stack in list(game_state.unit_stacks.values()):
        if (stack.faction_id == faction_id and stack.location_city_id == city_id
                and (member_ids is None or stack.owner_character_id in member_ids
                     or not stack.owner_character_id)):
            casualties = int(stack.count * casualty_rate)
            stack.count -= casualties
            losses['units'] += casualties

            # Remove empty stacks
            if stack.count <= 0:
                del game_state.unit_stacks[stack.id]

    # Apply to elite units (soldiers taking losses like any other force)
    for unit in list(game_state.elite_units.values()):
        if (unit.faction_id == faction_id and unit.location_city_id == city_id
                and (member_ids is None or unit.leader_character_id in member_ids)):
            casualties = int(unit.size * casualty_rate)
            unit.size -= casualties
            losses['units'] += casualties

            if unit.size <= 0:
                del game_state.elite_units[unit.id]

    # Apply to ships (probabilistic)
    for ship in list(game_state.ships.values()):
        if (ship.faction_id == faction_id and ship.location_city_id == city_id
                and (member_ids is None or ship.owner_character_id in member_ids
                     or not ship.owner_character_id)):
            if rng.random() < casualty_rate:
                del game_state.ships[ship.id]
                losses['ships'] += 1

    return losses
