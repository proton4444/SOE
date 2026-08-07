"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List

from spoils_engine.models import (
    GameState, Character, UnitType, available_gold, debit_gold, credit_gold,
)
from spoils_engine.orders import (
    Order, PreachOrder, OfferOrder,
)
from spoils_engine import config, groups
from spoils_engine.turn_log import TurnLog
from spoils_engine.phases.units import _add_group_units


def process_preach(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """
    Process PREACH orders: collect tithes and donations.

    Donations scale with religion skill and location population. The preacher
    may also attract followers -- mostly unskilled workers, occasionally a
    soldier, per rules.md.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, PreachOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            daily = config.PREACH_DONATION_DAILY_PER_BAND.get(city.population_band, 0.0)
            donations = int(actor.religion_skill / 100.0 * daily * order.duration_days
                            * (0.5 + rng.random()))
            if donations > 0:
                credit_gold(actor, donations)
            followers = 0
            follower_roll = rng.random()
            if follower_roll < (actor.religion_skill / 100.0) * config.PREACH_FOLLOWER_CHANCE:
                followers = rng.randint(1, 3)

            details = []
            if donations:
                details.append(f"collected {donations}g in donations")
            else:
                details.append("collected nothing")
            if followers:
                _add_group_units(actor, game_state, UnitType.WORKER, followers)
                details.append(f"{followers} follower(s) joined")

            turn_log.add("preach", player_id, "preach",
                        f"{actor.name} preached {order.duration_days} days in "
                        f"{city.name} and {'; '.join(details)}",
                        location=city.id, character_id=actor.id)


def _offer_acceptance_threshold(target: Character, game_state: GameState) -> float:
    """The gold an offer to `target` must reach: half the square of the
    highest skill plus the value of items in their possession (rules.md)."""
    highest = max(target.combat_skill, target.magic_skill, target.religion_skill,
                  target.trading_skill, target.sailing_skill)
    threshold = config.OFFER_ACCEPT_FRACTION_OF_LEVEL_SQUARE * (highest ** 2)
    for item in game_state.magical_items.values():
        if item.holder_character_id != target.id:
            continue
        value = (item.power_current * config.OFFER_ITEM_VALUE_POWER_PER_POINT
                 + item.skill_level * config.OFFER_ITEM_VALUE_SKILL_PER_POINT
                 + item.protection * config.OFFER_ITEM_VALUE_PROTECTION_PER_POINT)
        threshold += value
    return threshold


def _transfer_ownership(target: Character, new_faction_id: str, game_state: GameState) -> None:
    """The offeree, their group, their units, ships and elite units all move
    to the new faction (rules.md: "he and everyone and everything currently
    assigned to him will become yours to control")."""
    member_ids = {m.id for m in [target] + groups.group_members(target.id, game_state)}
    for member in game_state.characters.values():
        if member.id in member_ids:
            member.faction_id = new_faction_id
    for stack in game_state.unit_stacks.values():
        if stack.owner_character_id in member_ids:
            stack.faction_id = new_faction_id
    for ship in game_state.ships.values():
        if ship.owner_character_id in member_ids:
            ship.faction_id = new_faction_id
    for unit in game_state.elite_units.values():
        if unit.leader_character_id in member_ids:
            unit.faction_id = new_faction_id


def process_offer(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                  turn_log: TurnLog) -> set[tuple[str, str]]:
    """
    Process OFFER orders: recruit an independent character (or free one of
    your prisoners) with gold.

    Acceptance is deterministic: the offer must reach half the square of the
    offeree's highest level plus item value. A character under another
    player's control always declines. Offers to one's own prisoners are
    accepted (the rules' magic ensures sincerity).

    Runs before movement and group leadership so an accepted character joins
    the faction in time for any orders chained after the offer ("Offer ...
    and have her come to Pomye") to work.

    Returns {(player_id, character_id)} of refusals, so run_turn can fail the
    chained orders that assumed acceptance.
    """
    refusals: set[tuple[str, str]] = set()
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, OfferOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            target = game_state.characters.get(order.target_id)
            if not actor or not target:
                continue

            faction = game_state.factions.get(player_id)
            if order.amount < 0:
                amount = available_gold(actor, faction) * (-order.amount / 100.0) if order.amount < -1 else available_gold(actor, faction)
            else:
                amount = order.amount

            target_faction = game_state.factions.get(target.faction_id)

            # One's own prisoner: the magic of the offer guarantees sincerity.
            if target.is_prisoner and target.captor_id and \
                    game_state.characters.get(target.captor_id, None) and \
                    game_state.characters[target.captor_id].faction_id == player_id:
                if not debit_gold(actor, faction, amount):
                    turn_log.add("offer", player_id, "offer_failed",
                                f"{actor.name}: insufficient gold to offer "
                                f"{amount:g}g to {target.name}",
                                character_id=actor.id, success=False)
                    continue
                target.is_prisoner = False
                target.captor_id = ""
                _transfer_ownership(target, player_id, game_state)
                turn_log.add("offer", player_id, "offer",
                            f"{actor.name} offered {amount:g}g and {target.name} "
                            "accepted: they join your faction, released from "
                            "prison",
                            character_id=actor.id)
                continue

            # A character already under a player's control declines politely.
            if target_faction and not target_faction.is_npc:
                turn_log.add("offer", player_id, "offer_rejected",
                            f"{target.name} declined your offer -- they are "
                            "already under another player's command",
                            character_id=actor.id, success=False)
                refusals.add((player_id, target.id))
                continue

            threshold = _offer_acceptance_threshold(target, game_state)
            if amount < threshold:
                turn_log.add("offer", player_id, "offer_rejected",
                            f"{target.name} declined your offer of {amount:g}g "
                            f"-- they hold out for at least {threshold:g}g",
                            character_id=actor.id, success=False)
                refusals.add((player_id, target.id))
                continue

            if not debit_gold(actor, faction, amount):
                turn_log.add("offer", player_id, "offer_failed",
                            f"{actor.name}: insufficient gold to offer "
                            f"{amount:g}g to {target.name}",
                            character_id=actor.id, success=False)
                continue

            _transfer_ownership(target, player_id, game_state)
            turn_log.add("offer", player_id, "offer",
                        f"{actor.name} offered {amount:g}g and {target.name} "
                        "accepted: they and their group join your faction",
                        character_id=actor.id)
    return refusals

