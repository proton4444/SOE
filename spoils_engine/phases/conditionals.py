"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List, Optional

from spoils_engine.models import (
    GameState, Character, UnitType, available_gold,
)
from spoils_engine.orders import (
    Order, IfOrder,
)
from spoils_engine import groups
from spoils_engine.parser import resolve_character
from spoils_engine.turn_log import TurnLog


def _count_condition_units(subject: Character, unit: str, game_state: GameState) -> int:
    """Count what an IF condition asks about, per rules.md: recruitable
    ranks, creatures, items and power the character controls."""
    if unit == "gold":
        return int(available_gold(subject, game_state.factions.get(subject.faction_id)))
    if unit == "soldier":
        return groups.group_soldier_count(subject, game_state, UnitType.SOLDIER)
    if unit == "sailor":
        return groups.group_soldier_count(subject, game_state, UnitType.SAILOR)
    if unit == "worker":
        return groups.group_soldier_count(subject, game_state, UnitType.WORKER)
    if unit == "slave":
        return groups.group_soldier_count(subject, game_state, UnitType.SLAVE)
    if unit == "horse":
        return subject.resources.get("horse", 0)
    if unit == "catapult":
        return subject.resources.get("catapult", 0)
    if unit == "weapon":
        return subject.resources.get("weapon", 0)
    if unit == "armor":
        return subject.resources.get("armor", 0)
    if unit == "wood":
        return subject.resources.get("wood", 0)
    if unit == "stone":
        return subject.resources.get("stone", 0)
    if unit == "iron":
        return subject.resources.get("iron", 0)
    if unit == "copper":
        return subject.resources.get("copper", 0)
    if unit == "silver":
        return subject.resources.get("silver", 0)
    if unit == "gems":
        return subject.resources.get("gems", 0)
    if unit == "galley":
        return sum(1 for ship in game_state.ships.values()
                   if ship.faction_id == subject.faction_id
                   and ship.location_city_id == subject.location_city_id)
    if unit in ("skeleton", "zombie", "harpy", "minotaur", "griffin",
                "chimera", "dragon", "demon"):
        return sum(creature.count for creature in game_state.summoned_creatures.values()
                   if creature.summoner_id == subject.id
                   and creature.creature_type.value == unit)
    if unit == "encumbrance":
        # No encumbrance model; the group's size in people stands in for it.
        return 1 + sum(
            stack.count for stack in game_state.unit_stacks.values()
            if stack.faction_id == subject.faction_id
            and stack.location_city_id == subject.location_city_id)
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

