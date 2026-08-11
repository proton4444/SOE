"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List, Optional

from soe.models import (
    GameState, Character, UnitType,
)
from soe.orders import (
    Order, IfOrder,
)
from soe import groups, encumbrance
from soe.parser import resolve_character
from soe.turn_log import TurnLog


def _count_condition_units(subject: Character, unit: str, game_state: GameState) -> int:
    """Count what an IF condition asks about, per the design -- recruitable
    ranks, creatures, items and power the character controls."""
    if unit == "gold":
        return int(groups.group_gold(subject, game_state))
    if unit == "soldier":
        return groups.group_soldier_count(subject, game_state, UnitType.SOLDIER)
    if unit == "sailor":
        return groups.group_soldier_count(subject, game_state, UnitType.SAILOR)
    if unit == "worker":
        return groups.group_soldier_count(subject, game_state, UnitType.WORKER)
    if unit == "slave":
        return groups.group_soldier_count(subject, game_state, UnitType.SLAVE)
    if unit == "horse":
        return groups.group_resource_count(subject, "horse", game_state)
    if unit == "catapult":
        return groups.group_resource_count(subject, "catapult", game_state)
    if unit == "weapon":
        return groups.group_resource_count(subject, "weapon", game_state)
    if unit == "armor":
        return groups.group_resource_count(subject, "armor", game_state)
    if unit == "wood":
        return groups.group_resource_count(subject, "wood", game_state)
    if unit == "stone":
        return groups.group_resource_count(subject, "stone", game_state)
    if unit == "iron":
        return groups.group_resource_count(subject, "iron", game_state)
    if unit == "copper":
        return groups.group_resource_count(subject, "copper", game_state)
    if unit == "silver":
        return groups.group_resource_count(subject, "silver", game_state)
    if unit == "gems":
        return groups.group_resource_count(subject, "gems", game_state)
    if unit == "galley":
        return sum(1 for ship in groups.group_ships(subject, game_state)
                   if ship.location_city_id == subject.location_city_id)
    if unit in ("skeleton", "zombie", "harpy", "minotaur", "griffin",
                "chimera", "dragon", "demon"):
        return sum(creature.count for creature in game_state.summoned_creatures.values()
                   if creature.summoner_id == subject.id
                   and creature.creature_type.value == unit)
    if unit == "encumbrance":
        return int(encumbrance.group_encumbrance(subject, game_state) + 0.999999)
    if unit == "power":
        if subject.magic_skill == 0 and subject.religion_skill == 0:
            return 0
        return subject.magic_power_current + subject.religious_power_current
    return 0


def evaluate_if_condition(condition: dict, game_state: GameState, player_id: str,
                          turn_log: TurnLog, order) -> Optional[bool]:
    """Evaluate one parsed IF condition against the current state."""
    subject = resolve_character(condition["subject_name"], game_state, player_id,
                                enemy_ok=True)
    if not subject.found:
        return None

    subject_char = game_state.characters.get(subject.entity_id)
    if not subject_char or subject_char.is_dead:
        return None

    amount = int(condition.get("amount", 0))
    comparator = condition.get("comparator", "exactly")
    unit = condition.get("unit", "gold")
    modifier = condition.get("power_modifier", "")

    if unit == "power":
        if modifier == "magic" or modifier == "magical":
            value = subject_char.magic_power_current
        elif modifier == "religious" or modifier == "religion":
            value = subject_char.religious_power_current
        else:
            value = max(subject_char.magic_power_current,
                        subject_char.religious_power_current)
    else:
        value = _count_condition_units(subject_char, unit, game_state)

    if comparator in ("less than", "fewer than"):
        return value < amount
    if comparator == "more than":
        return value > amount
    if comparator == "at least":
        return value >= amount
    if comparator == "at most":
        return value <= amount
    return value == amount


def process_if_orders(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                      turn_log: TurnLog):
    """
    Evaluate IF statements and splice the chosen branch's orders into the
    turn.

    Runs right after the queue releases the turn's orders, so a condition
    waited on across turns is judged against the world it lands in -- the
    engine's version of "tested after all preceding orders have executed".
    """
    for player_id, orders in orders_by_player.items():
        spliced: List[Order] = []
        for order in orders:
            if not isinstance(order, IfOrder):
                spliced.append(order)
                continue
            if order.warnings or not order.condition:
                spliced.append(order)
                continue

            result = evaluate_if_condition(order.condition, game_state, player_id,
                                           turn_log, order)
            if result is None:
                turn_log.add("if", player_id, "if_unknown",
                            f"Condition 'if {order.condition.get('subject_name')} "
                            f"has {order.condition.get('comparator')} "
                            f"{order.condition.get('amount')} "
                            f"{order.condition.get('unit')}' could not be "
                            "resolved",
                            success=False)
                continue

            branch = order.then_orders if result else order.else_orders
            turn_log.add("if", player_id, "if_branch",
                        f"IF condition {'held' if result else 'failed'} -- "
                        f"{len(branch)} order(s) {'issued' if result else 'skipped'}",
                        character_id=order.actor_id or "")
            spliced.extend(branch)
        orders_by_player[player_id] = spliced

