"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List

from spoils_engine.models import (
    GameState, Character,
)
from spoils_engine.orders import (
    Order, AttackOrder,
)
from spoils_engine.combat import CombatResolver, calculate_faction_power, apply_casualties
from spoils_engine.turn_log import TurnLog


def defending_side(defender_id: str, attacker_id: str, city_id: str,
                   game_state: GameState) -> List[str]:
    """
    Factions that fight alongside the defender at a location.

    An ally joins only if it actually has fighting strength present, so a lone
    envoy is not dragged into a battle it cannot influence. A faction allied to
    both combatants stays out rather than fighting itself.
    """
    side = [defender_id]
    defender = game_state.factions.get(defender_id)
    if not defender:
        return side

    for ally_id in sorted(defender.allies):
        if ally_id in (defender_id, attacker_id):
            continue
        ally = game_state.factions.get(ally_id)
        if not ally or attacker_id in ally.allies:
            continue
        if calculate_faction_power(ally_id, city_id, game_state) > 0:
            side.append(ally_id)

    return side


def supporting_side(attacker: Character, city_id: str,
                    game_state: GameState) -> List[str]:
    """
    Other factions whose characters have agreed to fight alongside this attacker.

    rules.md: a supporter joins "as if they had given the same ATTACK/CAPTURE
    order at exactly the same time", but stays a separate group. Their strength
    is summed per faction rather than merged, which is what the rules mean by
    combat leadership being "limited to a single group" -- the supporter's
    leadership lifts their own people and nobody else's.
    """
    extra: List[str] = []

    for char in game_state.characters.values():
        if char.supporting_id != attacker.id:
            continue
        if char.location_city_id != city_id or char.is_dead or char.is_prisoner:
            continue
        if char.faction_id == attacker.faction_id or char.faction_id in extra:
            continue
        if calculate_faction_power(char.faction_id, city_id, game_state) > 0:
            extra.append(char.faction_id)

    return sorted(extra)


def process_combat(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog, rng: random.Random):
    """Process combat orders using CombatResolver."""
    # Group attacks by location
    attacks_by_location = defaultdict(list)

    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, AttackOrder) and not order.warnings:
                attacks_by_location[order.location_city_id].append((player_id, order))

    # Initialize combat resolver
    resolver = CombatResolver(rng)

    # Process each battle
    for city_id, attacks in attacks_by_location.items():
        city = game_state.world_map.cities.get(city_id)
        if not city:
            continue

        for attacker_player_id, attack_order in attacks:
            attacker = game_state.characters.get(attack_order.actor_id)
            if not attacker:
                continue

            # Find defender faction
            defender_faction_id = attack_order.target_faction_id
            if not defender_faction_id:
                turn_log.add("combat", attacker_player_id, "attack_failed",
                            f"{attacker.name} found no valid target in {city.name}",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            # Calculate powers. The defender's allies present at the location
            # stand with them, so their strength counts and they share the
            # losses.
            # Supporters fight as if they had attacked at the same moment, and
            # cannot also be counted among the defender's allies.
            supporters = supporting_side(attacker, city_id, game_state)
            side = [fid for fid in
                    defending_side(defender_faction_id, attacker_player_id, city_id, game_state)
                    if fid not in supporters]
            attack_side = [attacker_player_id] + supporters
            attacker_power = sum(
                calculate_faction_power(fid, city_id, game_state) for fid in attack_side
            )
            defender_power = sum(
                calculate_faction_power(fid, city_id, game_state) for fid in side
            )

            # Validate engagement
            if defender_power == 0:
                turn_log.add("combat", attacker_player_id, "attack_failed",
                            f"{attacker.name} found no defenders in {city.name}",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            if not resolver.should_attack(attacker_power, defender_power):
                turn_log.add("combat", attacker_player_id, "attack_declined",
                            f"{attacker.name} declined to attack (odds too poor)",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            # Resolve combat
            result = resolver.resolve_combat(
                attacker_player_id, defender_faction_id,
                attacker_power, defender_power
            )

            # Apply casualties. Supporters bleed for it too.
            attacker_losses = apply_casualties(
                attacker_player_id, city_id, result.attacker_casualties, game_state, rng
            )
            for supporter_id in supporters:
                supporter_losses = apply_casualties(
                    supporter_id, city_id, result.attacker_casualties, game_state, rng
                )
                turn_log.add("combat", supporter_id, "supported",
                            f"Your forces fought alongside {attacker.name} in {city.name} "
                            f"(lost {supporter_losses['units']} units)",
                            location=city_id)
            defender_losses = {
                fid: apply_casualties(fid, city_id, result.defender_casualties, game_state, rng)
                for fid in side
            }

            # Log results
            allies = [game_state.factions[f].name for f in side[1:] if f in game_state.factions]
            with_allies = f" (aided by {', '.join(allies)})" if allies else ""

            if result.winner_id == attacker_player_id:
                turn_log.add("combat", attacker_player_id, "victory",
                            f"{attacker.name} defeated {attack_order.target_name}{with_allies} "
                            f"in {city.name} (lost {attacker_losses['units']} units)",
                            location=city_id, character_id=attacker.id)
                for fid in side:
                    turn_log.add("combat", fid, "defeat",
                                f"Your forces were defeated by {attacker.name} in {city.name} "
                                f"(lost {defender_losses[fid]['units']} units)",
                                location=city_id)
            else:
                turn_log.add("combat", attacker_player_id, "defeat",
                            f"{attacker.name} was defeated in {city.name} "
                            f"(lost {attacker_losses['units']} units)",
                            location=city_id, character_id=attacker.id)
                for fid in side:
                    turn_log.add("combat", fid, "victory",
                                f"Your forces successfully defended {city.name} "
                                f"(lost {defender_losses[fid]['units']} units)",
                                location=city_id)

