"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import math
import random
from typing import Dict, List

from spoils_engine.models import (
    GameState, UnitStack, UnitType, LocationPosition, debit_gold, credit_gold,
)
from spoils_engine.orders import (
    Order, MoveOrder, SailOrder, PassageOrder,
)
from spoils_engine import config, groups, encumbrance
from spoils_engine.turn_log import TurnLog
from spoils_engine.phases.common import allocate_id
from spoils_engine.phases.pathing import (
    find_shortest_path, find_sea_route,
)


def process_movement(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                     turn_log: TurnLog, rng: random.Random):
    """Process all movement orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, MoveOrder):
                continue

            if order.warnings:
                continue  # Skip invalid orders

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            # Find path
            path, cost = find_shortest_path(actor.location_city_id, order.destination_city_id, game_state)

            if not path or cost == float('inf'):
                order.warnings.append("No path found to destination")
                turn_log.add("movement", player_id, "move_failed",
                            f"{actor.name} could not find path to destination",
                            character_id=actor.id, success=False)
                continue

            # Check movement points
            if cost > actor.movement_points:
                order.warnings.append(f"Insufficient movement points (need {cost}, have {actor.movement_points})")
                turn_log.add("movement", player_id, "move_failed",
                            f"{actor.name} lacks movement points (need {cost:.1f}, have {actor.movement_points})",
                            character_id=actor.id, success=False)
                continue

            # Move character, and whoever is travelling with them. rules.md:
            # a group goes where its leader goes. Position (inside/outside/near)
            # is shared by the travelling party.
            start_city = game_state.world_map.cities[actor.location_city_id]
            end_city = game_state.world_map.cities[order.destination_city_id]
            try:
                arrive_pos = LocationPosition(order.destination_position or "inside")
            except ValueError:
                arrive_pos = LocationPosition.INSIDE
            travelled = groups.move_group(
                actor, order.destination_city_id, game_state, position=arrive_pos
            )
            actor.location_city_id = order.destination_city_id
            actor.location_position = arrive_pos
            # Round up: truncating made every sub-1.0 hop (excellent roads cost
            # 0.5) free, so a character could cross the map without ever
            # spending a movement point.
            actor.movement_points -= max(1, math.ceil(cost))
            for member in travelled:
                member.movement_points -= max(1, math.ceil(cost))

            escort = groups.describe_escort(travelled, actor, game_state)
            pos_note = "" if arrive_pos == LocationPosition.INSIDE else f" ({arrive_pos.value})"
            turn_log.add("movement", player_id, "move",
                        f"{actor.name} moved from {start_city.name} to {end_city.name}"
                        f"{pos_note}{escort} (cost: {cost:.1f})",
                        location=end_city.id, character_id=actor.id)


def process_sail(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                 turn_log: TurnLog, rng: random.Random):
    """Process all sailing orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SailOrder):
                continue

            if order.warnings:
                continue  # Skip invalid orders

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            origin_city_id = actor.location_city_id
            travelling = [
                member for member in groups.group_members(actor.id, game_state)
                if member.location_city_id == origin_city_id
                and not member.is_dead and not member.is_prisoner
            ]
            travelling_group_ids = {actor.id, *(member.id for member in travelling)}

            # Find a ship at the actor's location
            ship = None
            if order.ship_id:
                ship = game_state.ships.get(order.ship_id)
                if (not ship or ship.faction_id != player_id
                        or (ship.owner_character_id
                            and ship.owner_character_id not in travelling_group_ids)):
                    turn_log.add("sail", player_id, "sail_failed",
                                f"{actor.name}: specified ship not found or not owned",
                                character_id=actor.id, success=False)
                    continue
                if ship.location_city_id != actor.location_city_id:
                    turn_log.add("sail", player_id, "sail_failed",
                                f"{actor.name}: ship not at current location",
                                character_id=actor.id, success=False)
                    continue
            else:
                # Auto-select first available ship at location
                for s in game_state.ships.values():
                    if (s.faction_id == player_id
                            and (not s.owner_character_id
                                 or s.owner_character_id in travelling_group_ids)
                            and s.location_city_id == actor.location_city_id):
                        ship = s
                        break

            if not ship:
                turn_log.add("sail", player_id, "sail_failed",
                            f"{actor.name}: no ship available at current location",
                            character_id=actor.id, success=False)
                continue

            # Find sea route
            path, cost = find_sea_route(actor.location_city_id, order.destination_city_id, game_state)

            if not path or cost == float('inf'):
                turn_log.add("sail", player_id, "sail_failed",
                            f"{actor.name}: no sea route found to destination",
                            character_id=actor.id, success=False)
                continue

            # Assigned units belong to the captain's group. Unassigned local
            # stacks remain available as the faction's port crew, but a stack
            # assigned to an unrelated character is neither crew nor cargo.
            def travels_with_captain(stack: UnitStack) -> bool:
                return (not stack.owner_character_id
                        or stack.owner_character_id in travelling_group_ids)

            # Count sailors and rowers available to this sailing group.
            sailors_count = 0
            total_crew = 0  # Everyone except captain can row
            for stack in game_state.unit_stacks.values():
                if (stack.faction_id == player_id
                        and stack.location_city_id == actor.location_city_id
                        and travels_with_captain(stack)):
                    if stack.unit_type == UnitType.SAILOR:
                        sailors_count += stack.count
                    total_crew += stack.count

            # Check crew requirements
            MIN_SAILORS = 10
            OPTIMAL_ROWERS = 40

            if sailors_count < MIN_SAILORS:
                turn_log.add("sail", player_id, "sail_failed",
                            f"{actor.name}: insufficient sailors (need {MIN_SAILORS}, have {sailors_count})",
                            character_id=actor.id, success=False)
                continue

            # Calculate sailing efficiency based on crew
            available_rowers = total_crew - MIN_SAILORS  # Subtract required sailors
            rowing_efficiency = min(1.0, available_rowers / OPTIMAL_ROWERS) if OPTIMAL_ROWERS > 0 else 0.5

            # Simplified: Sailing always succeeds if we have minimum crew and sea route exists
            # In full implementation, would factor in captain's sailing skill and trip duration

            # Move the ship and captain
            start_city = game_state.world_map.cities[actor.location_city_id]
            end_city = game_state.world_map.cities[order.destination_city_id]

            ship.location_city_id = order.destination_city_id
            actor.location_city_id = order.destination_city_id
            for member in travelling:
                member.location_city_id = order.destination_city_id

            # Load units onto the ship, up to its capacity. Previously every
            # stack in the port sailed along regardless of capacity, so a
            # single galley could ferry an unlimited army.
            berths = ship.capacity
            embarked = 0
            for stack in sorted(game_state.unit_stacks.values(), key=lambda s: s.id):
                if (stack.faction_id != player_id
                        or stack.location_city_id != start_city.id
                        or not travels_with_captain(stack)):
                    continue
                if berths <= 0:
                    break

                if stack.count <= berths:
                    stack.location_city_id = order.destination_city_id
                    berths -= stack.count
                    embarked += stack.count
                else:
                    # Split the stack: only `berths` units fit aboard
                    boarding = berths
                    stack.count -= boarding
                    new_stack_id = allocate_id(game_state.unit_stacks, "stack")
                    game_state.unit_stacks[new_stack_id] = UnitStack(
                        id=new_stack_id,
                        faction_id=stack.faction_id,
                        location_city_id=order.destination_city_id,
                        unit_type=stack.unit_type,
                        count=boarding,
                        owner_character_id=stack.owner_character_id,
                    )
                    berths = 0
                    embarked += boarding

            efficiency_note = f" (rowing efficiency: {rowing_efficiency * 100:.0f}%)" if rowing_efficiency < 1.0 else ""
            efficiency_note += f" carrying {embarked} units" if embarked else ""
            efficiency_note += groups.describe_escort(travelling, actor, game_state)
            turn_log.add("sail", player_id, "sail",
                        f"{actor.name} sailed from {start_city.name} to {end_city.name}{efficiency_note}",
                        location=end_city.id, character_id=actor.id)

