"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List

from spoils_engine.models import (
    GameState, UnitStack, Ship, UnitType, ShipType, available_gold, debit_gold,
)
from spoils_engine.orders import (
    Order, RecruitOrder, BuyShipOrder,
)
from spoils_engine import config, territory
from spoils_engine.turn_log import TurnLog
from spoils_engine.phases.common import allocate_id


def process_recruit_and_buy(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                            turn_log: TurnLog, rng: random.Random):
    """Process recruitment and ship purchase orders."""
    # Track recruitment per city to enforce caps
    recruit_counts = defaultdict(lambda: defaultdict(int))

    for player_id, orders in orders_by_player.items():
        faction = game_state.factions.get(player_id)
        if not faction:
            continue

        for order in orders:
            # Handle RecruitOrder
            if isinstance(order, RecruitOrder):
                if order.warnings:
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    continue
                # "Go to Kitesta and recruit 10 soldiers" names no city for the
                # recruiting, so the parser could only guess at where the actor
                # would be -- and it guessed before the move. Read the real
                # location now. A city the player did name stands as written.
                if order.city_implicit and actor.location_city_id:
                    order.city_id = actor.location_city_id
                city = game_state.world_map.cities.get(order.city_id)
                if not city:
                    continue

                # The actor must actually stand in the city: a chained order
                # behind a move that failed (no path, insufficient movement
                # points) has no right to recruit from afar.
                if actor.location_city_id != order.city_id:
                    order.warnings.append(
                        f"{actor.name} is not in {city.name}")
                    turn_log.add("recruit", player_id, "recruit_failed",
                                f"{actor.name} is not in {city.name}",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                authority_id = territory.administrative_faction_id(
                    game_state, order.city_id)
                # Unclaimed cities keep their existing open recruitment
                # behavior; this model does not invent a neutral authority.
                if authority_id is not None and authority_id != player_id:
                    turn_log.add(
                        "recruit", player_id, "recruit_failed",
                        f"{actor.name}: cannot recruit in {city.name} — "
                        + territory.administration_denial(
                            game_state, city.id, player_id),
                        location=city.id, character_id=actor.id, success=False,
                    )
                    continue

                # Check recruit cap
                cap = config.get_recruit_cap_for_city(city.population_band)
                already_recruited = recruit_counts[order.city_id][order.unit_type]

                if already_recruited + order.count > cap:
                    available = cap - already_recruited
                    order.count = max(0, available)
                    if order.count == 0:
                        order.warnings.append(f"Recruitment cap reached in {city.name}")
                        turn_log.add("recruit", player_id, "recruit_failed",
                                    f"Recruitment cap reached in {city.name}",
                                    location=city.id, character_id=actor.id, success=False)
                        continue

                # Check cost (spent from the actor's purse / legacy treasury)
                unit_type_enum = UnitType(order.unit_type)
                cost = config.get_recruit_cost(unit_type_enum) * order.count

                if not debit_gold(actor, faction, cost):
                    have = available_gold(actor, faction)
                    order.warnings.append(f"Insufficient gold (need {cost}, have {have})")
                    turn_log.add("recruit", player_id, "recruit_failed",
                                f"Insufficient gold to recruit {order.count} "
                                f"{order.unit_type} in {city.name} "
                                f"(need {cost:g}g, have {have:g}g)",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                # Create unit stack. Recruits belong to whoever raised them, so
                # they march with that character rather than being left behind.
                stack_id = allocate_id(game_state.unit_stacks, f"stack_{player_id}")
                new_stack = UnitStack(
                    id=stack_id,
                    faction_id=player_id,
                    location_city_id=order.city_id,
                    unit_type=unit_type_enum,
                    count=order.count,
                    owner_character_id=actor.id,
                )
                game_state.unit_stacks[stack_id] = new_stack

                # Update recruit count
                recruit_counts[order.city_id][order.unit_type] += order.count

                turn_log.add("recruit", player_id, "recruit",
                            f"{actor.name} recruited {order.count} {order.unit_type} in {city.name} for {cost}g",
                            location=city.id, character_id=actor.id)

            # Handle BuyShipOrder
            elif isinstance(order, BuyShipOrder):
                if order.warnings:
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    continue
                if order.city_implicit and actor.location_city_id:
                    order.city_id = actor.location_city_id
                city = game_state.world_map.cities.get(order.city_id)
                if not city:
                    continue

                # Buying a ship requires standing at the port (see the recruit
                # guard above: a failed move must fail the chained order too).
                if actor.location_city_id != order.city_id:
                    order.warnings.append(
                        f"{actor.name} is not in {city.name}")
                    turn_log.add("buy_ship", player_id, "buy_failed",
                                f"{actor.name} is not in {city.name}",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                # Check cost
                ship_type_enum = ShipType(order.ship_type)
                cost = config.get_ship_cost(ship_type_enum) * order.count

                if not debit_gold(actor, faction, cost):
                    have = available_gold(actor, faction)
                    order.warnings.append(f"Insufficient gold (need {cost}, have {have})")
                    turn_log.add("buy_ship", player_id, "buy_failed",
                                f"Insufficient gold to buy {order.count} {order.ship_type}",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                # Create ships
                for i in range(order.count):
                    ship_id = allocate_id(game_state.ships, f"ship_{player_id}")
                    new_ship = Ship(
                        id=ship_id,
                        faction_id=player_id,
                        location_city_id=order.city_id,
                        ship_type=ship_type_enum,
                        owner_character_id=actor.id,
                    )
                    game_state.ships[ship_id] = new_ship

                turn_log.add("buy_ship", player_id, "buy_ship",
                            f"{actor.name} bought {order.count} {order.ship_type} in {city.name} for {cost}g",
                            location=city.id, character_id=actor.id)

