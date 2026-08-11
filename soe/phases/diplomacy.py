"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List

from soe.models import (
    GameState, LocationPosition,
)
from soe.orders import (
    Order, SecureOrder, FortifyOrder, UnfortifyOrder, AllyOrder, EnemyOrder,
    NeutralOrder, NoncomOrder, LurkOrder,
)
from soe import groups, territory
from soe.turn_log import TurnLog


def process_secure(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process SECURE orders for location control."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SecureOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            city_id = order.city_id or actor.location_city_id
            city = game_state.world_map.cities.get(city_id)
            if not city:
                continue

            faction = game_state.factions.get(player_id)
            if not faction:
                continue

            if not territory.has_qualifying_garrison(game_state, actor, city_id):
                # One message used to cover three quite different problems, so
                # a player could not tell whether to march, step inside the
                # walls, or bring soldiers. Same rule, named precisely.
                if actor.location_city_id != city_id:
                    reason = f"{actor.name} is not in {city.name}"
                elif actor.location_position != LocationPosition.INSIDE:
                    reason = (f"{actor.name} is {actor.location_position.value} "
                              f"{city.name}, and SECURE requires being inside "
                              f"the walls")
                else:
                    reason = (f"{actor.name} has no ordinary soldiers in their "
                              f"group in {city.name} (elite units do not count)")
                turn_log.add(
                    "secure", player_id, "secure_failed",
                    f"{actor.name}: cannot secure {city.name} — {reason}",
                    location=city_id, character_id=actor.id, success=False,
                )
                continue

            other_faction = next((
                candidate for candidate in game_state.factions.values()
                if candidate.id != player_id
                and territory.is_valid_occupation(
                    game_state, candidate.id, city_id)
            ), None)
            if other_faction:
                turn_log.add("secure", player_id, "secure_failed",
                            f"{actor.name}: {city.name} already secured by {other_faction.name}",
                            location=city_id, character_id=actor.id, success=False)
                continue

            # Establishing occupation needs the place militarily settled: no
            # other faction may still be standing inside under arms. Holding
            # one is a separate question, answered by reconciliation, so a
            # faction already occupying here is only renewing and is not asked
            # to clear the ground again.
            if (not territory.is_valid_occupation(game_state, player_id, city_id)
                    and territory.has_competing_qualifying_garrison(
                        game_state, city_id, player_id)):
                turn_log.add(
                    "secure", player_id, "secure_failed",
                    f"{actor.name}: cannot secure {city.name} — another "
                    f"faction still maintains an armed garrison inside",
                    location=city_id, character_id=actor.id, success=False,
                )
                continue

            # Secure the location
            faction.secured_city_ids.add(city_id)
            turn_log.add("secure", player_id, "secure",
                        f"{actor.name} secured {city.name}",
                        location=city_id, character_id=actor.id)


def process_fortifications(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process FORTIFY and UNFORTIFY orders that modify city defenses."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, (FortifyOrder, UnfortifyOrder)):
                if order.warnings:
                    continue  # Skip invalid orders

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    continue

                city_id = order.city_id or actor.location_city_id
                city = game_state.world_map.cities.get(city_id)
                if not city:
                    continue

                if territory.administrative_faction_id(game_state, city_id) != player_id:
                    verb = ("unfortify" if isinstance(order, UnfortifyOrder)
                            else "fortify")
                    turn_log.add(
                        "fortify", player_id, "fortify_failed",
                        f"{actor.name}: cannot {verb} {city.name} — "
                        + territory.administration_denial(
                            game_state, city_id, player_id),
                        character_id=actor.id, location=city_id, success=False,
                    )
                    continue

                current = city.fortification_level
                stone_needed = max(1, order.percent)

                if isinstance(order, FortifyOrder):
                    available_stone = actor.resources.get("stone", 0)
                    if available_stone < stone_needed:
                        turn_log.add("fortify", player_id, "fortify_failed",
                                    f"{actor.name}: insufficient stone to fortify {city.name}",
                                    character_id=actor.id, success=False)
                        continue

                    actor.resources["stone"] = available_stone - stone_needed
                    new_level = min(100, current + order.percent)
                    city.fortification_level = new_level
                    turn_log.add("fortify", player_id, "fortify",
                                f"{actor.name}: fortified {city.name} to {new_level}%", character_id=actor.id)

                else:
                    new_level = max(0, current - order.percent)
                    city.fortification_level = new_level
                    turn_log.add("fortify", player_id, "unfortify",
                                f"{actor.name}: reduced fortifications in {city.name} to {new_level}%", character_id=actor.id)


def process_diplomacy(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process ALLY, ENEMY, and NEUTRAL diplomacy orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            faction = game_state.factions.get(player_id)
            if not faction:
                continue

            if isinstance(order, AllyOrder):
                if order.warnings or not order.target_faction_id:
                    continue

                # Add to allies, remove from enemies
                faction.allies.add(order.target_faction_id)
                faction.enemies.discard(order.target_faction_id)

                target_faction = game_state.factions.get(order.target_faction_id)
                if target_faction:
                    turn_log.add("diplomacy", player_id, "ally",
                                f"Declared {target_faction.name} as ally")

            elif isinstance(order, EnemyOrder):
                if order.warnings or not order.target_faction_id:
                    continue

                # Add to enemies, remove from allies
                faction.enemies.add(order.target_faction_id)
                faction.allies.discard(order.target_faction_id)

                target_faction = game_state.factions.get(order.target_faction_id)
                if target_faction:
                    turn_log.add("diplomacy", player_id, "enemy",
                                f"Declared {target_faction.name} as enemy")

            elif isinstance(order, NeutralOrder):
                if order.warnings or not order.target_faction_id:
                    continue

                # Remove from both allies and enemies
                faction.allies.discard(order.target_faction_id)
                faction.enemies.discard(order.target_faction_id)

                target_faction = game_state.factions.get(order.target_faction_id)
                if target_faction:
                    turn_log.add("diplomacy", player_id, "neutral",
                                f"Set diplomatic stance to neutral with {target_faction.name}")

def process_status_orders(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                          turn_log: TurnLog):
    """Process NONCOM/COMBATANT and LURK/UNLURK status flags."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, NoncomOrder):
                if order.warnings:
                    continue
                for cid, cname in zip(order.character_ids, order.character_names):
                    char = game_state.characters.get(cid)
                    if not char or char.faction_id != player_id:
                        turn_log.add("status", player_id, "status_failed",
                                    f"Cannot set status for {cname}", success=False)
                        continue
                    char.is_noncom = order.set_noncom
                    label = "non-combatant" if order.set_noncom else "combatant"
                    turn_log.add("status", player_id, "noncom",
                                f"{char.name} is now a {label}",
                                character_id=char.id)

            elif isinstance(order, LurkOrder):
                if order.warnings:
                    continue
                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    continue
                # Design: "The LURK command should only be used on the leader
                # of a group. Everyone in the group will automatically be
                # included." A member who later breaks away keeps the flag only
                # if their new leader is given their own LURK order.
                actor.is_lurking = order.set_lurking
                followers = groups.group_members(actor.id, game_state)
                for member in followers:
                    member.is_lurking = order.set_lurking

                verb = "starts lurking" if order.set_lurking else "stops lurking"
                with_group = f" (with {len(followers)} in their group)" if followers else ""
                turn_log.add("status", player_id, "lurk",
                            f"{actor.name} {verb}{with_group}",
                            character_id=actor.id)