def process_passage(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                    turn_log: TurnLog, rng: random.Random):
    """
    Process BUY PASSAGE orders: travel one direct sealane hop on a merchant
    ship.

    Cost is the group's size in gold (encumbrance is unmodelled). Passage may
    fail -- the bigger the group, the harder to find a berth -- and
    `definitely` improves the odds. On success the whole group travels, like
    any other movement.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, PassageOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            start_city = game_state.world_map.cities.get(actor.location_city_id)
            end_city = game_state.world_map.cities.get(order.destination_city_id)
            if not start_city or not end_city:
                continue
            if start_city.id == end_city.id:
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: already at {end_city.name}",
                            character_id=actor.id, success=False)
                continue

            # One direct sealane hop only (rules.md).
            path, cost = find_sea_route(actor.location_city_id, order.destination_city_id, game_state)
            if not path or cost == float('inf') or len(path) != 2:
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: no direct sealane from "
                            f"{start_city.name} to {end_city.name}",
                            character_id=actor.id, success=False)
                continue

            owners = [actor] + groups.group_members(actor.id, game_state)
            people = len(owners)
            for owner in owners:
                people += sum(stack.count for stack in groups.owned_stacks(owner.id, game_state)
                              if stack.location_city_id == actor.location_city_id)

            cargo = encumbrance.group_encumbrance(actor, game_state)
            fare = max(1, math.ceil(cargo * config.PASSAGE_COST_PER_PERSON))
            faction = game_state.factions.get(player_id)
            if not debit_gold(actor, faction, fare):
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: cannot afford passage "
                            f"({fare}g for a party of {people})",
                            character_id=actor.id, success=False)
                continue

            chance = config.PASSAGE_BASE_CHANCE - config.PASSAGE_SIZE_PENALTY_PER_100 * (cargo / 100.0)
            if order.definitely:
                chance += config.PASSAGE_DEFINITELY_BONUS
            chance = max(0.0, min(1.0, chance))

            if rng.random() > chance:
                credit_gold(actor, fare)
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: no berth found on the {start_city.name}-"
                            f"{end_city.name} run for a party of {people} "
                            "(refunded the fare)",
                            character_id=actor.id, success=False)
                continue

            travelled = groups.move_group(actor, end_city.id, game_state)
            actor.location_city_id = end_city.id
            escort = groups.describe_escort(travelled, actor, game_state)
            turn_log.add("passage", player_id, "passage",
                        f"{actor.name} bought passage from {start_city.name} to "
                        f"{end_city.name}{escort} (fare {fare}g)",
                        location=end_city.id, character_id=actor.id)

def sync_elite_locations(game_state: GameState) -> None:
    """Elite units travel with their group leader; keep their stored location
    in step whenever the leader moves."""
    for unit in game_state.elite_units.values():
        leader = game_state.characters.get(unit.leader_character_id)
        if leader and not leader.is_dead:
            unit.location_city_id = leader.location_city_id

