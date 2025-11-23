"""
Combat resolution module.

Handles all combat-related calculations and resolution.
"""

import random
from dataclasses import dataclass
from typing import Optional

from spoils_engine.models import GameState, Character, Faction
from spoils_engine import config


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

def calculate_faction_power(faction_id: str, city_id: str, game_state: GameState) -> float:
    """
    Calculate total combat power of a faction at a location.

    Formula: base_power * (1 + best_combat_skill / 100)
    """
    base_power = 0.0
    best_combat_skill = 0
    soldier_count = 0
    weapon_count = 0
    armor_count = 0
    siege_power = 0

    # Add character combat skills (best one applies as multiplier)
    for char in game_state.characters.values():
        if char.faction_id == faction_id and char.location_city_id == city_id:
            best_combat_skill = max(best_combat_skill, char.combat_skill)

    # Add unit attack values
    for stack in game_state.unit_stacks.values():
        if stack.faction_id == faction_id and stack.location_city_id == city_id:
            base_power += stack.attack_value
            if stack.unit_type.name == "SOLDIER":
                soldier_count += stack.count

    # Add ship attack values
    for ship in game_state.ships.values():
        if ship.faction_id == faction_id and ship.location_city_id == city_id:
            base_power += ship.attack_value

    # Add summoned creatures (they fight for their summoner)
    for creature in game_state.summoned_creatures.values():
        summoner = game_state.characters.get(creature.summoner_id)
        if summoner and summoner.faction_id == faction_id and summoner.location_city_id == city_id:
            base_power += creature.attack_value

    # Apply skill multiplier
    # Apply equipment bonuses present on characters at this location
    for char in game_state.characters.values():
        if char.faction_id == faction_id and char.location_city_id == city_id:
            weapon_count += char.resources.get("weapon", 0)
            armor_count += char.resources.get("armor", 0)
            siege_power += char.resources.get("catapult", 0)

    if soldier_count > 0:
        base_power += min(weapon_count, soldier_count) * 0.5
        base_power += min(siege_power, soldier_count) * 3

    skill_multiplier = 1.0 + (best_combat_skill * config.COMBAT_SKILL_BONUS_PER_POINT)

    blessing_bonus = 1.0 + (game_state.location_blessings.get(city_id, 0) / 100)
    curse_penalty = 1.0 - (game_state.location_curses.get(city_id, 0) / 100)
    city_fort_level = game_state.city_fortifications.get(city_id, 0)
    fort_multiplier = 1.0 + (city_fort_level / 100)

    total_power = base_power * skill_multiplier * blessing_bonus * max(0.5, curse_penalty)

    # Fortifications only benefit defenders
    if city_id in game_state.world_map.cities and city_id in game_state.factions.get(faction_id, Faction(faction_id, faction_id)).controlled_city_ids:
        total_power *= fort_multiplier

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
            winner_casualties = config.COMBAT_CASUALTY_RATE_WINNER
            loser_casualties = config.COMBAT_CASUALTY_RATE_LOSER
        else:
            winner_id, loser_id = defender_id, attacker_id
            winner_casualties = config.COMBAT_CASUALTY_RATE_WINNER
            loser_casualties = config.COMBAT_CASUALTY_RATE_LOSER

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
                     game_state: GameState, rng: random.Random) -> dict[str, int]:
    """
    Apply casualties to a faction's forces at a location.

    Returns dict with counts of losses: {'units': X, 'ships': Y, 'characters_wounded': Z, 'characters_killed': W}
    """
    losses = {'units': 0, 'ships': 0, 'characters_wounded': 0, 'characters_killed': 0}

    # Armor reduces casualties modestly
    soldier_count = sum(
        stack.count for stack in game_state.unit_stacks.values()
        if stack.faction_id == faction_id and stack.location_city_id == city_id and stack.unit_type.name == "SOLDIER"
    )
    armor_available = sum(
        char.resources.get("armor", 0) for char in game_state.characters.values()
        if char.faction_id == faction_id and char.location_city_id == city_id
    )
    if soldier_count > 0:
        armor_mitigation = 1 - min(armor_available, soldier_count) / (soldier_count * 4)
    else:
        armor_mitigation = 1

    casualty_rate *= max(0.25, armor_mitigation)

    # Apply to characters (damage proportional to casualty rate)
    for char in game_state.characters.values():
        if char.faction_id == faction_id and char.location_city_id == city_id and not char.is_dead:
            # Damage: casualty_rate * 30 points (0.3 rate = ~9 damage, 0.1 rate = ~3 damage)
            damage = int(casualty_rate * 30)
            if damage > 0:
                char.health = max(0, char.health - damage)
                losses['characters_wounded'] += 1

                if char.health <= 0:
                    char.is_dead = True
                    losses['characters_killed'] += 1

    # Apply to unit stacks
    for stack in list(game_state.unit_stacks.values()):
        if stack.faction_id == faction_id and stack.location_city_id == city_id:
            casualties = int(stack.count * casualty_rate)
            stack.count -= casualties
            losses['units'] += casualties

            # Remove empty stacks
            if stack.count <= 0:
                del game_state.unit_stacks[stack.id]

    # Apply to ships (probabilistic)
    for ship in list(game_state.ships.values()):
        if ship.faction_id == faction_id and ship.location_city_id == city_id:
            if rng.random() < casualty_rate:
                del game_state.ships[ship.id]
                losses['ships'] += 1

    return losses
