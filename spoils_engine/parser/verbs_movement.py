"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from spoils_engine.models import (
    GameState,
)
from spoils_engine.orders import (
    MoveOrder, SailOrder, TeleportOrder, FlyOrder, PassageOrder,
)
from spoils_engine.parser.text import (
    strip_wand, _strip_clause_adverbs,
)
from spoils_engine.parser.resolve import (
    resolve_character, resolve_city, OrderParserBase, _resolve_destination,
)


def parse_move_order(sentence: str, game_state: GameState, player_id: str) -> Optional[MoveOrder]:
    """Parse a movement order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(MoveOrder)

    # Pattern: "have <name> go/move/travel/come to <city>".
    # rules.md: "COME -- see the GO command"; they are the same order. The
    # rules also write "have him to go to Kitesta" (give 50 armor to Thomas
    # Ames), with a `to` between the name and the verb.
    match = re.search(
        r'have\s+(.+?)\s+(?:to\s+)?(?:go|move|travel|come)\s+to\s+(.+)',
        sentence)
    if match:
        actor_name, city_name = match.group(1).strip(), match.group(2).strip()

        if not parser.resolve_actor(order, actor_name):
            return order

        _resolve_destination(city_name, game_state, order, parser)
        return order

    # Pattern: "go/move/travel/come to <city>" (implicit leader)
    match = re.search(r'^(?:go|move|travel|come)\s+to\s+(.+)', sentence)
    if match:
        city_name = match.group(1).strip()

        if not parser.resolve_actor(order, None):  # Use leader
            return order

        _resolve_destination(city_name, game_state, order, parser)
        return order

    return None


def parse_sail_order(sentence: str, game_state: GameState, player_id: str) -> Optional[SailOrder]:
    """Parse a sailing order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(SailOrder)

    # Pattern: "have <name> sail to <city>"
    match = re.search(r'have\s+(.+?)\s+sail\s+to\s+(.+)', sentence)
    if match:
        actor_name, city_name = match.group(1).strip(), match.group(2).strip()

        if not parser.resolve_actor(order, actor_name):
            return order

        city_resolved = resolve_city(city_name, game_state)
        if not city_resolved.found:
            parser.add_warning(order, f"City '{city_name}' not found")
            return order

        order.destination_city_id = city_resolved.entity_id
        return order

    # Pattern: "sail to <city>" (implicit leader)
    match = re.search(r'^sail\s+to\s+(.+)', sentence)
    if match:
        city_name = match.group(1).strip()

        if not parser.resolve_actor(order, None):  # Use leader
            return order

        city_resolved = resolve_city(city_name, game_state)
        if not city_resolved.found:
            parser.add_warning(order, f"City '{city_name}' not found")
            return order

        order.destination_city_id = city_resolved.entity_id
        return order

    return None

def parse_teleport_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TeleportOrder]:
    """Parse a teleport order."""
    sentence, wand_name = strip_wand(sentence, game_state)
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TeleportOrder)
    order.wand_name = wand_name

    # Pattern: "have <wizard> teleport <target> to <city>"
    match = re.search(r'have\s+(.+?)\s+teleport\s+(.+?)\s+to\s+(.+)', sentence)
    if match:
        wizard_name = match.group(1).strip()
        target_name = match.group(2).strip()
        city_name = match.group(3).strip()

        wizard_resolved = resolve_character(wizard_name, game_state, player_id)
        if not wizard_resolved.found:
            parser.add_warning(order, f"Character '{wizard_name}' not found")
            return order

        target_resolved = resolve_character(target_name, game_state, player_id)
        if not target_resolved.found:
            parser.add_warning(order, f"Target '{target_name}' not found")
            return order

        city_resolved = resolve_city(city_name, game_state)
        if not city_resolved.found:
            parser.add_warning(order, f"City '{city_name}' not found")
            return order

        order.actor_id = wizard_resolved.entity_id
        order.target_character_id = target_resolved.entity_id
        order.destination_city_id = city_resolved.entity_id
        order.target_name = target_name
        return order

    # Pattern: "teleport <target> to <city>" (implicit leader)
    match = re.search(r'^teleport\s+(.+?)\s+to\s+(.+)', sentence)
    if match:
        target_name = match.group(1).strip()
        city_name = match.group(2).strip()

        if not parser.resolve_actor(order, None):
            return order

        target_resolved = resolve_character(target_name, game_state, player_id)
        if not target_resolved.found:
            parser.add_warning(order, f"Target '{target_name}' not found")
            return order

        city_resolved = resolve_city(city_name, game_state)
        if not city_resolved.found:
            parser.add_warning(order, f"City '{city_name}' not found")
            return order

        order.target_character_id = target_resolved.entity_id
        order.destination_city_id = city_resolved.entity_id
        order.target_name = target_name
        return order

    return None


def parse_fly_order(sentence: str, game_state: GameState, player_id: str) -> Optional[FlyOrder]:
    """Parse a fly order (simplified)."""
    sentence, wand_name = strip_wand(sentence, game_state)
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(FlyOrder)
    order.wand_name = wand_name

    # Pattern: "have <wizard> fly to <city>"
    match = re.search(r'have\s+(.+?)\s+fly\s+to\s+(.+)', sentence)
    if match:
        wizard_name = match.group(1).strip()
        city_name = match.group(2).strip()

        wizard_resolved = resolve_character(wizard_name, game_state, player_id)
        if not wizard_resolved.found:
            parser.add_warning(order, f"Character '{wizard_name}' not found")
            return order

        city_resolved = resolve_city(city_name, game_state)
        if not city_resolved.found:
            parser.add_warning(order, f"City '{city_name}' not found")
            return order

        order.actor_id = wizard_resolved.entity_id
        order.destination_city_id = city_resolved.entity_id
        return order

    # Pattern: "fly to <city>" (implicit leader)
    match = re.search(r'^fly\s+to\s+(.+)', sentence)
    if match:
        city_name = match.group(1).strip()

        if not parser.resolve_actor(order, None):
            return order

        city_resolved = resolve_city(city_name, game_state)
        if not city_resolved.found:
            parser.add_warning(order, f"City '{city_name}' not found")
            return order

        order.destination_city_id = city_resolved.entity_id
        return order

    return None

def parse_passage_order(sentence: str, game_state: GameState, player_id: str) -> Optional[PassageOrder]:
    """
    Parse a BUY PASSAGE order: travel one direct sealane hop by merchant ship.

    Examples:
        - "Buy passage to Kitesta."
        - "Have Jim Thomas buy passage to Amesbok."
        - "Have Joe Flint definitely buy passage to Kitesta."
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(PassageOrder)

    if not re.search(r'passage\b', sentence):
        return None

    actor_match = re.search(r'have\s+(.+?)\s+(?:buy\s+)?passage\b',
                            _strip_clause_adverbs(sentence))
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    dest_match = re.search(r'passage\s+(?:to\s+)?(.+)$', sentence)
    if not dest_match:
        return None
    dest_name = dest_match.group(1).strip()
    dest = resolve_city(dest_name, game_state)
    if not dest.found:
        return parser.add_warning(order, f"City '{dest_name}' not found")
    order.destination_city_id = dest.entity_id
    order.definitely = bool(re.search(r'\bdefinitely\b', sentence))
    return order

