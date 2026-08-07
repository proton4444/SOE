"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List

from spoils_engine.models import (
    GameState, UnitType, ShipType,
)
from spoils_engine.orders import (
    Order, MoveOrder, SailOrder, RecruitOrder, BuyShipOrder, AttackOrder,
    TeleportOrder, FlyOrder, AssignOrder, SummonOrder, PrayOrder, BlessOrder, CurseOrder, ResurrectOrder,
    TradeOrder,
    ScryOrder, actor_field, OfferOrder, IfOrder,
)
from spoils_engine.turn_log import TurnLog
from spoils_engine.phases.common import actor_can_act


def validate_orders(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Validate all orders and mark invalid ones with warnings.

    Every order carrying an actor goes through `actor_can_act`, so ownership,
    death and imprisonment are enforced uniformly rather than per order type.
    Order-specific preconditions (destinations, ports, skills) are checked on
    top of that.

    This runs on the orders the queue released for *this* turn, not on the raw
    submission, so an order that waited three turns is judged against the world
    it actually executes in.
    """
    # Characters named in this turn's OFFER orders may not belong to the
    # player yet: the rules let you order them on the assumption the offer is
    # accepted. Validation lets those orders through; process_offer fails them
    # if the character actually refuses.
    offered_ids = {
        o.target_id for orders in orders_by_player.values() for o in orders
        if isinstance(o, OfferOrder)
    }

    for player_id, orders in orders_by_player.items():
        for order in orders:
            # An IF statement tests a condition about (possibly) another
            # player's character; the condition evaluation owns that check.
            if isinstance(order, IfOrder):
                continue
            # Universal actor preconditions. A few order types name their
            # actor with a role-specific field instead of `actor_id`.
            actor_attr = actor_field(order)
            if hasattr(order, actor_attr):
                if not actor_can_act(order, player_id, game_state, actor_attr,
                                     offered_ids):
                    continue

            actor = game_state.characters.get(getattr(order, actor_attr, ""))

            # Order-specific preconditions
            if isinstance(order, (MoveOrder, SailOrder)):
                if not game_state.world_map.cities.get(order.destination_city_id):
                    order.warnings.append("Destination city not found")
                elif isinstance(order, SailOrder):
                    destination = game_state.world_map.cities[order.destination_city_id]
                    if not destination.is_port:
                        order.warnings.append(f"{destination.name} is not a port")

            elif isinstance(order, AttackOrder):
                faction = game_state.factions.get(player_id)
                target = game_state.factions.get(order.target_faction_id)
                if faction and target and target.id in faction.allies:
                    order.warnings.append(
                        f"{target.name} is your ally - declare them an enemy first"
                    )

            elif isinstance(order, RecruitOrder):
                if not game_state.world_map.cities.get(order.city_id):
                    order.warnings.append("City not found")

                try:
                    UnitType(order.unit_type)
                except ValueError:
                    order.warnings.append(f"Invalid unit type '{order.unit_type}'")

            elif isinstance(order, BuyShipOrder):
                city = game_state.world_map.cities.get(order.city_id)
                if not city:
                    order.warnings.append("City not found")
                elif not city.is_port:
                    order.warnings.append(f"City {city.name} is not a port")

                try:
                    ShipType(order.ship_type)
                except ValueError:
                    order.warnings.append(f"Invalid ship type '{order.ship_type}'")

            elif isinstance(order, (TeleportOrder, FlyOrder, SummonOrder, ScryOrder)):
                if actor and actor.magic_skill <= 0:
                    order.warnings.append("Character has no magic skill")

            elif isinstance(order, (PrayOrder, BlessOrder, CurseOrder, ResurrectOrder)):
                if actor and actor.religion_skill <= 0:
                    order.warnings.append("Character has no religion skill")

            elif isinstance(order, AssignOrder):
                recipient = game_state.characters.get(order.recipient_id)
                if not recipient:
                    order.warnings.append("Recipient not found")
                elif recipient.is_dead:
                    order.warnings.append(f"{recipient.name} is dead")

            elif isinstance(order, TradeOrder):
                if order.amount <= 0:
                    order.warnings.append("Trade amount must be positive")
                if order.action not in ("buy", "sell"):
                    order.warnings.append(f"Unknown trade action '{order.action}'")

