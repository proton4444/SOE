"""
Turn processing engine for SOE.

Processes orders in deterministic phases and updates game state.
All randomness is controlled by a seeded RNG for reproducibility.

Phase handlers live under ``soe.phases``; this module remains the
public façade (re-exports + ``run_turn``) so existing imports keep working.
"""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from soe.models import GameState
from soe import config, territory
from soe.orders import (
    Order, OfferOrder, actor_id_of,
)
from soe import order_queue
from soe.turn_log import TurnEvent, TurnLog
from soe.phases.common import allocate_id, actor_can_act
from soe.phases.pathing import (
    find_shortest_path, find_sea_route, find_route, route_miles, Route,
)
from soe.phases.validate import validate_orders
from soe.phases.groups_orders import (
    process_group_leadership, process_join, process_support, expire_support,
)
from soe.phases.movement import (
    process_movement, process_sail, process_passage, sync_elite_locations,
)
from soe.phases.recruit import process_recruit_and_buy
from soe.phases.magic import (
    process_magic, process_summon, process_religion,
    process_conjure, process_charge, process_absorb,
    process_magic_free_zones, process_item_upkeep,
)
from soe.phases.combat_phase import (
    defending_side, supporting_side, process_combat,
)
from soe.phases.units import (
    process_work, process_train, process_unname, process_create,
    process_elite_upkeep, process_disband, process_assign, process_name, process_promote,
)
from soe.phases.economy import (
    process_invest, process_invest_weekly, process_income_and_upkeep,
    process_tax, process_trade, process_collect, process_build, process_mine,
    recover_resources,
)
from soe.phases.offer_preach import process_preach, process_offer
from soe.phases.conditionals import (
    evaluate_if_condition, process_if_orders,
)
from soe.phases.diplomacy import (
    process_secure, process_fortifications, process_diplomacy,
    process_status_orders,
)
from soe.phases.prisoners import (
    process_capture, process_free, process_kill, process_enslave,
    process_interrogate, process_prisoner_escape,
)
from soe.phases.intel import (
    process_probe, process_search, process_scan, orb_scan_cost,
    process_sightings,
)
from soe.phases.comms import (
    process_messages, process_post, process_report,
    process_address_and_password, expire_postings, report_pending_orders,
)
from soe.phases.finance import (
    process_get, process_transfer, process_unload,
    process_pay, process_borrow, process_repay,
)
from soe.phases.skills import process_study, process_teach
from soe.phases.cleanup import cleanup_turn


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
    "process_elite_upkeep", "process_disband", "process_assign", "process_name", "process_promote",
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


def _run_order_batch(
    game_state: GameState,
    orders_by_player: Dict[str, List[Order]],
    rng: random.Random,
    turn_log: TurnLog,
    weekly: bool = False,
) -> None:
    """Execute every order that becomes ready at one clock instant."""

    # Phase 0b: IF statements. A condition reached on the queue is judged
    # against the world it lands in, and its chosen branch joins the turn.
    process_if_orders(orders_by_player, game_state, turn_log)
    turn_log.register_orders(orders_by_player)

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

    # Travel can remove the last local occupation group. Recruitment must see
    # the resulting authority, not an occupation expected later in the batch.
    territory.reconcile_occupations(game_state)

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
    territory.reconcile_occupations(game_state)
    combat_authority = territory.administrative_snapshot(game_state)
    process_combat(
        orders_by_player, game_state, turn_log, rng,
        fortification_authority=combat_authority,
    )

    # Phase 5b: Capture (prisoner taking)
    process_capture(orders_by_player, game_state, turn_log, rng)
    territory.reconcile_occupations(game_state)

    # Phase 6: weekly economy runs only in the first hour batch.
    if weekly:
        process_invest_weekly(game_state, turn_log, rng)
        process_income_and_upkeep(game_state, turn_log, rng)
        recover_resources(game_state)

    # Phase 7: Location Control & Diplomacy & Unit Management & Economics & Training
    process_secure(orders_by_player, game_state, turn_log)
    process_fortifications(orders_by_player, game_state, turn_log)
    process_diplomacy(orders_by_player, game_state, turn_log)
    process_assign(orders_by_player, game_state, turn_log)
    process_join(orders_by_player, game_state, turn_log)
    process_support(orders_by_player, game_state, turn_log)
    process_name(orders_by_player, game_state, turn_log)
    process_promote(orders_by_player, game_state, turn_log)
    territory.reconcile_occupations(game_state)
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
    process_disband(orders_by_player, game_state, turn_log)
    process_invest(orders_by_player, game_state, turn_log)
    process_preach(orders_by_player, game_state, turn_log, rng)

    # Late transfers, prisoner actions, and unit conversions may remove the
    # final qualifying garrison before administrative/reporting behavior.
    territory.reconcile_occupations(game_state)

    # Communication. SECURE has already resolved above, so a POST is judged
    # against who holds the town at the end of this turn, and REPORT last of
    # all so it describes the world the player will actually wake up to.
    process_address_and_password(orders_by_player, game_state, turn_log, rng)
    process_messages(orders_by_player, game_state, turn_log)
    process_post(orders_by_player, game_state, turn_log)
    process_report(orders_by_player, game_state, turn_log, rng)


def run_turn(
    game_state: GameState,
    orders_by_player: Dict[str, List[Order]],
    seed: int,
) -> Tuple[GameState, TurnLog]:
    """Process a reporting week while waking queues at exact game hours."""
    rng = random.Random(seed)
    turn_log = TurnLog()
    start_hour = max(game_state.game_time_hours,
                     game_state.turn_number * config.HOURS_PER_TURN)
    end_hour = start_hour + config.HOURS_PER_TURN
    game_state.game_time_hours = start_hour
    time_budget = order_queue.TurnTimeBudget()

    # Intake happens once; later passes only wake queues already in progress.
    ready = order_queue.process_order_queue(
        orders_by_player, game_state, turn_log, time_budget
    )
    _run_order_batch(game_state, ready, rng, turn_log, weekly=True)
    while True:
        wake_hour = order_queue.next_wake_hour(game_state, end_hour)
        if wake_hour is None:
            break
        game_state.game_time_hours = wake_hour
        ready = order_queue.resume_order_queue(
            game_state, turn_log, time_budget
        )
        if ready:
            _run_order_batch(game_state, ready, rng, turn_log)

    game_state.game_time_hours = end_hour
    report_pending_orders(game_state, turn_log)
    process_sightings(game_state, turn_log, rng)
    expire_support(game_state, turn_log)
    expire_postings(game_state, turn_log)
    process_item_upkeep(game_state, turn_log)
    process_prisoner_escape(game_state, turn_log, rng)
    sync_elite_locations(game_state)
    process_elite_upkeep(game_state, turn_log)
    cleanup_turn(game_state)
    return game_state, turn_log

