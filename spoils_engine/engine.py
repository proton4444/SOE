"""
Turn processing engine for Spoils of Empire.

Processes orders in deterministic phases and updates game state.
All randomness is controlled by a seeded RNG for reproducibility.

Phase handlers live under ``spoils_engine.phases``; this module remains the
public façade (re-exports + ``run_turn``) so existing imports keep working.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from spoils_engine.models import GameState
from spoils_engine.orders import (
    Order, OfferOrder, actor_id_of,
)
from spoils_engine import order_queue
from spoils_engine.turn_log import TurnEvent, TurnLog
from spoils_engine.phases.common import allocate_id, actor_can_act
from spoils_engine.phases.pathing import (
    find_shortest_path, find_sea_route, find_route, route_miles, Route,
)
from spoils_engine.phases.validate import validate_orders
from spoils_engine.phases.groups_orders import (
    process_group_leadership, process_join, process_support, expire_support,
)
from spoils_engine.phases.movement import (
    process_movement, process_sail, process_passage, sync_elite_locations,
)
from spoils_engine.phases.recruit import process_recruit_and_buy
from spoils_engine.phases.magic import (
    process_magic, process_summon, process_religion,
    process_conjure, process_charge, process_absorb,
    process_magic_free_zones, process_item_upkeep,
)
from spoils_engine.phases.combat_phase import (
    defending_side, supporting_side, process_combat,
)
from spoils_engine.phases.units import (
    process_work, process_train, process_unname, process_create,
    process_elite_upkeep, process_assign, process_name, process_promote,
)
from spoils_engine.phases.economy import (
    process_invest, process_invest_weekly, process_income_and_upkeep,
    process_tax, process_trade, process_collect, process_build, process_mine,
)
from spoils_engine.phases.offer_preach import process_preach, process_offer
from spoils_engine.phases.conditionals import (
    evaluate_if_condition, process_if_orders,
)
from spoils_engine.phases.diplomacy import (
    process_secure, process_fortifications, process_diplomacy,
    process_status_orders,
)
from spoils_engine.phases.prisoners import (
    process_capture, process_free, process_kill, process_enslave,
    process_interrogate, process_prisoner_escape,
)
from spoils_engine.phases.intel import (
    process_probe, process_search, process_scan, orb_scan_cost,
    process_sightings,
)
from spoils_engine.phases.comms import (
    process_messages, process_post, process_report,
    process_address_and_password, expire_postings, report_pending_orders,
)
from spoils_engine.phases.finance import (
    process_get, process_transfer, process_unload,
    process_pay, process_borrow, process_repay,
)
from spoils_engine.phases.skills import process_study, process_teach
from spoils_engine.phases.cleanup import cleanup_turn


__all__ = [
    "TurnEvent", "TurnLog",
    "allocate_id", "actor_can_act",
    "find_shortest_path", "find_sea_route", "find_route", "route_miles", "Route",
    "validate_orders",
    "process_group_leadership", "process_join", "process_support", "expire_support",
    "process_movement", "process_sail", "process_passage", "sync_elite_locations",
    "process_recruit_and_buy",
    "process_magic", "process_summon", "process_religion",
    "process_conjure", "process_charge", "process_absorb",
    "process_magic_free_zones", "process_item_upkeep",
    "defending_side", "supporting_side", "process_combat",
    "process_work", "process_train", "process_unname", "process_create",
    "process_elite_upkeep", "process_assign", "process_name", "process_promote",
    "process_invest", "process_invest_weekly", "process_income_and_upkeep",
    "process_tax", "process_trade", "process_collect", "process_build", "process_mine",
    "process_preach", "process_offer",
    "evaluate_if_condition", "process_if_orders",
    "process_secure", "process_fortifications", "process_diplomacy",
    "process_status_orders",
    "process_capture", "process_free", "process_kill", "process_enslave",
    "process_interrogate", "process_prisoner_escape",
    "process_probe", "process_search", "process_scan", "orb_scan_cost",
    "process_sightings",
    "process_messages", "process_post", "process_report",
    "process_address_and_password", "expire_postings", "report_pending_orders",
    "process_get", "process_transfer", "process_unload",
    "process_pay", "process_borrow", "process_repay",
    "process_study", "process_teach",
    "cleanup_turn",
    "run_turn",
]


def run_turn(
    game_state: GameState,
    orders_by_player: Dict[str, List[Order]],
    seed: int
) -> Tuple[GameState, TurnLog]:
    """
    Process a complete game turn deterministically.

    Orders are not executed straight from `orders_by_player`. They go onto each
    character's persistent queue first, and the queue decides what this turn
    actually runs -- which for an unblocked character is everything they were
    just given. See `order_queue` for what holds work back.

    Args:
        game_state: Current game state (will be modified in-place)
        orders_by_player: Dict mapping player_id -> list of orders submitted now
        seed: RNG seed for deterministic execution

    Returns:
        Tuple of (updated_game_state, turn_log)
    """
    rng = random.Random(seed)
    turn_log = TurnLog()

    # Phase 0: Order queue. Everything below acts on what the queue released.
    orders_by_player = order_queue.process_order_queue(
        orders_by_player, game_state, turn_log
    )

    # Phase 0b: IF statements. A condition reached on the queue is judged
    # against the world it lands in, and its chosen branch joins the turn.
    process_if_orders(orders_by_player, game_state, turn_log)

    # Phase 1: Validation
    validate_orders(orders_by_player, game_state, turn_log)

    # Phase 1a: Offers. Resolved before group leadership so an accepted
    # independent character joins the faction before any order naming them
    # (the HAVE-promotes-to-leader pass) runs. A refusal fails the chained
    # orders that assumed acceptance.
    refusals = process_offer(orders_by_player, game_state, turn_log)
    for player_id, char_id in refusals:
        for order in orders_by_player.get(player_id, []):
            if (actor_id_of(order) == char_id and order.explicit_actor
                    and not isinstance(order, OfferOrder)):
                order.warnings.append(
                    "The offer to this character was refused, so their "
                    "assumed orders failed")

    # Phase 1b: Group leadership. A character given a direct order becomes a
    # group leader before the order that named them is carried out.
    process_group_leadership(orders_by_player, game_state, turn_log)

    # Phase 2: Movement
    process_movement(orders_by_player, game_state, turn_log, rng)

    # Phase 2b: Sailing, then buying passage (which is sea travel without a
    # ship) -- and elite units follow whoever led them on the way.
    process_sail(orders_by_player, game_state, turn_log, rng)
    process_passage(orders_by_player, game_state, turn_log, rng)
    sync_elite_locations(game_state)

    # Phase 3: Recruit & Buy
    process_recruit_and_buy(orders_by_player, game_state, turn_log, rng)

    # Phase 4: Magic & Summoning. ABSORB runs first so power drawn out of an
    # item is available to this turn's spells, and CHARGE last so what the
    # caster did not spend can be stowed.
    process_absorb(orders_by_player, game_state, turn_log)
    process_magic(orders_by_player, game_state, turn_log, rng)
    process_summon(orders_by_player, game_state, turn_log)
    process_conjure(orders_by_player, game_state, turn_log, rng)
    process_charge(orders_by_player, game_state, turn_log)
    process_religion(orders_by_player, game_state, turn_log, rng)

    # Walking, sailing, flying and teleporting have all resolved by now, so one
    # sweep catches everyone who ended up somewhere magic cannot exist.
    process_magic_free_zones(game_state, turn_log)

    # Phase 5: Combat
    process_combat(orders_by_player, game_state, turn_log, rng)

    # Phase 5b: Capture (prisoner taking)
    process_capture(orders_by_player, game_state, turn_log, rng)

    # Phase 6: Income & Upkeep. The weekly INVEST check runs first so the
    # growth it pays for counts in this turn's income.
    process_invest_weekly(game_state, turn_log, rng)
    process_income_and_upkeep(game_state, turn_log, rng)

    # Phase 7: Location Control & Diplomacy & Unit Management & Economics & Training
    process_secure(orders_by_player, game_state, turn_log)
    process_fortifications(orders_by_player, game_state, turn_log)
    process_diplomacy(orders_by_player, game_state, turn_log)
    process_assign(orders_by_player, game_state, turn_log)
    process_join(orders_by_player, game_state, turn_log)
    process_support(orders_by_player, game_state, turn_log)
    process_name(orders_by_player, game_state, turn_log)
    process_promote(orders_by_player, game_state, turn_log)
    process_tax(orders_by_player, game_state, turn_log)
    process_trade(orders_by_player, game_state, turn_log)
    process_collect(orders_by_player, game_state, turn_log)
    process_mine(orders_by_player, game_state, turn_log)
    process_build(orders_by_player, game_state, turn_log)
    process_free(orders_by_player, game_state, turn_log)
    process_kill(orders_by_player, game_state, turn_log)
    process_enslave(orders_by_player, game_state, turn_log)
    process_interrogate(orders_by_player, game_state, turn_log, rng)
    process_status_orders(orders_by_player, game_state, turn_log)
    process_get(orders_by_player, game_state, turn_log)
    process_transfer(orders_by_player, game_state, turn_log)
    process_unload(orders_by_player, game_state, turn_log)
    process_pay(orders_by_player, game_state, turn_log)
    process_borrow(orders_by_player, game_state, turn_log, rng)
    process_repay(orders_by_player, game_state, turn_log)
    process_study(orders_by_player, game_state, turn_log, rng)
    process_teach(orders_by_player, game_state, turn_log, rng)
    process_probe(orders_by_player, game_state, turn_log, rng)
    process_search(orders_by_player, game_state, turn_log, rng)
    process_scan(orders_by_player, game_state, turn_log)
    process_work(orders_by_player, game_state, turn_log)
    process_train(orders_by_player, game_state, turn_log)
    process_unname(orders_by_player, game_state, turn_log)
    process_create(orders_by_player, game_state, turn_log)
    process_invest(orders_by_player, game_state, turn_log)
    process_preach(orders_by_player, game_state, turn_log, rng)

    # Communication. SECURE has already resolved above, so a POST is judged
    # against who holds the town at the end of this turn, and REPORT last of
    # all so it describes the world the player will actually wake up to.
    process_address_and_password(orders_by_player, game_state, turn_log, rng)
    process_messages(orders_by_player, game_state, turn_log)
    process_post(orders_by_player, game_state, turn_log)
    process_report(orders_by_player, game_state, turn_log, rng)
    report_pending_orders(game_state, turn_log)

    # Phase 8: Fog of war — who noticed whom after all movement and status
    # changes for the turn have settled.
    process_sightings(game_state, turn_log, rng)

    # Phase 9: Cleanup. Item upkeep runs before `cleanup_turn` refills everyone
    # to full power, so a crystal only charges off a possessor who really did
    # end the turn at their natural maximum.
    expire_support(game_state, turn_log)
    expire_postings(game_state, turn_log)
    process_item_upkeep(game_state, turn_log)
    process_prisoner_escape(game_state, turn_log, rng)
    sync_elite_locations(game_state)
    process_elite_upkeep(game_state, turn_log)
    cleanup_turn(game_state)

    return (game_state, turn_log)

