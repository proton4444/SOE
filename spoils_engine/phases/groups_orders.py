"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List

from spoils_engine.models import (
    GameState,
)
from spoils_engine.orders import (
    Order, JoinOrder, SupportOrder, actor_id_of,
)
from spoils_engine import groups, order_queue
from spoils_engine.turn_log import TurnLog


def process_group_leadership(orders_by_player: Dict[str, List[Order]],
                             game_state: GameState, turn_log: TurnLog):
    """
    Give a character their independence the moment they are given an order.

    rules.md: "Whenever you use the HAVE command, the character named in the
    command will automatically become a group leader if he was not already one.
    From that point on, he will remain independent unless given specific orders
    to join another group."

    This runs before the phases that act on those orders, so a character who is
    told to go somewhere leaves with their own group rather than dragging their
    former leader's people along.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if order.warnings or not order.explicit_actor:
                continue

            actor = game_state.characters.get(actor_id_of(order))
            if not actor or actor.faction_id != player_id:
                continue

            former_leader_id = actor.group_leader_id
            if not groups.detach(actor):
                continue

            former = game_state.characters.get(former_leader_id)
            turn_log.add("groups", player_id, "became_leader",
                         f"{actor.name} left {former.name}'s group and now leads their own"
                         if former else f"{actor.name} now leads their own group",
                         character_id=actor.id)


def process_join(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                 turn_log: TurnLog):
    """Process JOIN -- the ASSIGN operation, given to the one being assigned."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, JoinOrder) or order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            target = game_state.characters.get(order.target_id)

            if not actor:
                continue
            if not target or target.faction_id != player_id:
                turn_log.add("groups", player_id, "join_failed",
                             f"{actor.name}: cannot join {order.target_name or 'them'}",
                             character_id=actor.id, success=False)
                continue

            refusal = groups.attach(actor, target, game_state)
            if refusal:
                turn_log.add("groups", player_id, "join_failed",
                             f"{actor.name} could not join {target.name}: {refusal}",
                             character_id=actor.id, success=False)
                continue

            following = len(groups.group_members(actor.id, game_state))
            brought = f" bringing {following} other(s)" if following else ""
            turn_log.add("groups", player_id, "join",
                         f"{actor.name} joined {target.name}'s group{brought}",
                         character_id=actor.id)


def process_support(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                    turn_log: TurnLog):
    """
    Process SUPPORT -- agree to fight alongside someone when they attack.

    The supporter keeps their own group, so combat leadership does not carry
    across; see `combat.calculate_faction_power`. With no duration the
    agreement stands until a HALT or STOP clears the character's queue.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SupportOrder) or order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            target_id = order.target_ids[0] if order.target_ids else ""
            target = game_state.characters.get(target_id)
            if not target:
                turn_log.add("groups", player_id, "support_failed",
                             f"{actor.name}: nobody by that name to support",
                             character_id=actor.id, success=False)
                continue

            actor.supporting_id = target.id
            if order.duration_days > 0:
                actor.support_until_turn = (
                    game_state.turn_number
                    + order_queue.turns_for_days(order.duration_days)
                )
                window = f" for {order.duration_days} day(s)"
            else:
                actor.support_until_turn = -1  # until halted
                window = " until halted"

            turn_log.add("groups", player_id, "support",
                         f"{actor.name} will fight alongside {target.name}{window}",
                         character_id=actor.id)


def expire_support(game_state: GameState, turn_log: TurnLog):
    """Drop support agreements whose time is up."""
    for char in game_state.characters.values():
        if not char.supporting_id or char.support_until_turn < 0:
            continue
        if game_state.turn_number >= char.support_until_turn:
            target = game_state.characters.get(char.supporting_id)
            char.supporting_id = ""
            char.support_until_turn = -1
            turn_log.add("groups", char.faction_id, "support_ended",
                         f"{char.name} is no longer supporting "
                         f"{target.name if target else 'anyone'}",
                         character_id=char.id)

