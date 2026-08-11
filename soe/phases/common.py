"""Shared helpers used by turn phases."""

from __future__ import annotations

from typing import Dict

from soe.models import GameState
from soe.orders import Order


def allocate_id(registry: Dict[str, object], prefix: str) -> str:
    """
    Allocate an entity id that is not already used in `registry`.

    Sizing an id off len(registry) alone collides once anything has been
    removed -- e.g. a stack wiped out in combat frees its number and the next
    allocation silently overwrites a live entity.
    """
    n = len(registry) + 1
    while f"{prefix}_{n}" in registry:
        n += 1
    return f"{prefix}_{n}"


def actor_can_act(order: Order, player_id: str, game_state: GameState,
                  actor_attr: str = "actor_id",
                  offered_ids: set = None) -> bool:
    """
    Check the preconditions every acting character must satisfy.

    The actor must exist, belong to the issuing player, be alive, and not be
    held prisoner. Appends a warning to the order and returns False on failure.

    `offered_ids` lists characters named in the same submission's OFFER
    orders: they are exempt from the ownership check (see validate_orders).
    """
    actor_id = getattr(order, actor_attr, "")
    if not actor_id:
        order.warnings.append("No actor specified")
        return False

    actor = game_state.characters.get(actor_id)
    if not actor:
        order.warnings.append(f"Character {actor_id} not found")
        return False

    if actor.faction_id != player_id and actor_id not in (offered_ids or set()):
        order.warnings.append("Character does not belong to you")
        return False

    if actor.is_dead:
        order.warnings.append(f"{actor.name} is dead and cannot act")
        return False

    if actor.is_prisoner:
        order.warnings.append(f"{actor.name} is a prisoner and cannot act")
        return False

    return True

