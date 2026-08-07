"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from typing import Dict, List

from spoils_engine.models import (
    GameState, Character, UnitStack, UnitType,
)
from spoils_engine.orders import (
    Order, CaptureOrder, FreeOrder, KillOrder, EnslaveOrder, InterrogateOrder,
)
from spoils_engine import items
from spoils_engine.combat import calculate_faction_power
from spoils_engine.parser import get_player_leader
from spoils_engine.turn_log import TurnLog
from spoils_engine.phases.common import allocate_id


def process_capture(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """Process CAPTURE orders to take prisoners."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, CaptureOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            # Simplified capture for alpha: if you have more power, you capture
            # In full game: would do combat resolution with capture attempts
            for i, target_id in enumerate(order.target_ids):
                target = game_state.characters.get(target_id)
                if not target or target.is_dead or target.is_prisoner:
                    continue

                # Check same location
                if actor.location_city_id != target.location_city_id:
                    turn_log.add("capture", player_id, "capture_failed",
                                f"{actor.name}: {target.name} is not at this location",
                                character_id=actor.id, success=False)
                    continue

                # Calculate power (simplified - use combat power calculation)
                attacker_power = calculate_faction_power(player_id, actor.location_city_id, game_state)
                defender_power = calculate_faction_power(target.faction_id, target.location_city_id, game_state)

                # Capture check: 50% + power ratio bonus. A magical ring cuts
                # the chance of being captured just as it cuts the chance of
                # being hit, and a blessing on the location adds to it.
                capture_chance = 0.5 + (attacker_power / max(1, defender_power + attacker_power)) * 0.5
                protection = items.ring_protection(
                    target, game_state,
                    blessed=target.location_city_id in game_state.location_blessings)
                capture_chance = items.apply_ring_protection(capture_chance, protection)

                if rng.random() < capture_chance:
                    # Successful capture
                    target.is_prisoner = True
                    target.captor_id = actor.id
                    turn_log.add("capture", player_id, "capture_success",
                                f"{actor.name}: captured {target.name}!",
                                character_id=actor.id)
                else:
                    # Failed capture - minor damage to target
                    damage = rng.randint(5, 15)
                    target.health = max(0, target.health - damage)
                    if target.health <= 0:
                        target.is_dead = True
                        turn_log.add("capture", player_id, "capture_killed",
                                    f"{actor.name}: killed {target.name} during capture attempt",
                                    character_id=actor.id)
                    else:
                        turn_log.add("capture", player_id, "capture_failed",
                                    f"{actor.name}: failed to capture {target.name} (dealt {damage} damage)",
                                    character_id=actor.id, success=False)


def process_free(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process FREE/RELEASE orders to free prisoners."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, FreeOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            # Free all specified prisoners
            for i, prisoner_id in enumerate(order.prisoner_ids):
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue

                # Check if this character is actually a prisoner held by this actor
                if not prisoner.is_prisoner or prisoner.captor_id != actor.id:
                    turn_log.add("free", player_id, "free_failed",
                                f"{actor.name}: {prisoner.name} is not a prisoner held by you",
                                character_id=actor.id, success=False)
                    continue

                # Free the prisoner
                prisoner.is_prisoner = False
                prisoner.captor_id = ""

                turn_log.add("free", player_id, "free_success",
                            f"{actor.name}: freed {prisoner.name}",
                            character_id=actor.id)


def _prisoner_held_by(prisoner: Character, actor: Character) -> bool:
    return bool(prisoner and prisoner.is_prisoner and prisoner.captor_id == actor.id)


def process_kill(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process KILL/EXECUTE orders against held prisoners."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, KillOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            for prisoner_id in order.prisoner_ids:
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue
                if not _prisoner_held_by(prisoner, actor):
                    turn_log.add("kill", player_id, "kill_failed",
                                f"{actor.name}: {prisoner.name} is not your prisoner",
                                character_id=actor.id, success=False)
                    continue
                prisoner.is_dead = True
                prisoner.health = 0
                prisoner.is_prisoner = False
                prisoner.captor_id = ""
                turn_log.add("kill", player_id, "kill_success",
                            f"{actor.name}: executed {prisoner.name}",
                            character_id=actor.id)


def process_enslave(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Convert prisoners into unnamed slave labour units."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, EnslaveOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            for prisoner_id in list(order.prisoner_ids):
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue
                if not _prisoner_held_by(prisoner, actor):
                    turn_log.add("enslave", player_id, "enslave_failed",
                                f"{actor.name}: {prisoner.name} is not your prisoner",
                                character_id=actor.id, success=False)
                    continue

                # Valuables on the prisoner are lost (rules warn to TAKE first)
                lost_gold = prisoner.gold
                prisoner.gold = 0

                # Add one slave unit at the actor's location for the captors
                stack = next(
                    (s for s in game_state.unit_stacks.values()
                     if s.faction_id == player_id
                     and s.location_city_id == actor.location_city_id
                     and s.unit_type == UnitType.SLAVE),
                    None,
                )
                if stack:
                    stack.count += 1
                else:
                    sid = allocate_id(game_state.unit_stacks, "stack")
                    game_state.unit_stacks[sid] = UnitStack(
                        id=sid,
                        faction_id=player_id,
                        location_city_id=actor.location_city_id,
                        unit_type=UnitType.SLAVE,
                        count=1,
                    )

                # Named identity is gone — remove the character
                name = prisoner.name
                del game_state.characters[prisoner_id]
                msg = f"{actor.name}: enslaved {name} (now 1 slave)"
                if lost_gold:
                    msg += f"; {lost_gold}g of their purse was lost"
                turn_log.add("enslave", player_id, "enslave_success", msg,
                            character_id=actor.id)


def process_interrogate(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                        turn_log: TurnLog, rng: random.Random):
    """Extract faction / leader intel from a prisoner."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, InterrogateOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            for prisoner_id in order.prisoner_ids:
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue
                if not _prisoner_held_by(prisoner, actor):
                    turn_log.add("interrogate", player_id, "interrogate_failed",
                                f"{actor.name}: {prisoner.name} is not your prisoner",
                                character_id=actor.id, success=False)
                    continue

                actor_level = actor.combat_skill + actor.magic_skill + actor.religion_skill
                victim_level = prisoner.combat_skill + prisoner.magic_skill + prisoner.religion_skill
                chance = 0.35 + (actor_level - victim_level) / 200
                chance = max(0.1, min(0.9, chance))

                # Higher-level victims more likely to die under torture
                death_chance = 0.05 + victim_level / 400
                if rng.random() < death_chance:
                    prisoner.is_dead = True
                    prisoner.health = 0
                    prisoner.is_prisoner = False
                    prisoner.captor_id = ""
                    turn_log.add("interrogate", player_id, "interrogate_killed",
                                f"{actor.name}: {prisoner.name} died under interrogation",
                                character_id=actor.id, success=False)
                    continue

                if rng.random() < chance:
                    fac = game_state.factions.get(prisoner.faction_id)
                    fac_name = fac.name if fac else prisoner.faction_id
                    leader = get_player_leader(game_state, prisoner.faction_id)
                    leader_name = leader.name if leader else "unknown"
                    turn_log.add("interrogate", player_id, "interrogate_success",
                                f"{actor.name}: {prisoner.name} revealed faction '{fac_name}', "
                                f"leader '{leader_name}'",
                                character_id=actor.id)
                else:
                    damage = rng.randint(5, 20)
                    prisoner.health = max(1, prisoner.health - damage)
                    turn_log.add("interrogate", player_id, "interrogate_failed",
                                f"{actor.name}: {prisoner.name} revealed nothing "
                                f"(took {damage} damage)",
                                character_id=actor.id, success=False)

def process_prisoner_escape(game_state: GameState, turn_log: TurnLog, rng: random.Random):
    """Allow prisoners a small chance to escape each turn."""
    for prisoner in game_state.characters.values():
        if not prisoner.is_prisoner or prisoner.is_dead:
            continue

        if rng.random() < 0.1:
            prisoner.is_prisoner = False
            prisoner.captor_id = ""
            turn_log.add("prisoner", prisoner.faction_id, "escape",
                        f"{prisoner.name} escaped captivity", character_id=prisoner.id)

