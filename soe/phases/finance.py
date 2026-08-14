"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from typing import Dict, List

from soe.models import (
    GameState, UnitStack, UnitType, available_gold, debit_gold, credit_gold,
)
from soe.orders import (
    Order, GetOrder, TransferOrder, UnloadOrder, PayOrder, BorrowOrder, RepayOrder,
)
from soe import config, groups
from soe.turn_log import TurnLog
from soe.phases.common import allocate_id


def process_get(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process GET/TAKE/OBTAIN — inverse of ASSIGN/GIVE."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, GetOrder) or order.warnings:
                continue
            recipient = game_state.characters.get(order.actor_id)
            donor = game_state.characters.get(order.donor_id)
            if not recipient or not donor:
                continue

            # Cannot take from another player's free character
            donor_is_prisoner = donor.is_prisoner and donor.captor_id == recipient.id
            if donor.faction_id != player_id and not donor_is_prisoner:
                turn_log.add("get", player_id, "get_failed",
                            f"{recipient.name}: cannot take from {donor.name} (not under your control)",
                            character_id=recipient.id, success=False)
                continue

            if recipient.location_city_id != donor.location_city_id:
                turn_log.add("get", player_id, "get_failed",
                            f"{recipient.name}: {donor.name} is not at the same location",
                            character_id=recipient.id, success=False)
                continue

            # Character-join form: no gold/units/resources — attach the donor.
            if (order.gold_amount <= 0 and order.unit_count <= 0
                    and not order.resources):
                refusal = groups.attach(donor, recipient, game_state)
                if refusal:
                    turn_log.add("get", player_id, "get_failed",
                                f"{donor.name} could not join {recipient.name}: {refusal}",
                                character_id=recipient.id, success=False)
                    continue
                turn_log.add("get", player_id, "get_join",
                            f"{donor.name} joined {recipient.name}",
                            character_id=recipient.id)
                continue

            if order.gold_amount > 0:
                donor_faction = game_state.factions.get(donor.faction_id)
                if debit_gold(donor, donor_faction if donor.faction_id == player_id else None,
                              order.gold_amount):
                    credit_gold(recipient, order.gold_amount)
                    turn_log.add("get", player_id, "get_gold",
                                f"{recipient.name} took {order.gold_amount}g from {donor.name}",
                                character_id=recipient.id)
                else:
                    turn_log.add("get", player_id, "get_failed",
                                f"{recipient.name}: {donor.name} has insufficient gold",
                                character_id=recipient.id, success=False)
                    continue

            for kind, wanted in order.resources.items():
                amount = wanted if wanted >= 0 else donor.resources.get(kind, 0)
                if donor.resources.get(kind, 0) < amount:
                    turn_log.add("get", player_id, "get_failed",
                                f"{recipient.name}: {donor.name} has "
                                f"insufficient {kind}",
                                character_id=recipient.id, success=False)
                    continue
                donor.resources[kind] = donor.resources.get(kind, 0) - amount
                recipient.resources[kind] = (
                    recipient.resources.get(kind, 0) + amount)
                turn_log.add("get", player_id, "get_resource",
                            f"{recipient.name} took {amount} {kind} "
                            f"from {donor.name}",
                            character_id=recipient.id)

            if order.unit_count > 0 and order.unit_type:
                # Donor-owned first, then the unowned local pool — same as ASSIGN.
                donor_stack = None
                for stack in game_state.unit_stacks.values():
                    if (stack.faction_id == donor.faction_id
                            and stack.location_city_id == donor.location_city_id
                            and stack.unit_type.name == order.unit_type
                            and stack.owner_character_id == donor.id):
                        donor_stack = stack
                        break
                if donor_stack is None or donor_stack.count < order.unit_count:
                    for stack in game_state.unit_stacks.values():
                        if (stack.faction_id == donor.faction_id
                                and stack.location_city_id == donor.location_city_id
                                and stack.unit_type.name == order.unit_type
                                and not stack.owner_character_id):
                            donor_stack = stack
                            break
                if not donor_stack or donor_stack.count < order.unit_count:
                    turn_log.add("get", player_id, "get_failed",
                                f"{recipient.name}: not enough {order.unit_type.lower()}s to take",
                                character_id=recipient.id, success=False)
                    continue
                donor_stack.count -= order.unit_count
                recip_stack = next(
                    (s for s in game_state.unit_stacks.values()
                     if s.faction_id == recipient.faction_id
                     and s.location_city_id == recipient.location_city_id
                     and s.unit_type.name == order.unit_type
                     and s.owner_character_id == recipient.id),
                    None,
                )
                if recip_stack:
                    recip_stack.count += order.unit_count
                else:
                    sid = allocate_id(game_state.unit_stacks, "stack")
                    game_state.unit_stacks[sid] = UnitStack(
                        id=sid,
                        faction_id=recipient.faction_id,
                        location_city_id=recipient.location_city_id,
                        unit_type=UnitType[order.unit_type],
                        count=order.unit_count,
                        owner_character_id=recipient.id,
                    )
                if donor_stack.count <= 0:
                    del game_state.unit_stacks[donor_stack.id]
                turn_log.add("get", player_id, "get_units",
                            f"{recipient.name} took {order.unit_count} "
                            f"{order.unit_type.lower()}s from {donor.name}",
                            character_id=recipient.id)


def process_transfer(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Banking-guild gold transfer with fee."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, TransferOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            recipient = game_state.characters.get(order.recipient_id)
            if not actor or not recipient:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                turn_log.add("transfer", player_id, "transfer_failed",
                            f"{actor.name}: no banking office here",
                            character_id=actor.id, success=False)
                continue

            faction = game_state.factions.get(player_id)
            amount = order.gold_amount
            if amount <= 0:
                amount = int(available_gold(actor, faction))
            if amount <= 0:
                turn_log.add("transfer", player_id, "transfer_failed",
                            f"{actor.name}: nothing to transfer",
                            character_id=actor.id, success=False)
                continue

            fee = config.transfer_fee(amount)
            total = amount + fee
            if not debit_gold(actor, faction, total):
                turn_log.add("transfer", player_id, "transfer_failed",
                            f"{actor.name}: need {total}g ({amount}g + {fee}g fee)",
                            character_id=actor.id, success=False)
                continue

            credit_gold(recipient, amount)
            turn_log.add("transfer", player_id, "transfer_success",
                        f"{actor.name} transferred {amount}g to {recipient.name} "
                        f"(fee {fee}g)",
                        character_id=actor.id)


def process_unload(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process UNLOAD -- turn a member of your group loose without ordering them
    to do anything.

    Design: "you can always make a character a group leader by simply giving
    him an order. However, the UNLOAD command is useful when you simply want a
    character to become a group leader and not do anything else."
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, UnloadOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            for tid, tname in zip(order.target_ids, order.target_names):
                target = game_state.characters.get(tid)
                if not target or target.faction_id != player_id:
                    turn_log.add("unload", player_id, "unload_failed",
                                f"{actor.name}: cannot unload {tname}",
                                character_id=actor.id, success=False)
                    continue
                if target.location_city_id != actor.location_city_id:
                    turn_log.add("unload", player_id, "unload_failed",
                                f"{actor.name}: {target.name} is not co-located",
                                character_id=actor.id, success=False)
                    continue
                if not groups.detach(target):
                    turn_log.add("unload", player_id, "unload_failed",
                                f"{actor.name}: {target.name} already leads their own group",
                                character_id=actor.id, success=False)
                    continue
                turn_log.add("unload", player_id, "unload_success",
                            f"{actor.name} unloaded {target.name}, who now leads their own group",
                            character_id=actor.id)


def process_pay(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Pay down wage debt from the actor's purse."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, PayOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            faction = game_state.factions.get(player_id)
            if not actor or not faction:
                continue

            if order.gold_amount > 0:
                amount = float(order.gold_amount)
            else:
                # Pay off debt only (no surplus) when amount omitted
                amount = min(faction.wage_debt, available_gold(actor, faction))

            if amount <= 0:
                turn_log.add("pay", player_id, "pay_failed",
                            f"{actor.name}: nothing to pay",
                            character_id=actor.id, success=False)
                continue
            if not debit_gold(actor, faction, amount):
                turn_log.add("pay", player_id, "pay_failed",
                            f"{actor.name}: insufficient gold",
                            character_id=actor.id, success=False)
                continue

            faction.wage_debt = round(faction.wage_debt - amount, 1)
            # Negative debt = surplus credit (rules allow this)
            label = "debt" if faction.wage_debt >= 0 else "surplus"
            turn_log.add("pay", player_id, "pay_success",
                        f"{actor.name} paid {amount}g toward wages "
                        f"({label} now {abs(faction.wage_debt)}g)",
                        character_id=actor.id)


def process_borrow(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog, rng: random.Random):
    """Borrow gold from the bankers guild."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, BorrowOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            faction = game_state.factions.get(player_id)
            if not actor or not faction:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            amount = order.gold_amount or config.BORROW_MAX_AMOUNT
            # Chance scales with city size and character impressiveness
            band_bonus = {
                "TINY": -0.15, "SMALL": 0.0, "MEDIUM": 0.1, "LARGE": 0.2,
            }
            # PopulationBand is enum with values like "< 10k" — use name
            band_name = city.population_band.name if hasattr(city.population_band, "name") else "SMALL"
            impress = (actor.combat_skill + actor.magic_skill + actor.religion_skill
                       + actor.trading_skill) / 200
            debt_penalty = min(0.4, faction.loan_balance / 2000)
            chance = config.BORROW_BASE_CHANCE + band_bonus.get(band_name, 0) + impress - debt_penalty
            chance = max(0.05, min(0.95, chance))

            if rng.random() > chance:
                turn_log.add("borrow", player_id, "borrow_failed",
                            f"{actor.name}: loan of {amount}g refused in {city.name}",
                            character_id=actor.id, success=False)
                continue

            credit_gold(actor, amount)
            faction.loan_balance = round(faction.loan_balance + amount, 2)
            faction.loan_grace_turns = max(faction.loan_grace_turns, config.BORROW_GRACE_TURNS)
            turn_log.add("borrow", player_id, "borrow_success",
                        f"{actor.name} borrowed {amount}g in {city.name} "
                        f"(balance {faction.loan_balance}g)",
                        character_id=actor.id)


def process_repay(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Repay bankers-guild debt."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, RepayOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            faction = game_state.factions.get(player_id)
            if not actor or not faction:
                continue

            if faction.loan_balance <= 0:
                turn_log.add("repay", player_id, "repay_failed",
                            f"{actor.name}: no outstanding loan",
                            character_id=actor.id, success=False)
                continue

            if order.gold_amount > 0:
                amount = min(float(order.gold_amount), faction.loan_balance)
            else:
                amount = min(faction.loan_balance, available_gold(actor, faction))

            if amount <= 0:
                turn_log.add("repay", player_id, "repay_failed",
                            f"{actor.name}: nothing to repay with",
                            character_id=actor.id, success=False)
                continue
            if not debit_gold(actor, faction, amount):
                turn_log.add("repay", player_id, "repay_failed",
                            f"{actor.name}: insufficient gold",
                            character_id=actor.id, success=False)
                continue

            faction.loan_balance = round(faction.loan_balance - amount, 2)
            if faction.loan_balance <= 0:
                faction.loan_balance = 0.0
                faction.loan_grace_turns = 0
            turn_log.add("repay", player_id, "repay_success",
                        f"{actor.name} repaid {amount}g "
                        f"(loan balance {faction.loan_balance}g)",
                        character_id=actor.id)

