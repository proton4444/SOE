"""
Natural-language order parser (rule-based).

Parses English-like commands into structured Order objects.
This implementation uses regex and string matching, but the
interface is designed to be replaceable with an LLM-based parser.
"""

import re
from typing import Optional

from spoils_engine.models import GameState, UnitType, ShipType
from spoils_engine.orders import (
    Order, MoveOrder, RecruitOrder, BuyShipOrder, AttackOrder, TeleportOrder
)


# ============================================================================
# PARSING UTILITIES
# ============================================================================

def normalize_text(text: str) -> str:
    """Normalize text for parsing (lowercase, clean whitespace)."""
    # Remove comments (# to end of line)
    text = re.sub(r'#.*?$', '', text, flags=re.MULTILINE)
    # Remove commas, colons, semicolons (rules say they're ignored)
    text = text.replace(',', ' ').replace(':', ' ').replace(';', ' ')
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.lower()


def extract_sentences(text: str) -> list[str]:
    """Split text into sentences (periods delimit sentences)."""
    # Split on periods, keep non-empty
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    return sentences


def extract_number(text: str, pattern: str) -> Optional[int]:
    """Extract a number from text using a regex pattern."""
    match = re.search(pattern, text)
    if match:
        try:
            return int(match.group(1))
        except (ValueError, IndexError):
            pass
    return None


# ============================================================================
# ENTITY RESOLUTION
# ============================================================================

def resolve_character(name_text: str, game_state: GameState, player_id: str) -> Optional[tuple[str, str]]:
    """
    Resolve a character name to ID.

    Args:
        name_text: Character name from order text
        game_state: Current game state
        player_id: Player issuing the order

    Returns:
        Tuple of (character_id, resolved_name) or None
    """
    # Try to find character in player's faction
    char = game_state.get_character_by_name(name_text, faction_id=player_id)
    if char:
        return (char.id, char.name)

    # Try without faction restriction (for targets)
    char = game_state.get_character_by_name(name_text)
    if char:
        return (char.id, char.name)

    return None


def resolve_city(name_text: str, game_state: GameState) -> Optional[tuple[str, str]]:
    """
    Resolve a city name to ID.

    Args:
        name_text: City name from order text
        game_state: Current game state

    Returns:
        Tuple of (city_id, resolved_name) or None
    """
    city = game_state.world_map.get_city_by_name(name_text)
    if city:
        return (city.id, city.name)
    return None


# ============================================================================
# ORDER PARSERS
# ============================================================================

def parse_move_order(sentence: str, game_state: GameState, player_id: str) -> Optional[MoveOrder]:
    """
    Parse a movement order.

    Patterns:
        - "have <char> go to <city>"
        - "have <char> move to <city>"
        - "have <char> travel to <city>"
        - "go to <city>" (implicit: player's leader)
    """
    order = MoveOrder(player_id=player_id, original_text=sentence)

    # Pattern: "have <name> go/move/travel to <city>"
    match = re.search(r'have\s+(.+?)\s+(?:go|move|travel)\s+to\s+(.+)', sentence)
    if match:
        char_name = match.group(1).strip()
        city_name = match.group(2).strip()

        char_result = resolve_character(char_name, game_state, player_id)
        if not char_result:
            order.warnings.append(f"Character '{char_name}' not found")
            return order

        city_result = resolve_city(city_name, game_state)
        if not city_result:
            order.warnings.append(f"City '{city_name}' not found")
            return order

        order.actor_id = char_result[0]
        order.destination_city_id = city_result[0]
        return order

    # Pattern: "go/move/travel to <city>" (implicit leader)
    match = re.search(r'^(?:go|move|travel)\s+to\s+(.+)', sentence)
    if match:
        city_name = match.group(1).strip()
        city_result = resolve_city(city_name, game_state)
        if not city_result:
            order.warnings.append(f"City '{city_name}' not found")
            return order

        # Find player's leader (first character of faction)
        faction = game_state.factions.get(player_id)
        if not faction:
            order.warnings.append("Faction not found")
            return order

        # Find first character
        leader = None
        for char in game_state.characters.values():
            if char.faction_id == player_id:
                leader = char
                break

        if not leader:
            order.warnings.append("No leader character found")
            return order

        order.actor_id = leader.id
        order.destination_city_id = city_result[0]
        return order

    return None


