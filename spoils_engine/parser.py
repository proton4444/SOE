"""
Natural-language order parser (rule-based) - REFACTORED.

Parses English-like commands into structured Order objects.
This implementation uses regex and string matching, but the
interface is designed to be replaceable with an LLM-based parser.
"""

import re
from typing import Optional, Tuple, Type
from dataclasses import dataclass

from spoils_engine.models import GameState, UnitType, ShipType, Character
from spoils_engine.orders import (
    Order, MoveOrder, SailOrder, RecruitOrder, BuyShipOrder, AttackOrder, TeleportOrder, FlyOrder, HealOrder,
    SecureOrder, AllyOrder, EnemyOrder, NeutralOrder
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
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    return sentences


# ============================================================================
# ENTITY RESOLUTION
# ============================================================================

@dataclass
class ResolvedEntity:
    """Result of entity resolution."""
    entity_id: str
    entity_name: str
    found: bool = True


def resolve_character(name_text: str, game_state: GameState,
                     player_id: Optional[str] = None) -> ResolvedEntity:
    """
    Resolve a character name to ID.

    Args:
        name_text: Character name from order text
        game_state: Current game state
        player_id: Player issuing the order (None = search all)

    Returns:
        ResolvedEntity with id and name (found=False if not found)
    """
    # Try player's faction first if specified
    if player_id:
        char = game_state.get_character_by_name(name_text, faction_id=player_id)
        if char:
            return ResolvedEntity(char.id, char.name)

    # Try all factions
    char = game_state.get_character_by_name(name_text)
    if char:
        return ResolvedEntity(char.id, char.name)

    return ResolvedEntity("", name_text, found=False)


def resolve_city(name_text: str, game_state: GameState) -> ResolvedEntity:
    """
    Resolve a city name to ID.

    Args:
        name_text: City name from order text
        game_state: Current game state

    Returns:
        ResolvedEntity with id and name (found=False if not found)
    """
    city = game_state.world_map.get_city_by_name(name_text)
    if city:
        return ResolvedEntity(city.id, city.name)
    return ResolvedEntity("", name_text, found=False)


def get_player_leader(game_state: GameState, player_id: str) -> Optional[Character]:
    """Get the first character (leader) for a faction."""
    for char in game_state.characters.values():
        if char.faction_id == player_id:
            return char
    return None


# ============================================================================
# PARSER BASE CLASS
# ============================================================================

class OrderParserBase:
    """Base class for order parsers with common functionality."""

    def __init__(self, game_state: GameState, player_id: str, original_text: str):
        self.game_state = game_state
        self.player_id = player_id
        self.original_text = original_text

    def create_order(self, order_class: Type[Order]) -> Order:
        """Create an order instance with base attributes."""
        return order_class(player_id=self.player_id, original_text=self.original_text)

    def add_warning(self, order: Order, message: str) -> Order:
        """Add a warning to an order."""
        order.warnings.append(message)
        return order

    def resolve_actor(self, order: Order, actor_name: Optional[str]) -> bool:
        """
        Resolve actor to character ID, handling implicit leader.

        Returns:
            True if resolved successfully, False otherwise
        """
        if actor_name:
            # Explicit actor name
            resolved = resolve_character(actor_name, self.game_state, self.player_id)
            if not resolved.found:
                self.add_warning(order, f"Character '{actor_name}' not found")
                return False
            order.actor_id = resolved.entity_id
        else:
            # Implicit leader
            leader = get_player_leader(self.game_state, self.player_id)
            if not leader:
                self.add_warning(order, "No leader character found")
                return False
            order.actor_id = leader.id

        return True

    def resolve_location(self, order: Order, city_name: Optional[str],
                        use_actor_location: bool = True) -> bool:
        """
        Resolve location to city ID.

        Args:
            order: Order to update
            city_name: Optional city name from text
            use_actor_location: If True and city_name is None, use actor's location

        Returns:
            True if resolved successfully, False otherwise
        """
        if city_name:
            resolved = resolve_city(city_name, self.game_state)
            if not resolved.found:
                self.add_warning(order, f"City '{city_name}' not found")
                return False
            order.city_id = resolved.entity_id
        elif use_actor_location and hasattr(order, 'actor_id'):
            # Use actor's current location
            actor = self.game_state.characters.get(order.actor_id)
            if actor:
                order.city_id = actor.location_city_id
            else:
                return False

        return True


# ============================================================================
# ORDER PARSERS (REFACTORED)
# ============================================================================

def parse_move_order(sentence: str, game_state: GameState, player_id: str) -> Optional[MoveOrder]:
    """Parse a movement order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(MoveOrder)

    # Pattern: "have <name> go/move/travel to <city>"
    match = re.search(r'have\s+(.+?)\s+(?:go|move|travel)\s+to\s+(.+)', sentence)
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

    # Pattern: "go/move/travel to <city>" (implicit leader)
    match = re.search(r'^(?:go|move|travel)\s+to\s+(.+)', sentence)
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


def parse_recruit_order(sentence: str, game_state: GameState, player_id: str) -> Optional[RecruitOrder]:
    """Parse a recruitment order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(RecruitOrder)

    # Pattern: "have <name> recruit <num> <type> [in <city>]"
    match = re.search(r'have\s+(.+?)\s+recruit\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        actor_name = match.group(1).strip()
        count = int(match.group(2))
        unit_type = match.group(3).strip().rstrip('s')  # Remove plural
        city_name = match.group(4).strip() if match.group(4) else None

        if not parser.resolve_actor(order, actor_name):
            return order

        # Validate unit type
        if unit_type not in [ut.value for ut in UnitType]:
            parser.add_warning(order, f"Invalid unit type '{unit_type}'")
            return order

        order.count = count
        order.unit_type = unit_type

        if not parser.resolve_location(order, city_name):
            return order

        return order

    # Pattern: "recruit <num> <type> [in <city>]" (implicit leader)
    match = re.search(r'^recruit\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        count = int(match.group(1))
        unit_type = match.group(2).strip().rstrip('s')
        city_name = match.group(3).strip() if match.group(3) else None

        if not parser.resolve_actor(order, None):  # Use leader
            return order

        # Validate unit type
        if unit_type not in [ut.value for ut in UnitType]:
            parser.add_warning(order, f"Invalid unit type '{unit_type}'")
            return order

        order.count = count
        order.unit_type = unit_type

        if not parser.resolve_location(order, city_name):
            return order

        return order

    return None


def parse_buy_ship_order(sentence: str, game_state: GameState, player_id: str) -> Optional[BuyShipOrder]:
    """Parse a ship purchase order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(BuyShipOrder)

    # Pattern: "have <name> buy <num> <ship_type> [in <city>]"
    match = re.search(r'have\s+(.+?)\s+buy\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        actor_name = match.group(1).strip()
        count = int(match.group(2))
        ship_type = match.group(3).strip().rstrip('s')
        city_name = match.group(4).strip() if match.group(4) else None

        if not parser.resolve_actor(order, actor_name):
            return order

        # Validate ship type
        if ship_type not in [st.value for st in ShipType]:
            parser.add_warning(order, f"Invalid ship type '{ship_type}'")
            return order

        order.count = count
        order.ship_type = ship_type

        if not parser.resolve_location(order, city_name):
            return order

        return order

    # Pattern: "buy <num> <ship_type> [in <city>]" (implicit leader)
    match = re.search(r'^buy\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
    if match:
        count = int(match.group(1))
        ship_type = match.group(2).strip().rstrip('s')
        city_name = match.group(3).strip() if match.group(3) else None

        if not parser.resolve_actor(order, None):  # Use leader
            return order

        # Validate ship type
        if ship_type not in [st.value for st in ShipType]:
            parser.add_warning(order, f"Invalid ship type '{ship_type}'")
            return order

        order.count = count
        order.ship_type = ship_type

        if not parser.resolve_location(order, city_name):
            return order

        return order

    return None


def parse_attack_order(sentence: str, game_state: GameState, player_id: str) -> Optional[AttackOrder]:
    """Parse an attack order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AttackOrder)

    # Pattern: "have <name> [go to <city> and] attack <target>"
    match = re.search(r'have\s+(.+?)\s+(?:go\s+to\s+(.+?)\s+and\s+)?attack\s+(.+)', sentence)
    if match:
        actor_name = match.group(1).strip()
        city_name = match.group(2).strip() if match.group(2) else None
        target_name = match.group(3).strip()

        if not parser.resolve_actor(order, actor_name):
            return order

        order.target_name = target_name

        # Resolve target faction
        target_resolved = resolve_character(target_name, game_state, None)
        if target_resolved.found:
            target_char = game_state.characters.get(target_resolved.entity_id)
            if target_char:
                order.target_faction_id = target_char.faction_id

        # Resolve location
        if city_name:
            city_resolved = resolve_city(city_name, game_state)
            if city_resolved.found:
                order.location_city_id = city_resolved.entity_id
        else:
            actor = game_state.characters.get(order.actor_id)
            if actor:
                order.location_city_id = actor.location_city_id

        return order

    # Pattern: "attack <target>" (implicit leader)
    match = re.search(r'^attack\s+(.+)', sentence)
    if match:
        target_name = match.group(1).strip()

        if not parser.resolve_actor(order, None):
            return order

        order.target_name = target_name

        # Resolve target
        target_resolved = resolve_character(target_name, game_state, None)
        if target_resolved.found:
            target_char = game_state.characters.get(target_resolved.entity_id)
            if target_char:
                order.target_faction_id = target_char.faction_id

        # Use leader's location
        leader = get_player_leader(game_state, player_id)
        if leader:
            order.location_city_id = leader.location_city_id

        return order

    return None


def parse_teleport_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TeleportOrder]:
    """Parse a teleport order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TeleportOrder)

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
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(FlyOrder)

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


def parse_heal_order(sentence: str, game_state: GameState, player_id: str) -> Optional[HealOrder]:
    """Parse a heal/cure order (simplified version)."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(HealOrder)

    # Simplified pattern: "heal <character>" or "have <healer> heal <character>"
    # This is a basic implementation - full version would handle "to level X" and "by Y points"

    # Pattern: "have <healer> heal/cure <target>"
    match = re.search(r'have\s+(.+?)\s+(?:heal|cure)\s+(.+)', sentence)
    if match:
        healer_name = match.group(1).strip()
        target_name = match.group(2).strip()

        healer_resolved = resolve_character(healer_name, game_state, player_id)
        if not healer_resolved.found:
            parser.add_warning(order, f"Healer '{healer_name}' not found")
            return order

        target_resolved = resolve_character(target_name, game_state, player_id)
        if not target_resolved.found:
            parser.add_warning(order, f"Target '{target_name}' not found")
            return order

        order.actor_id = healer_resolved.entity_id
        order.target_character_ids = [target_resolved.entity_id]
        order.heal_to_levels = {target_resolved.entity_id: 100}  # Heal to full by default
        return order

    # Pattern: "heal/cure <target>" (implicit leader)
    match = re.search(r'^(?:heal|cure)\s+(.+)', sentence)
    if match:
        target_name = match.group(1).strip()

        if not parser.resolve_actor(order, None):
            return order

        target_resolved = resolve_character(target_name, game_state, player_id)
        if not target_resolved.found:
            parser.add_warning(order, f"Target '{target_name}' not found")
            return order

        order.target_character_ids = [target_resolved.entity_id]
        order.heal_to_levels = {target_resolved.entity_id: 100}  # Heal to full by default
        return order

    return None


def parse_secure_order(sentence: str, game_state: GameState, player_id: str) -> Optional[SecureOrder]:
    """Parse a secure order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(SecureOrder)

    # Pattern: "have <name> secure" or "secure" (location is implicit - actor's location)
    match = re.search(r'have\s+(.+?)\s+secure', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        # city_id will be resolved during execution (actor's current location)
        return order

    # Pattern: "secure" (implicit leader)
    if re.search(r'^secure', sentence):
        if not parser.resolve_actor(order, None):  # Use leader
            return order
        return order

    return None


def parse_ally_order(sentence: str, game_state: GameState, player_id: str) -> Optional[AllyOrder]:
    """Parse an ally order (simplified)."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AllyOrder)

    # Pattern: "ally <faction_name>"
    match = re.search(r'ally\s+(.+)', sentence)
    if match:
        faction_name = match.group(1).strip()
        # Try to resolve faction by name
        for faction in game_state.factions.values():
            if faction.name.lower() == faction_name.lower():
                order.target_faction_id = faction.id
                order.target_faction_name = faction_name
                return order

        # If not found, still create order with warning
        parser.add_warning(order, f"Faction '{faction_name}' not found")
        order.target_faction_name = faction_name
        return order

    return None


def parse_enemy_order(sentence: str, game_state: GameState, player_id: str) -> Optional[EnemyOrder]:
    """Parse an enemy order (simplified)."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(EnemyOrder)

    # Pattern: "enemy <faction_name>"
    match = re.search(r'enemy\s+(.+)', sentence)
    if match:
        faction_name = match.group(1).strip()
        # Try to resolve faction by name
        for faction in game_state.factions.values():
            if faction.name.lower() == faction_name.lower():
                order.target_faction_id = faction.id
                order.target_faction_name = faction_name
                return order

        parser.add_warning(order, f"Faction '{faction_name}' not found")
        order.target_faction_name = faction_name
        return order

    return None


def parse_neutral_order(sentence: str, game_state: GameState, player_id: str) -> Optional[NeutralOrder]:
    """Parse a neutral order (simplified)."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(NeutralOrder)

    # Pattern: "neutral <faction_name>"
    match = re.search(r'neutral\s+(.+)', sentence)
    if match:
        faction_name = match.group(1).strip()
        # Try to resolve faction by name
        for faction in game_state.factions.values():
            if faction.name.lower() == faction_name.lower():
                order.target_faction_id = faction.id
                order.target_faction_name = faction_name
                return order

        parser.add_warning(order, f"Faction '{faction_name}' not found")
        order.target_faction_name = faction_name
        return order

    return None


# ============================================================================
# MAIN PARSER FUNCTION
# ============================================================================

# Order detection keywords for optimization
ORDER_KEYWORDS = {
    'move': ['go', 'move', 'travel'],
    'sail': ['sail'],
    'recruit': ['recruit'],
    'buy': ['buy'],
    'attack': ['attack'],
    'teleport': ['teleport'],
    'fly': ['fly'],
    'heal': ['heal', 'cure'],
    'secure': ['secure'],
    'ally': ['ally'],
    'enemy': ['enemy'],
    'neutral': ['neutral']
}


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
    normalized = normalize_text(raw_text)
    sentences = extract_sentences(normalized)

    for sentence in sentences:
        if not sentence:
            continue

        order = None

        # Try each parser based on keywords (optimization)
        if any(kw in sentence for kw in ORDER_KEYWORDS['move']):
            order = parse_move_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['sail']):
            order = parse_sail_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['recruit']):
            order = parse_recruit_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['buy']):
            order = parse_buy_ship_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['attack']):
            order = parse_attack_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['teleport']):
            order = parse_teleport_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['fly']):
            order = parse_fly_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['heal']):
            order = parse_heal_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['secure']):
            order = parse_secure_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['ally']):
            order = parse_ally_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['enemy']):
            order = parse_enemy_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['neutral']):
            order = parse_neutral_order(sentence, game_state, player_id)

        if order:
            orders.append(order)
        else:
            # Unparseable order - create placeholder with warning
            generic_order = MoveOrder(player_id=player_id, original_text=sentence)
            generic_order.warnings.append(f"Could not parse order: '{sentence}'")
            orders.append(generic_order)

    return orders