def parse_recruit_order(sentence: str, game_state: GameState, player_id: str) -> Optional[RecruitOrder]:
    """
    Parse a recruitment order.

    Patterns:
        - "have <char> recruit <num> <type> in <city>"
        - "have <char> recruit <num> <type>" (implicit: current location)
        - "recruit <num> <type> in <city>" (implicit leader)
        - "recruit <num> <type>" (implicit leader, current location)
    """
    order = RecruitOrder(player_id=player_id, original_text=sentence)

    # Pattern: "have <name> recruit <num> <type> [in <city>]"
    match = re.search(r'have\s+(.+?)\s+recruit\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        char_name = match.group(1).strip()
        count = int(match.group(2))
        unit_type = match.group(3).strip().rstrip('s')  # Remove plural 's'
        city_name = match.group(4).strip() if match.group(4) else None

        char_result = resolve_character(char_name, game_state, player_id)
        if not char_result:
            order.warnings.append(f"Character '{char_name}' not found")
            return order

        # Validate unit type
        if unit_type not in [ut.value for ut in UnitType]:
            order.warnings.append(f"Invalid unit type '{unit_type}'")
            return order

        order.actor_id = char_result[0]
        order.count = count
        order.unit_type = unit_type

        # Resolve city (or use character's current location)
        if city_name:
            city_result = resolve_city(city_name, game_state)
            if not city_result:
                order.warnings.append(f"City '{city_name}' not found")
                return order
            order.city_id = city_result[0]
        else:
            # Use character's current location
            char = game_state.characters.get(char_result[0])
            if char:
                order.city_id = char.location_city_id

        return order

    # Pattern: "recruit <num> <type> [in <city>]" (implicit leader)
    match = re.search(r'^recruit\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        count = int(match.group(1))
        unit_type = match.group(2).strip().rstrip('s')
        city_name = match.group(3).strip() if match.group(3) else None

        # Validate unit type
        if unit_type not in [ut.value for ut in UnitType]:
            order.warnings.append(f"Invalid unit type '{unit_type}'")
            return order

        # Find player's leader
        leader = None
        for char in game_state.characters.values():
            if char.faction_id == player_id:
                leader = char
                break

        if not leader:
            order.warnings.append("No leader character found")
            return order

        order.actor_id = leader.id
        order.count = count
        order.unit_type = unit_type

        # Resolve city (or use leader's current location)
        if city_name:
            city_result = resolve_city(city_name, game_state)
            if not city_result:
                order.warnings.append(f"City '{city_name}' not found")
                return order
            order.city_id = city_result[0]
        else:
            order.city_id = leader.location_city_id

        return order

    return None


def parse_buy_ship_order(sentence: str, game_state: GameState, player_id: str) -> Optional[BuyShipOrder]:
    """
    Parse a ship purchase order.

    Patterns:
        - "have <char> buy <num> galley in <city>"
        - "have <char> buy <num> galley" (implicit: current location)
        - "buy <num> galley in <city>" (implicit leader)
    """
    order = BuyShipOrder(player_id=player_id, original_text=sentence)

    # Pattern: "have <name> buy <num> galley [in <city>]"
    match = re.search(r'have\s+(.+?)\s+buy\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        char_name = match.group(1).strip()
        count = int(match.group(2))
        ship_type = match.group(3).strip().rstrip('s')
        city_name = match.group(4).strip() if match.group(4) else None

        char_result = resolve_character(char_name, game_state, player_id)
        if not char_result:
            order.warnings.append(f"Character '{char_name}' not found")
            return order

        # Validate ship type
        if ship_type not in [st.value for st in ShipType]:
            order.warnings.append(f"Invalid ship type '{ship_type}'")
            return order

        order.actor_id = char_result[0]
        order.count = count
        order.ship_type = ship_type

        # Resolve city (or use character's current location)
        if city_name:
            city_result = resolve_city(city_name, game_state)
            if not city_result:
                order.warnings.append(f"City '{city_name}' not found")
                return order
            order.city_id = city_result[0]
        else:
            char = game_state.characters.get(char_result[0])
            if char:
                order.city_id = char.location_city_id

        return order

    # Pattern: "buy <num> galley [in <city>]" (implicit leader)
    match = re.search(r'^buy\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        count = int(match.group(1))
        ship_type = match.group(2).strip().rstrip('s')
        city_name = match.group(3).strip() if match.group(3) else None

        # Validate ship type
        if ship_type not in [st.value for st in ShipType]:
            order.warnings.append(f"Invalid ship type '{ship_type}'")
            return order

        # Find player's leader
        leader = None
        for char in game_state.characters.values():
            if char.faction_id == player_id:
                leader = char
                break

        if not leader:
            order.warnings.append("No leader character found")
            return order

        order.actor_id = leader.id
        order.count = count
        order.ship_type = ship_type

        # Resolve city (or use leader's current location)
        if city_name:
            city_result = resolve_city(city_name, game_state)
            if not city_result:
                order.warnings.append(f"City '{city_name}' not found")
                return order
            order.city_id = city_result[0]
        else:
            order.city_id = leader.location_city_id

        return order

    return None


def parse_attack_order(sentence: str, game_state: GameState, player_id: str) -> Optional[AttackOrder]:
    """
    Parse an attack order.

    Patterns:
        - "have <char> go to <city> and attack <target>"
        - "have <char> attack <target>" (implicit: current location)
        - "attack <target>" (implicit leader)
    """
    order = AttackOrder(player_id=player_id, original_text=sentence)

    # Pattern: "have <name> [go to <city> and] attack <target>"
    match = re.search(r'have\s+(.+?)\s+(?:go\s+to\s+(.+?)\s+and\s+)?attack\s+(.+)', sentence)
    if match:
        char_name = match.group(1).strip()
        city_name = match.group(2).strip() if match.group(2) else None
        target_name = match.group(3).strip()

        char_result = resolve_character(char_name, game_state, player_id)
        if not char_result:
            order.warnings.append(f"Character '{char_name}' not found")
            return order

        order.actor_id = char_result[0]
        order.target_name = target_name

        # Resolve target (could be character or faction name)
        target_result = resolve_character(target_name, game_state, None)
        if target_result:
            target_char = game_state.characters.get(target_result[0])
            if target_char:
                order.target_faction_id = target_char.faction_id

        # Resolve location
        if city_name:
            city_result = resolve_city(city_name, game_state)
            if city_result:
                order.location_city_id = city_result[0]
        else:
            char = game_state.characters.get(char_result[0])
            if char:
                order.location_city_id = char.location_city_id

        return order

    # Pattern: "attack <target>" (implicit leader)
    match = re.search(r'^attack\s+(.+)', sentence)
    if match:
        target_name = match.group(1).strip()

        # Find player's leader
        leader = None
        for char in game_state.characters.values():
            if char.faction_id == player_id:
                leader = char
                break

        if not leader:
            order.warnings.append("No leader character found")
            return order

        order.actor_id = leader.id
        order.target_name = target_name
        order.location_city_id = leader.location_city_id

        # Resolve target
        target_result = resolve_character(target_name, game_state, None)
        if target_result:
            target_char = game_state.characters.get(target_result[0])
            if target_char:
                order.target_faction_id = target_char.faction_id

        return order

    return None


def parse_teleport_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TeleportOrder]:
    """
    Parse a teleport order.

    Patterns:
        - "have <wizard> teleport <target> to <city>"
        - "teleport <target> to <city>" (implicit leader)
    """
    order = TeleportOrder(player_id=player_id, original_text=sentence)

    # Pattern: "have <wizard> teleport <target> to <city>"
    match = re.search(r'have\s+(.+?)\s+teleport\s+(.+?)\s+to\s+(.+)', sentence)
    if match:
        wizard_name = match.group(1).strip()
        target_name = match.group(2).strip()
        city_name = match.group(3).strip()

        wizard_result = resolve_character(wizard_name, game_state, player_id)
        if not wizard_result:
            order.warnings.append(f"Character '{wizard_name}' not found")
            return order

        target_result = resolve_character(target_name, game_state, player_id)
        if not target_result:
            order.warnings.append(f"Target '{target_name}' not found")
            return order

        city_result = resolve_city(city_name, game_state)
        if not city_result:
            order.warnings.append(f"City '{city_name}' not found")
            return order

        order.actor_id = wizard_result[0]
        order.target_character_id = target_result[0]
        order.destination_city_id = city_result[0]
        order.target_name = target_name
        return order

    # Pattern: "teleport <target> to <city>" (implicit leader)
    match = re.search(r'^teleport\s+(.+?)\s+to\s+(.+)', sentence)
    if match:
        target_name = match.group(1).strip()
        city_name = match.group(2).strip()

        # Find player's leader
        leader = None
        for char in game_state.characters.values():
            if char.faction_id == player_id:
                leader = char
                break

        if not leader:
            order.warnings.append("No leader character found")
            return order

        target_result = resolve_character(target_name, game_state, player_id)
        if not target_result:
            order.warnings.append(f"Target '{target_name}' not found")
            return order

        city_result = resolve_city(city_name, game_state)
        if not city_result:
            order.warnings.append(f"City '{city_name}' not found")
            return order

        order.actor_id = leader.id
        order.target_character_id = target_result[0]
        order.destination_city_id = city_result[0]
        order.target_name = target_name
        return order

    return None


# ============================================================================
# MAIN PARSER FUNCTION
# ============================================================================

def parse_orders(raw_text: str, game_state: GameState, player_id: str) -> list[Order]:
    """
    Parse raw order text into a list of Order objects.

    This is the main entry point for order parsing. It can be replaced
    with an LLM-based implementation that has the same signature.

    Args:
        raw_text: Raw order text from player
        game_state: Current game state (for entity resolution)
        player_id: ID of the player issuing orders

    Returns:
        List of Order objects (may contain warnings)
    """
    orders = []

    # Normalize and split into sentences
    normalized = normalize_text(raw_text)
    sentences = extract_sentences(normalized)

    for sentence in sentences:
        if not sentence:
            continue

        # Try each parser in sequence
        order = None

        # Try movement
        if any(word in sentence for word in ['go', 'move', 'travel']):
            order = parse_move_order(sentence, game_state, player_id)

        # Try recruit
        if not order and 'recruit' in sentence:
            order = parse_recruit_order(sentence, game_state, player_id)

        # Try buy ship
        if not order and 'buy' in sentence and 'galley' in sentence:
            order = parse_buy_ship_order(sentence, game_state, player_id)

        # Try attack
        if not order and 'attack' in sentence:
            order = parse_attack_order(sentence, game_state, player_id)

        # Try teleport
        if not order and 'teleport' in sentence:
            order = parse_teleport_order(sentence, game_state, player_id)

        if order:
            orders.append(order)
        else:
            # Create a generic order with warning
            generic_order = MoveOrder(player_id=player_id, original_text=sentence)
            generic_order.warnings.append(f"Could not parse order: '{sentence}'")
            orders.append(generic_order)

    return orders
