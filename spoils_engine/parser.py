"""
Natural-language order parser (rule-based) - REFACTORED.

Parses English-like commands into structured Order objects.
This implementation uses regex and string matching, but the
interface is designed to be replaceable with an LLM-based parser.
"""

import math
import re
from typing import Optional, Type
from dataclasses import dataclass

from spoils_engine.models import GameState, UnitType, ShipType, Character
from spoils_engine.orders import (
    Order, MoveOrder, SailOrder, RecruitOrder, BuyShipOrder, AttackOrder, TeleportOrder, FlyOrder, HealOrder,
    SecureOrder, FortifyOrder, UnfortifyOrder, AllyOrder, EnemyOrder, NeutralOrder, AssignOrder, NameOrder,
    PromoteOrder, TaxOrder, CaptureOrder, FreeOrder, StudyOrder, TeachOrder, SummonOrder, CollectOrder,
    BuildOrder, MineOrder, PrayOrder, BlessOrder, CurseOrder, ResurrectOrder, TradeOrder, AwaitOrder,
    RepeatOrder, ScryOrder, KillOrder, EnslaveOrder, InterrogateOrder, NoncomOrder, LurkOrder,
    GetOrder, TransferOrder, UnloadOrder, PayOrder, BorrowOrder, RepayOrder,
    HaltOrder, StopOrder, JoinOrder, SupportOrder,
)
from spoils_engine import config


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
                     player_id: Optional[str] = None,
                     enemy_ok: bool = False) -> ResolvedEntity:
    """
    Resolve a character name to ID.

    Args:
        name_text: Character name from order text
        game_state: Current game state
        player_id: Player issuing the order (None = search all factions)
        enemy_ok: If True, fall back to other factions when the name does not
            match one of the player's own characters. Use this for *targets*
            (attack, capture, freeing a prisoner) only.

    Returns:
        ResolvedEntity with id and name (found=False if not found)

    Note:
        With a player_id and enemy_ok=False the search is confined to that
        player's characters. Anything that becomes an order's `actor_id` must
        resolve this way -- otherwise naming an opponent's character in an
        order binds them as your actor and lets you act on their behalf.
    """
    if player_id:
        char = game_state.get_character_by_name(name_text, faction_id=player_id)
        if char:
            return ResolvedEntity(char.id, char.name)
        if not enemy_ok:
            return ResolvedEntity("", name_text, found=False)

    # Search all factions (targets, or no issuing player given)
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
    """
    Get the leader of a faction.

    The leader is marked by Character.is_leader. Saves written before that flag
    existed are migrated on load (see storage._migrate); the fallback here only
    covers game states built directly in code, such as in tests, and reproduces
    the old behaviour of taking whichever character iterates first.
    """
    fallback = None
    for char in game_state.characters.values():
        if char.faction_id != player_id:
            continue
        if char.is_leader:
            return char
        if fallback is None:
            fallback = char
    return fallback


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
            # Explicit actor name -- the HAVE form. rules.md makes that
            # character a group leader, so record that it was named.
            resolved = resolve_character(actor_name, self.game_state, self.player_id)
            if not resolved.found:
                self.add_warning(order, f"Character '{actor_name}' not found")
                return False
            order.actor_id = resolved.entity_id
            order.explicit_actor = True
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

    # Pattern: "have <name> go/move/travel/come to <city>".
    # rules.md: "COME -- see the GO command"; they are the same order.
    match = re.search(r'have\s+(.+?)\s+(?:go|move|travel|come)\s+to\s+(.+)', sentence)
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

    # Pattern: "go/move/travel/come to <city>" (implicit leader)
    match = re.search(r'^(?:go|move|travel|come)\s+to\s+(.+)', sentence)
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

    # Pattern: "have <name> recruit|hire <num> <type> [in <city>]"
    match = re.search(r'have\s+(.+?)\s+(?:recruit|hire)\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
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

    # Pattern: "recruit|hire <num> <type> [in <city>]" (implicit leader)
    match = re.search(r'^(?:recruit|hire)\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
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


def parse_pray_order(sentence: str, game_state: GameState, player_id: str) -> Optional[PrayOrder]:
    """Parse a pray order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(PrayOrder)

    match = re.search(r'have\s+(.+?)\s+pray(?:\s+for\s+(.*))?', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        intent = match.group(2)
        if intent:
            order.intent = intent.strip()
        return order

    if re.search(r'^pray', sentence):
        if not parser.resolve_actor(order, None):
            return order
        return order

    return None


def parse_bless_order(sentence: str, game_state: GameState, player_id: str) -> Optional[BlessOrder]:
    """Parse a bless order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(BlessOrder)

    match = re.search(r'have\s+(.+?)\s+bless\s+(.*)', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        city_resolved = resolve_city(match.group(2).strip(), game_state)
        if city_resolved.found:
            order.city_id = city_resolved.entity_id
        return order

    if re.search(r'^bless\s', sentence):
        if not parser.resolve_actor(order, None):
            return order
        city_resolved = resolve_city(sentence.replace('bless', '').strip(), game_state)
        if city_resolved.found:
            order.city_id = city_resolved.entity_id
        return order

    return None


def parse_curse_order(sentence: str, game_state: GameState, player_id: str) -> Optional[CurseOrder]:
    """Parse a curse order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(CurseOrder)

    match = re.search(r'have\s+(.+?)\s+curse\s+(.*)', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        city_resolved = resolve_city(match.group(2).strip(), game_state)
        if city_resolved.found:
            order.city_id = city_resolved.entity_id
        return order

    if re.search(r'^curse\s', sentence):
        if not parser.resolve_actor(order, None):
            return order
        city_resolved = resolve_city(sentence.replace('curse', '').strip(), game_state)
        if city_resolved.found:
            order.city_id = city_resolved.entity_id
        return order

    return None


def parse_resurrect_order(sentence: str, game_state: GameState, player_id: str) -> Optional[ResurrectOrder]:
    """Parse a resurrection order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(ResurrectOrder)

    match = re.search(r'resurrect\s+(.+)', sentence)
    if match:
        target_name = match.group(1).strip()
        # You may only resurrect your own dead, not an opponent's.
        target_resolved = resolve_character(target_name, game_state, player_id)
        order.target_name = target_name
        order.target_id = target_resolved.entity_id
        parser.resolve_actor(order, None)
        if not target_resolved.found:
            parser.add_warning(order, f"Target '{target_name}' not found")
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


def parse_fortify_order(sentence: str, game_state: GameState, player_id: str) -> Optional[FortifyOrder]:
    """Parse a fortify order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(FortifyOrder)

    match = re.search(r'have\s+(.+?)\s+fortify(?:\s+(.*?))?$', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        target_city_text = match.group(2)
        if target_city_text:
            city_resolved = resolve_city(target_city_text, game_state)
            if city_resolved.found:
                order.city_id = city_resolved.entity_id
        return order

    if re.search(r'^fortify', sentence):
        if not parser.resolve_actor(order, None):
            return order
        return order

    return None


def parse_unfortify_order(sentence: str, game_state: GameState, player_id: str) -> Optional[UnfortifyOrder]:
    """Parse an unfortify order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(UnfortifyOrder)

    match = re.search(r'have\s+(.+?)\s+unfortify(?:\s+(.*?))?$', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        target_city_text = match.group(2)
        if target_city_text:
            city_resolved = resolve_city(target_city_text, game_state)
            if city_resolved.found:
                order.city_id = city_resolved.entity_id
        return order

    if re.search(r'^unfortify', sentence):
        if not parser.resolve_actor(order, None):
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


def parse_assign_order(sentence: str, game_state: GameState, player_id: str) -> Optional[AssignOrder]:
    """Parse an assign/give order (simplified)."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AssignOrder)

    # Pattern: "have <donor> assign/give <quantity> <type> to <recipient>"
    # Example: "have Joe give 100 soldiers to Bill"
    match = re.search(r'have\s+(.+?)\s+(?:assign|give)\s+(\d+)\s+(soldier|sailor|worker|gold)s?\s+to\s+(.+)', sentence)
    if match:
        donor_name = match.group(1).strip()
        quantity = int(match.group(2))
        unit_or_gold = match.group(3).strip().lower()
        recipient_name = match.group(4).strip()

        donor_resolved = resolve_character(donor_name, game_state, player_id)
        if not donor_resolved.found:
            parser.add_warning(order, f"Donor '{donor_name}' not found")
            return order

        # GIVE may target another faction's character; the donor may not.
        recipient_resolved = resolve_character(recipient_name, game_state, player_id, enemy_ok=True)
        if not recipient_resolved.found:
            parser.add_warning(order, f"Recipient '{recipient_name}' not found")
            return order

        order.donor_id = donor_resolved.entity_id
        order.recipient_id = recipient_resolved.entity_id

        if unit_or_gold == 'gold':
            order.gold_amount = quantity
        elif unit_or_gold == 'soldier':
            order.unit_type = "SOLDIER"
            order.unit_count = quantity
        elif unit_or_gold == 'sailor':
            order.unit_type = "SAILOR"
            order.unit_count = quantity
        elif unit_or_gold == 'worker':
            order.unit_type = "WORKER"
            order.unit_count = quantity

        return order

    # Pattern: "assign/give <quantity> <type> to <recipient>" (implicit leader as donor)
    match = re.search(r'^(?:assign|give)\s+(\d+)\s+(soldier|sailor|worker|gold)s?\s+to\s+(.+)', sentence)
    if match:
        quantity = int(match.group(1))
        unit_or_gold = match.group(2).strip().lower()
        recipient_name = match.group(3).strip()

        leader = get_player_leader(game_state, player_id)
        if not leader:
            parser.add_warning(order, "No leader character found")
            return order
        order.donor_id = leader.id

        # GIVE may target another faction's character; the donor may not.
        recipient_resolved = resolve_character(recipient_name, game_state, player_id, enemy_ok=True)
        if not recipient_resolved.found:
            parser.add_warning(order, f"Recipient '{recipient_name}' not found")
            return order

        order.recipient_id = recipient_resolved.entity_id

        if unit_or_gold == 'gold':
            order.gold_amount = quantity
        elif unit_or_gold == 'soldier':
            order.unit_type = "SOLDIER"
            order.unit_count = quantity
        elif unit_or_gold == 'sailor':
            order.unit_type = "SAILOR"
            order.unit_count = quantity
        elif unit_or_gold == 'worker':
            order.unit_type = "WORKER"
            order.unit_count = quantity

        return order

    # Pattern: "assign <name> [and <name>] to <recipient>" -- named characters
    # rather than a count of unnamed units. rules.md: an assigned character
    # keeps whoever was already assigned to them, so a whole branch of the
    # group moves at once.
    match = re.search(r'^(?:have\s+(.+?)\s+)?(?:assign|give)\s+(.+?)\s+to\s+(.+)$', sentence)
    if match:
        donor_name, subject_text, recipient_name = match.groups()

        if donor_name:
            donor_resolved = resolve_character(donor_name.strip(), game_state, player_id)
            if not donor_resolved.found:
                parser.add_warning(order, f"Donor '{donor_name.strip()}' not found")
                return order
            order.donor_id = donor_resolved.entity_id
            order.explicit_actor = True
        else:
            leader = get_player_leader(game_state, player_id)
            if not leader:
                parser.add_warning(order, "No leader character found")
                return order
            order.donor_id = leader.id

        recipient_resolved = resolve_character(recipient_name.strip(), game_state, player_id)
        if not recipient_resolved.found:
            parser.add_warning(order, f"Recipient '{recipient_name.strip()}' not found")
            return order
        order.recipient_id = recipient_resolved.entity_id

        for name in [n.strip() for n in subject_text.split(' and ') if n.strip()]:
            subject_resolved = resolve_character(name, game_state, player_id)
            if not subject_resolved.found:
                parser.add_warning(order, f"Character '{name}' not found")
                return order
            order.character_ids.append(subject_resolved.entity_id)
            order.character_names.append(subject_resolved.entity_name)

        return order

    return None


def parse_name_order(sentence: str, game_state: GameState, player_id: str) -> Optional[NameOrder]:
    """
    Parse a NAME order.

    Examples:
        - "Name male soldier Joe Henley"
        - "name female sailor Donna Majesti"
        - "Have Jema Kendi recruit 1 sailor and name female sailor Donna Majesti"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(NameOrder)

    # Pattern: "name <gender> <unit_type> <name>"
    # Example: "name male soldier Joe Henley"
    match = re.search(r'name\s+(male|female)\s+(soldier|sailor|worker)\s+(.+)', sentence, re.IGNORECASE)
    if match:
        gender = match.group(1).strip().lower()
        unit_type = match.group(2).strip().lower()
        new_name = match.group(3).strip()

        # Remove punctuation at the end if any
        new_name = re.sub(r'[.,;!?]+$', '', new_name)

        # Validate name length (8-32 chars)
        if len(new_name) < 8:
            # Pad with random characters
            import random
            while len(new_name) < 8:
                new_name += chr(random.randint(97, 122))  # a-z
            parser.add_warning(order, f"Name too short, padded to: {new_name}")
        elif len(new_name) > 32:
            # Truncate
            new_name = new_name[:32]
            parser.add_warning(order, f"Name too long, truncated to: {new_name}")

        # Find the group leader (actor is implicit - the faction's leader at some location)
        # For simplicity, we'll use the player_id as actor and resolve in engine
        order.actor_id = player_id
        order.unit_type = unit_type.upper()
        order.gender = gender
        order.new_name = new_name

        return order

    return None


def parse_promote_order(sentence: str, game_state: GameState, player_id: str) -> Optional[PromoteOrder]:
    """
    Parse a PROMOTE order.

    Examples:
        - "Promote Jim Thomas to Major"
        - "Promote me to King"
        - "Promote Joe Smith and Ken Jones to Captain"
        - "Promote Jim Thomas to untitled"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(PromoteOrder)

    # Pattern: "promote <name(s)> to <title>"
    # Example: "promote Jim Thomas to Major"
    # Also handles: "promote Joe Smith and Ken Jones to Captain"
    match = re.search(r'promote\s+(.+?)\s+to\s+(.+)', sentence, re.IGNORECASE)
    if match:
        names_part = match.group(1).strip()
        new_title = match.group(2).strip()

        # Remove punctuation at the end
        new_title = re.sub(r'[.,;!?]+$', '', new_title)

        # Handle "untitled" as empty string
        if new_title.lower() == "untitled":
            new_title = ""

        # Split names by "and" to handle multiple promotions
        name_list = [n.strip() for n in re.split(r'\s+and\s+', names_part, flags=re.IGNORECASE)]

        for name in name_list:
            # Resolve character (can be "me" or a character name)
            if name.lower() == "me":
                # Find faction leader
                leader = None
                for char in game_state.characters.values():
                    if char.faction_id == player_id:
                        leader = char
                        break
                if leader:
                    order.character_ids.append(leader.id)
                    order.character_names.append(name)
                else:
                    parser.add_warning(order, "Could not find faction leader")
            else:
                char_resolved = resolve_character(name, game_state, player_id)
                if char_resolved.found:
                    order.character_ids.append(char_resolved.entity_id)
                    order.character_names.append(name)
                else:
                    parser.add_warning(order, f"Character '{name}' not found")

        order.new_title = new_title
        return order

    return None


def parse_tax_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TaxOrder]:
    """
    Parse a TAX order.

    Examples:
        - "tax"
        - "tax for 2 weeks"
        - "have Captain Jones tax for 14 days"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TaxOrder)

    # Pattern: "tax for <number> <unit>"
    # Example: "tax for 2 weeks"
    duration_days = 7  # Default 1 week

    # Check for duration specification
    duration_match = re.search(r'tax(?:\s+for\s+(\d+)\s+(day|days|week|weeks|hour|hours))?', sentence, re.IGNORECASE)
    if duration_match and duration_match.group(1):
        amount = int(duration_match.group(1))
        unit = duration_match.group(2).lower()

        if 'week' in unit:
            duration_days = amount * 7
        elif 'day' in unit:
            duration_days = amount
        elif 'hour' in unit:
            # 12 daylight hours per day
            duration_days = max(1, amount // 12)

    # Pattern: "have <actor> tax..."
    # Example: "have Captain Jones tax for 2 weeks"
    match = re.search(r'have\s+(.+?)\s+tax', sentence)
    if match:
        actor_name = match.group(1).strip()
        actor_resolved = resolve_character(actor_name, game_state, player_id)
        if not actor_resolved.found:
            parser.add_warning(order, f"Actor '{actor_name}' not found")
            return order
        order.actor_id = actor_resolved.entity_id
        order.duration_days = duration_days
        return order

    # Pattern: "tax" (implicit actor - use faction leader)
    if 'tax' in sentence:
        # Use faction leader as implicit actor
        if not parser.resolve_actor(order, None):
            return order
        order.duration_days = duration_days
        return order

    return None


def parse_capture_order(sentence: str, game_state: GameState, player_id: str) -> Optional[CaptureOrder]:
    """
    Parse a CAPTURE order.

    Examples:
        - "Capture Jamu Penda"
        - "Have Joe Flint capture Mary Tarrington and Billy The Kid"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(CaptureOrder)

    # Pattern: "have <actor> capture <target(s)>"
    # Example: "have Joe Flint capture Mary Tarrington"
    match = re.search(r'have\s+(.+?)\s+capture\s+(.+)', sentence, re.IGNORECASE)
    if match:
        actor_name = match.group(1).strip()
        targets_part = match.group(2).strip()

        actor_resolved = resolve_character(actor_name, game_state, player_id)
        if not actor_resolved.found:
            parser.add_warning(order, f"Actor '{actor_name}' not found")
            return order

        order.actor_id = actor_resolved.entity_id

        # Split targets by "and"
        target_list = [n.strip() for n in re.split(r'\s+and\s+', targets_part, flags=re.IGNORECASE)]
        for target_name in target_list:
            # Remove trailing punctuation
            target_name = re.sub(r'[.,;!?]+$', '', target_name)
            target_resolved = resolve_character(target_name, game_state, player_id, enemy_ok=True)
            if target_resolved.found:
                order.target_ids.append(target_resolved.entity_id)
                order.target_names.append(target_name)
            else:
                parser.add_warning(order, f"Target '{target_name}' not found")

        return order

    # Pattern: "capture <target(s)>" (implicit actor - use faction leader)
    match = re.search(r'capture\s+(.+)', sentence, re.IGNORECASE)
    if match:
        targets_part = match.group(1).strip()

        if not parser.resolve_actor(order, None):
            return order

        # Split targets by "and"
        target_list = [n.strip() for n in re.split(r'\s+and\s+', targets_part, flags=re.IGNORECASE)]
        for target_name in target_list:
            # Remove trailing punctuation
            target_name = re.sub(r'[.,;!?]+$', '', target_name)
            target_resolved = resolve_character(target_name, game_state, player_id, enemy_ok=True)
            if target_resolved.found:
                order.target_ids.append(target_resolved.entity_id)
                order.target_names.append(target_name)
            else:
                parser.add_warning(order, f"Target '{target_name}' not found")

        return order

    return None


def parse_free_order(sentence: str, game_state: GameState, player_id: str) -> Optional[FreeOrder]:
    """
    Parse a FREE/RELEASE/DISCARD/DISMISS order.

    Examples:
        - "Free Wizard Yemishoka"
        - "Have Joe Flint free 5 slaves"
        - "Release all prisoners"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(FreeOrder)

    # Pattern: "have <actor> free/release <prisoner(s)>"
    # Example: "have Joe Flint free Mary"
    match = re.search(r'have\s+(.+?)\s+(?:free|release|discard|dismiss)\s+(.+)', sentence, re.IGNORECASE)
    if match:
        actor_name = match.group(1).strip()
        prisoners_part = match.group(2).strip()

        actor_resolved = resolve_character(actor_name, game_state, player_id)
        if not actor_resolved.found:
            parser.add_warning(order, f"Actor '{actor_name}' not found")
            return order

        order.actor_id = actor_resolved.entity_id

        # Split prisoners by "and"
        prisoner_list = [n.strip() for n in re.split(r'\s+and\s+', prisoners_part, flags=re.IGNORECASE)]
        for prisoner_name in prisoner_list:
            # Remove trailing punctuation
            prisoner_name = re.sub(r'[.,;!?]+$', '', prisoner_name)
            # Prisoners keep their original faction, so they must be looked up
            # across factions; the engine verifies the actor is their captor.
            prisoner_resolved = resolve_character(prisoner_name, game_state, player_id, enemy_ok=True)
            if prisoner_resolved.found:
                order.prisoner_ids.append(prisoner_resolved.entity_id)
                order.prisoner_names.append(prisoner_name)
            else:
                parser.add_warning(order, f"Prisoner '{prisoner_name}' not found")

        return order

    # Pattern: "free/release <prisoner(s)>" (implicit actor - use faction leader)
    match = re.search(r'(?:free|release|discard|dismiss)\s+(.+)', sentence, re.IGNORECASE)
    if match:
        prisoners_part = match.group(1).strip()

        if not parser.resolve_actor(order, None):
            return order

        # Split prisoners by "and"
        prisoner_list = [n.strip() for n in re.split(r'\s+and\s+', prisoners_part, flags=re.IGNORECASE)]
        for prisoner_name in prisoner_list:
            # Remove trailing punctuation
            prisoner_name = re.sub(r'[.,;!?]+$', '', prisoner_name)
            # Prisoners keep their original faction, so they must be looked up
            # across factions; the engine verifies the actor is their captor.
            prisoner_resolved = resolve_character(prisoner_name, game_state, player_id, enemy_ok=True)
            if prisoner_resolved.found:
                order.prisoner_ids.append(prisoner_resolved.entity_id)
                order.prisoner_names.append(prisoner_name)
            else:
                parser.add_warning(order, f"Prisoner '{prisoner_name}' not found")

        return order

    return None


def parse_study_order(sentence: str, game_state: GameState, player_id: str) -> Optional[StudyOrder]:
    """
    Parse a STUDY order.

    Examples:
        - "Study magic"
        - "Study combat for 3 weeks"
        - "Have Joe study sailing to level 20"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(StudyOrder)

    # Pattern: "have <actor> study <skill> [for <duration>] [to <level>]"
    match = re.search(r'have\s+(.+?)\s+study\s+(combat|magic|religion|sailing)(?:\s+for\s+(\d+))?(?:\s+to\s+(?:level\s+)?(\d+))?', sentence, re.IGNORECASE)
    if match:
        actor_name = match.group(1).strip()
        skill = match.group(2).strip().lower()
        duration = int(match.group(3)) if match.group(3) else 1
        target_level = int(match.group(4)) if match.group(4) else 0

        actor_resolved = resolve_character(actor_name, game_state, player_id)
        if not actor_resolved.found:
            parser.add_warning(order, f"Actor '{actor_name}' not found")
            return order

        order.actor_id = actor_resolved.entity_id
        order.skill_name = skill
        order.duration_weeks = duration
        order.target_level = target_level
        return order

    # Pattern: "study <skill> [for <duration>] [to <level>]" (implicit actor)
    match = re.search(r'study\s+(combat|magic|religion|sailing)(?:\s+for\s+(\d+))?(?:\s+to\s+(?:level\s+)?(\d+))?', sentence, re.IGNORECASE)
    if match:
        skill = match.group(1).strip().lower()
        duration = int(match.group(2)) if match.group(2) else 1
        target_level = int(match.group(3)) if match.group(3) else 0

        if not parser.resolve_actor(order, None):
            return order

        order.skill_name = skill
        order.duration_weeks = duration
        order.target_level = target_level
        return order

    return None


def parse_teach_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TeachOrder]:
    """
    Parse a TEACH order.

    Examples:
        - "Have Joe teach combat to Mary"
        - "Teach Mike magic to level 10"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TeachOrder)

    # Pattern: "have <teacher> teach <skill> to <student> [for <duration>] [to level <level>]"
    match = re.search(r'have\s+(.+?)\s+teach\s+(combat|magic|religion|sailing)\s+to\s+(.+?)(?:\s+for\s+(\d+))?(?:\s+to\s+(?:level\s+)?(\d+))?$', sentence, re.IGNORECASE)
    if match:
        teacher_name = match.group(1).strip()
        skill = match.group(2).strip().lower()
        student_name = match.group(3).strip()
        duration = int(match.group(4)) if match.group(4) else 1
        target_level = int(match.group(5)) if match.group(5) else 0

        # Remove punctuation from student name
        student_name = re.sub(r'[.,;!?]+$', '', student_name)

        teacher_resolved = resolve_character(teacher_name, game_state, player_id)
        if not teacher_resolved.found:
            parser.add_warning(order, f"Teacher '{teacher_name}' not found")
            return order

        student_resolved = resolve_character(student_name, game_state, player_id)
        if not student_resolved.found:
            parser.add_warning(order, f"Student '{student_name}' not found")
            return order

        order.teacher_id = teacher_resolved.entity_id
        order.student_id = student_resolved.entity_id
        order.skill_name = skill
        order.duration_weeks = duration
        order.target_level = target_level
        return order

    return None


def parse_summon_order(sentence: str, game_state: GameState, player_id: str) -> Optional[SummonOrder]:
    """
    Parse a SUMMON order.

    Examples:
        - "Summon 2 dragons"
        - "Have Merlinus summon 1 demon and 2 griffins"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(SummonOrder)

    # Creature types mapping
    creature_types = ['skeleton', 'zombie', 'harpy', 'minotaur', 'griffin', 'chimera', 'dragon', 'demon']

    # Pattern: "have <summoner> summon <creatures>"
    match = re.search(r'have\s+(.+?)\s+summon\s+(.+)', sentence, re.IGNORECASE)
    if match:
        summoner_name = match.group(1).strip()
        creatures_part = match.group(2).strip()

        summoner_resolved = resolve_character(summoner_name, game_state, player_id)
        if not summoner_resolved.found:
            parser.add_warning(order, f"Summoner '{summoner_name}' not found")
            return order

        order.summoner_id = summoner_resolved.entity_id

        # Parse creature list: "2 dragons and 1 griffin"
        # Split by "and"
        creature_phrases = [p.strip() for p in re.split(r'\s+and\s+', creatures_part, flags=re.IGNORECASE)]

        for phrase in creature_phrases:
            # Pattern: "<number> <creature_type>"
            creature_match = re.search(r'(\d+)\s+(' + '|'.join(creature_types) + r')s?', phrase, re.IGNORECASE)
            if creature_match:
                count = int(creature_match.group(1))
                creature_type = creature_match.group(2).strip().lower()
                order.creature_counts[creature_type] = order.creature_counts.get(creature_type, 0) + count

        if not order.creature_counts:
            parser.add_warning(order, "No valid creatures specified")

        return order

    # Pattern: "summon <creatures>" (implicit summoner - use faction leader)
    match = re.search(r'summon\s+(.+)', sentence, re.IGNORECASE)
    if match:
        creatures_part = match.group(1).strip()

        if not parser.resolve_actor(order, None):
            return order

        order.summoner_id = order.actor_id  # Use the resolved actor as summoner

        # Parse creature list
        creature_phrases = [p.strip() for p in re.split(r'\s+and\s+', creatures_part, flags=re.IGNORECASE)]

        for phrase in creature_phrases:
            creature_match = re.search(r'(\d+)\s+(' + '|'.join(creature_types) + r')s?', phrase, re.IGNORECASE)
            if creature_match:
                count = int(creature_match.group(1))
                creature_type = creature_match.group(2).strip().lower()
                order.creature_counts[creature_type] = order.creature_counts.get(creature_type, 0) + count

        if not order.creature_counts:
            parser.add_warning(order, "No valid creatures specified")

        return order

    return None


def parse_collect_order(sentence: str, game_state: GameState, player_id: str) -> Optional[CollectOrder]:
    """
    Parse a COLLECT/GATHER order.

    Examples:
        - "Gather stone"
        - "Collect wood for 5 days"
        - "Have Engineer collect 40 wood"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(CollectOrder)

    # Pattern: "have <actor> collect/gather <resource> [for <duration>]"
    match = re.search(r'have\s+(.+?)\s+(?:collect|gather)\s+(wood|stone)(?:\s+for\s+(\d+))?', sentence, re.IGNORECASE)
    if match:
        actor_name = match.group(1).strip()
        resource = match.group(2).strip().lower()
        duration = int(match.group(3)) if match.group(3) else 7

        actor_resolved = resolve_character(actor_name, game_state, player_id)
        if not actor_resolved.found:
            parser.add_warning(order, f"Actor '{actor_name}' not found")
            return order

        order.actor_id = actor_resolved.entity_id
        order.resource_type = resource
        order.duration_days = duration
        return order

    # Pattern: "collect/gather <resource> [for <duration>]" (implicit actor)
    match = re.search(r'(?:collect|gather)\s+(wood|stone)(?:\s+for\s+(\d+))?', sentence, re.IGNORECASE)
    if match:
        resource = match.group(1).strip().lower()
        duration = int(match.group(2)) if match.group(2) else 7

        if not parser.resolve_actor(order, None):
            return order

        order.resource_type = resource
        order.duration_days = duration
        return order

    return None


def parse_build_order(sentence: str, game_state: GameState, player_id: str) -> Optional[BuildOrder]:
    """
    Parse a BUILD/CONSTRUCT/MAKE order.

    Examples:
        - "Build 1 galley"
        - "Have Engineer build 2 galleys"
        - "Construct 5 catapults"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(BuildOrder)

    # Pattern: "have <actor> build/construct/make <count> <item>"
    match = re.search(r'have\s+(.+?)\s+(?:build|construct|make)\s+(\d+)\s+(galley|galleys|catapult|catapults|weapon|weapons|armor|armors)', sentence, re.IGNORECASE)
    if match:
        actor_name = match.group(1).strip()
        count = int(match.group(2))
        item = match.group(3).strip().lower()

        # Normalize plural forms
        if item.endswith('s'):
            item = item[:-1]

        actor_resolved = resolve_character(actor_name, game_state, player_id)
        if not actor_resolved.found:
            parser.add_warning(order, f"Actor '{actor_name}' not found")
            return order

        order.actor_id = actor_resolved.entity_id
        order.item_type = item
        order.count = count
        return order

    # Pattern: "build/construct/make <count> <item>" (implicit actor)
    match = re.search(r'(?:build|construct|make)\s+(\d+)\s+(galley|galleys|catapult|catapults|weapon|weapons|armor|armors)', sentence, re.IGNORECASE)
    if match:
        count = int(match.group(1))
        item = match.group(2).strip().lower()

        # Normalize plural forms
        if item.endswith('s'):
            item = item[:-1]

        if not parser.resolve_actor(order, None):
            return order

        order.item_type = item
        order.count = count
        return order

    return None


def parse_mine_order(sentence: str, game_state: GameState, player_id: str) -> Optional[MineOrder]:
    """
    Parse a MINE order.

    Examples:
        - "Mine iron"
        - "Mine gold for 10 days"
        - "Have Miner mine silver"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(MineOrder)

    # Pattern: "have <actor> mine <resource> [for <duration>]"
    match = re.search(r'have\s+(.+?)\s+mine\s+(iron|gold|silver|copper|gems)(?:\s+for\s+(\d+))?', sentence, re.IGNORECASE)
    if match:
        actor_name = match.group(1).strip()
        resource = match.group(2).strip().lower()
        duration = int(match.group(3)) if match.group(3) else 7

        actor_resolved = resolve_character(actor_name, game_state, player_id)
        if not actor_resolved.found:
            parser.add_warning(order, f"Actor '{actor_name}' not found")
            return order

        order.actor_id = actor_resolved.entity_id
        order.resource_type = resource
        order.duration_days = duration
        return order

    # Pattern: "mine <resource> [for <duration>]" (implicit actor)
    match = re.search(r'mine\s+(iron|gold|silver|copper|gems)(?:\s+for\s+(\d+))?', sentence, re.IGNORECASE)
    if match:
        resource = match.group(1).strip().lower()
        duration = int(match.group(2)) if match.group(2) else 7

        if not parser.resolve_actor(order, None):
            return order

        order.resource_type = resource
        order.duration_days = duration
        return order

    return None


def parse_trade_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TradeOrder]:
    """Parse buy/sell trade orders."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TradeOrder)

    match = re.search(r'have\s+(.+?)\s+(buy|sell)\s+(\d+)\s+([a-z]+)', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        order.action = match.group(2)
        order.amount = int(match.group(3))
        order.resource_type = match.group(4)
        return order

    match = re.search(r'^(buy|sell)\s+(\d+)\s+([a-z]+)', sentence)
    if match:
        order.action = match.group(1)
        order.amount = int(match.group(2))
        order.resource_type = match.group(3)
        parser.resolve_actor(order, None)
        return order

    return None


# rules.md allows minutes, hours, days, weeks and months, forbids mixing units,
# and fixes a month at exactly 30 days.
TIME_UNIT_DAYS = {
    'minute': 1 / (24 * 60),
    'hour': 1 / 24,
    'day': 1.0,
    'week': 7.0,
    'month': float(config.DAYS_PER_MONTH),
}


def parse_duration_days(sentence: str) -> Optional[int]:
    """
    Read a "<number> <unit>" duration out of a sentence, in whole days.

    Rounded up, because the queue cannot hold work for less than a turn. The
    rules' one-hour minimum therefore lands on a single day here.
    """
    match = re.search(
        r'(\d+)\s+(minute|hour|day|week|month)s?\b', sentence
    )
    if not match:
        return None

    days = int(match.group(1)) * TIME_UNIT_DAYS[match.group(2)]
    return max(1, math.ceil(days))


def parse_await_order(sentence: str, game_state: GameState, player_id: str) -> Optional[AwaitOrder]:
    """
    Parse WAIT FOR / AWAIT / WAIT UNTIL.

    Three forms are understood: a timed wait ("wait for 3 days"), a wait for a
    person ("have Mary await Joe Flint"), and a wait to an absolute turn ("wait
    until turn 12"). `rules.md` writes the last of these as a calendar date,
    which the alpha has no clock for, so the turn number stands in for it.

    A wait for a person may also carry a duration, which then acts as the
    deadline the character gives up on.
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AwaitOrder)

    if not re.search(r'\b(?:await|wait)\b', sentence):
        return None

    # "have <name> wait ..." -- otherwise the wait belongs to the leader.
    actor_match = re.search(r'have\s+(.+?)\s+(?:await|wait)\b', sentence)
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    remainder = re.sub(r'^.*?\b(?:await|wait)\b', '', sentence).strip()
    remainder = re.sub(r'^(?:for|until)\s+', '', remainder).strip()

    # "wait until turn 12" -- convert the absolute turn into a duration.
    turn_match = re.search(r'^turn\s+(\d+)', remainder)
    if turn_match:
        turns = max(0, int(turn_match.group(1)) - game_state.turn_number)
        order.duration_days = turns * config.DAYS_PER_TURN
        return order

    duration = parse_duration_days(remainder)
    if duration is not None:
        order.duration_days = duration

    # Whatever is left that is not a duration is a person to wait for.
    target_text = re.sub(r'\d+\s+(?:minute|hour|day|week|month)s?\b', '', remainder)
    target_text = re.sub(r'\b(?:and|then|until|for|exactly)\b', ' ', target_text)
    target_text = ' '.join(target_text.split())

    if target_text:
        resolved = resolve_character(target_text, game_state, player_id, enemy_ok=True)
        if not resolved.found:
            return parser.add_warning(order, f"Character '{target_text}' not found")
        order.target_id = resolved.entity_id
        if duration is None:
            # No deadline given: hold for a good while rather than forever, so
            # a target who never shows up does not strand the queue.
            order.duration_days = config.AWAIT_DEFAULT_DEADLINE_DAYS
        return order

    if duration is None:
        return parser.add_warning(order, "Wait for how long, or for whom?")

    return order


def parse_repeat_order(sentence: str, game_state: GameState, player_id: str) -> Optional[RepeatOrder]:
    """
    Parse a bare REPEAT order.

    The usual spelling is the adverb `repeatedly`, which `parse_orders` lifts
    off the sentence it governs. This handles the explicit verb form.
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(RepeatOrder)

    if not re.search(r'\brepeat\b', sentence):
        return None

    actor_match = re.search(r'have\s+(.+?)\s+repeat\b', sentence)
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    match = re.search(r'repeat\s+(?:.*?\s+)?(\d+)', sentence)
    order.times = int(match.group(1)) if match else 0
    return order


def parse_join_order(sentence: str, game_state: GameState, player_id: str) -> Optional[JoinOrder]:
    """
    Parse JOIN -- become part of another character's group.

    "Have Joe Flint join General Bill Hayden" or the bare "join Mike Holmes",
    which the player's own leader carries out.
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(JoinOrder)

    match = re.search(r'(?:have\s+(.+?)\s+)?join\s+(.+)$', sentence)
    if not match:
        return None

    actor_name, target_name = match.group(1), match.group(2).strip()
    target_name = re.sub(r'^(?:and|then)\s+', '', target_name).strip()

    if not parser.resolve_actor(order, actor_name.strip() if actor_name else None):
        return order

    resolved = resolve_character(target_name, game_state, player_id)
    if not resolved.found:
        return parser.add_warning(order, f"Character '{target_name}' not found")

    order.target_id = resolved.entity_id
    order.target_name = resolved.entity_name
    return order


def parse_support_order(sentence: str, game_state: GameState, player_id: str) -> Optional[SupportOrder]:
    """
    Parse SUPPORT -- fight alongside somebody when they attack.

    The target is usually another player's character, so the name is resolved
    across factions. A `for <duration>` phrase bounds the agreement; without
    one it stands until a HALT or STOP.
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(SupportOrder)

    match = re.search(r'(?:have\s+(.+?)\s+)?support\s+(.+)$', sentence)
    if not match:
        return None

    actor_name, remainder = match.group(1), match.group(2).strip()

    if not parser.resolve_actor(order, actor_name.strip() if actor_name else None):
        return order

    duration = parse_duration_days(remainder)
    if duration is not None:
        order.duration_days = duration

    target_text = re.sub(r'\bfor\s+\d+\s+(?:minute|hour|day|week|month)s?\b', ' ', remainder)
    target_text = re.sub(r'\b(?:and|then)\b.*$', ' ', target_text)
    target_text = ' '.join(target_text.split())

    if not target_text:
        return parser.add_warning(order, "Support whom?")

    for name in [n.strip() for n in target_text.split(' and ') if n.strip()]:
        resolved = resolve_character(name, game_state, player_id, enemy_ok=True)
        if not resolved.found:
            return parser.add_warning(order, f"Character '{name}' not found")
        order.target_ids.append(resolved.entity_id)
        order.target_names.append(resolved.entity_name)

    return order


def parse_halt_order(sentence: str, game_state: GameState, player_id: str):
    """
    Parse HALT and STOP.

    HALT is the unplanned stop -- it takes effect the moment it is processed.
    STOP is the planned one and waits its turn in the queue. The adverb
    `immediately` additionally abandons a wait that is already running.
    """
    verb_match = re.search(r'\b(halt|stop)\b', sentence)
    if not verb_match:
        return None

    verb = verb_match.group(1)
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(HaltOrder if verb == 'halt' else StopOrder)

    # Both "have Joe halt" and the rules' "immediately stop Joe Flint" name the
    # character whose orders are being dropped.
    actor_match = (
        re.search(r'have\s+(.+?)\s+(?:immediately\s+)?(?:halt|stop)\b', sentence)
        or re.search(r'(?:halt|stop)\s+(.+)$', sentence)
    )
    actor_name = actor_match.group(1).strip() if actor_match else None
    actor_name = re.sub(r'^(?:and|then)\s+', '', actor_name).strip() if actor_name else None

    if not parser.resolve_actor(order, actor_name or None):
        return order

    order.immediate = bool(re.search(r'\bimmediately\b', sentence))
    return order


def parse_scry_order(sentence: str, game_state: GameState, player_id: str) -> Optional[ScryOrder]:
    """Parse a scry order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(ScryOrder)

    match = re.search(r'have\s+(.+?)\s+scry\s+(.*)', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        city_resolved = resolve_city(match.group(2).strip(), game_state)
        if city_resolved.found:
            order.city_id = city_resolved.entity_id
        return order

    match = re.search(r'^scry\s+(.*)', sentence)
    if match:
        parser.resolve_actor(order, None)
        city_resolved = resolve_city(match.group(1).strip(), game_state)
        if city_resolved.found:
            order.city_id = city_resolved.entity_id
        return order

    return None


def _parse_prisoner_list_order(sentence: str, game_state: GameState, player_id: str,
                               order_cls, verbs: str):
    """Shared parse for FREE-like prisoner-target orders (kill, enslave, interrogate)."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(order_cls)

    match = re.search(
        rf'have\s+(.+?)\s+(?:{verbs})\s+(.+?)(?:\s+for\s+(\d+))?\s*$',
        sentence,
    )
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        targets_part = match.group(2).strip()
        if match.group(3) and hasattr(order, 'duration_days'):
            order.duration_days = int(match.group(3))
    else:
        match = re.search(rf'^(?:{verbs})\s+(.+?)(?:\s+for\s+(\d+))?\s*$', sentence)
        if not match:
            return None
        if not parser.resolve_actor(order, None):
            return order
        targets_part = match.group(1).strip()
        if match.group(2) and hasattr(order, 'duration_days'):
            order.duration_days = int(match.group(2))

    for name in re.split(r'\s+and\s+', targets_part, flags=re.IGNORECASE):
        name = re.sub(r'[.,;!?]+$', '', name.strip())
        if not name:
            continue
        resolved = resolve_character(name, game_state, player_id, enemy_ok=True)
        ids_attr = 'prisoner_ids' if hasattr(order, 'prisoner_ids') else 'target_ids'
        names_attr = 'prisoner_names' if hasattr(order, 'prisoner_names') else 'target_names'
        if resolved.found:
            getattr(order, ids_attr).append(resolved.entity_id)
            getattr(order, names_attr).append(name)
        else:
            parser.add_warning(order, f"Target '{name}' not found")
    return order


def parse_kill_order(sentence: str, game_state: GameState, player_id: str) -> Optional[KillOrder]:
    return _parse_prisoner_list_order(sentence, game_state, player_id, KillOrder, r'kill|execute')


def parse_enslave_order(sentence: str, game_state: GameState, player_id: str) -> Optional[EnslaveOrder]:
    return _parse_prisoner_list_order(sentence, game_state, player_id, EnslaveOrder, r'enslave')


def parse_interrogate_order(sentence: str, game_state: GameState, player_id: str) -> Optional[InterrogateOrder]:
    return _parse_prisoner_list_order(
        sentence, game_state, player_id, InterrogateOrder, r'interrogate'
    )


def parse_noncom_order(sentence: str, game_state: GameState, player_id: str) -> Optional[NoncomOrder]:
    """Parse NONCOM / COMBATANT status orders."""
    parser = OrderParserBase(game_state, player_id, sentence)
    set_noncom = bool(re.search(r'\bnoncom\b', sentence))
    if not set_noncom and not re.search(r'\bcombatant\b', sentence):
        return None
    order = parser.create_order(NoncomOrder)
    order.set_noncom = set_noncom

    match = re.search(r'(?:noncom|combatant)\s+(.+)', sentence)
    if not match:
        parser.add_warning(order, "No characters named")
        return order

    for name in re.split(r'\s+and\s+', match.group(1).strip(), flags=re.IGNORECASE):
        name = re.sub(r'[.,;!?]+$', '', name.strip())
        if not name:
            continue
        resolved = resolve_character(name, game_state, player_id)
        if resolved.found:
            order.character_ids.append(resolved.entity_id)
            order.character_names.append(name)
        else:
            parser.add_warning(order, f"Character '{name}' not found")
    return order


def parse_lurk_order(sentence: str, game_state: GameState, player_id: str) -> Optional[LurkOrder]:
    parser = OrderParserBase(game_state, player_id, sentence)
    set_lurking = not bool(re.search(r'\bunlurk\b', sentence))
    if set_lurking and not re.search(r'\blurk\b', sentence):
        return None
    order = parser.create_order(LurkOrder)
    order.set_lurking = set_lurking

    match = re.search(r'have\s+(.+?)\s+(?:un)?lurk\b', sentence)
    if match:
        parser.resolve_actor(order, match.group(1).strip())
        return order

    match = re.search(r'^(?:un)?lurk\b(?:\s+(.+))?', sentence)
    if match and match.group(1):
        # "lurk major johnson" style — named actor
        parser.resolve_actor(order, match.group(1).strip())
        return order

    parser.resolve_actor(order, None)
    return order


def parse_get_order(sentence: str, game_state: GameState, player_id: str) -> Optional[GetOrder]:
    """Parse GET/TAKE/OBTAIN — inverse of GIVE."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(GetOrder)

    # have X take N gold|units from Y
    match = re.search(
        r'have\s+(.+?)\s+(?:get|take|obtain)\s+(\d+)\s+(soldier|sailor|worker|gold)s?\s+from\s+(.+)',
        sentence,
    )
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        qty = int(match.group(2))
        kind = match.group(3).strip().lower()
        donor = resolve_character(match.group(4).strip(), game_state, player_id, enemy_ok=True)
        if not donor.found:
            parser.add_warning(order, f"Donor '{match.group(4).strip()}' not found")
            return order
        order.donor_id = donor.entity_id
        if kind == 'gold':
            order.gold_amount = qty
        else:
            order.unit_type = kind.upper()
            order.unit_count = qty
        return order

    # take N gold|units from Y (leader is recipient)
    match = re.search(
        r'^(?:get|take|obtain)\s+(\d+)\s+(soldier|sailor|worker|gold)s?\s+from\s+(.+)',
        sentence,
    )
    if match:
        if not parser.resolve_actor(order, None):
            return order
        qty = int(match.group(1))
        kind = match.group(2).strip().lower()
        donor = resolve_character(match.group(3).strip(), game_state, player_id, enemy_ok=True)
        if not donor.found:
            parser.add_warning(order, f"Donor '{match.group(3).strip()}' not found")
            return order
        order.donor_id = donor.entity_id
        if kind == 'gold':
            order.gold_amount = qty
        else:
            order.unit_type = kind.upper()
            order.unit_count = qty
        return order

    # get Joe and Tom — characters join actor (same faction only)
    match = re.search(r'(?:have\s+(.+?)\s+)?(?:get|take|obtain)\s+(.+)', sentence)
    if match and ' from ' not in sentence:
        actor_name = match.group(1).strip() if match.group(1) else None
        if not parser.resolve_actor(order, actor_name):
            return order
        # Without "from", treat remaining as character names to obtain (no units)
        names = match.group(2).strip()
        # Skip if it looks like a quantity transfer we failed to parse
        if re.match(r'^\d+\s+', names):
            return None
        # Use first named character as "donor" of themselves — engine joins them
        for name in re.split(r'\s+and\s+', names, flags=re.IGNORECASE):
            name = re.sub(r'[.,;!?]+$', '', name.strip())
            if not name:
                continue
            resolved = resolve_character(name, game_state, player_id)
            if resolved.found:
                # Encode as zero-resource transfer with donor = joined character
                order.donor_id = resolved.entity_id
                break
            parser.add_warning(order, f"Character '{name}' not found")
        return order if order.donor_id else order

    return None


def parse_transfer_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TransferOrder]:
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TransferOrder)

    match = re.search(
        r'have\s+(.+?)\s+transfer\s+(\d+)\s*(?:gold)?\s+to\s+(.+)',
        sentence,
    )
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        order.gold_amount = int(match.group(2))
        recip = resolve_character(match.group(3).strip(), game_state, player_id, enemy_ok=True)
        if not recip.found:
            parser.add_warning(order, f"Recipient '{match.group(3).strip()}' not found")
            return order
        order.recipient_id = recip.entity_id
        return order

    match = re.search(r'^transfer\s+(\d+)\s*(?:gold)?\s+to\s+(.+)', sentence)
    if match:
        if not parser.resolve_actor(order, None):
            return order
        order.gold_amount = int(match.group(1))
        recip = resolve_character(match.group(2).strip(), game_state, player_id, enemy_ok=True)
        if not recip.found:
            parser.add_warning(order, f"Recipient '{match.group(2).strip()}' not found")
            return order
        order.recipient_id = recip.entity_id
        return order

    return None


def parse_unload_order(sentence: str, game_state: GameState, player_id: str) -> Optional[UnloadOrder]:
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(UnloadOrder)

    match = re.search(r'have\s+(.+?)\s+unload\s+(.+)', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        targets = match.group(2).strip()
    else:
        match = re.search(r'^unload\s+(.+)', sentence)
        if not match:
            return None
        if not parser.resolve_actor(order, None):
            return order
        targets = match.group(1).strip()

    for name in re.split(r'\s+and\s+', targets, flags=re.IGNORECASE):
        name = re.sub(r'[.,;!?]+$', '', name.strip())
        if not name:
            continue
        resolved = resolve_character(name, game_state, player_id)
        if resolved.found:
            order.target_ids.append(resolved.entity_id)
            order.target_names.append(name)
        else:
            parser.add_warning(order, f"Character '{name}' not found")
    return order


def parse_pay_order(sentence: str, game_state: GameState, player_id: str) -> Optional[PayOrder]:
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(PayOrder)

    match = re.search(r'have\s+(.+?)\s+pay(?:\s+(\d+))?\s*(?:gold)?\s*$', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        if match.group(2):
            order.gold_amount = int(match.group(2))
        return order

    match = re.search(r'^pay(?:\s+(\d+))?\s*(?:gold)?\s*$', sentence)
    if match:
        if not parser.resolve_actor(order, None):
            return order
        if match.group(1):
            order.gold_amount = int(match.group(1))
        return order

    return None


def parse_borrow_order(sentence: str, game_state: GameState, player_id: str) -> Optional[BorrowOrder]:
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(BorrowOrder)

    match = re.search(r'have\s+(.+?)\s+borrow(?:\s+(\d+))?\s*(?:gold)?\s*$', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        if match.group(2):
            order.gold_amount = int(match.group(2))
        return order

    match = re.search(r'^borrow(?:\s+(\d+))?\s*(?:gold)?\s*$', sentence)
    if match:
        if not parser.resolve_actor(order, None):
            return order
        if match.group(1):
            order.gold_amount = int(match.group(1))
        return order

    return None


def parse_repay_order(sentence: str, game_state: GameState, player_id: str) -> Optional[RepayOrder]:
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(RepayOrder)

    match = re.search(r'have\s+(.+?)\s+repay(?:\s+(\d+))?\s*(?:gold)?\s*$', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        if match.group(2):
            order.gold_amount = int(match.group(2))
        return order

    match = re.search(r'^repay(?:\s+(\d+))?\s*(?:gold)?\s*$', sentence)
    if match:
        if not parser.resolve_actor(order, None):
            return order
        if match.group(1):
            order.gold_amount = int(match.group(1))
        return order

    return None


# ============================================================================
# MAIN PARSER FUNCTION
# ============================================================================

# Order detection keywords for optimization
ORDER_KEYWORDS = {
    'move': ['go', 'move', 'travel', 'come'],
    'sail': ['sail'],
    'recruit': ['recruit', 'hire'],
    'buy': ['buy'],
    'attack': ['attack'],
    'capture': ['capture'],
    'teleport': ['teleport'],
    'fly': ['fly'],
    'heal': ['heal', 'cure'],
    'pray': ['pray'],
    'bless': ['bless'],
    'curse': ['curse'],
    'resurrect': ['resurrect'],
    'secure': ['secure'],
    'fortify': ['fortify'],
    'unfortify': ['unfortify'],
    'ally': ['ally'],
    'enemy': ['enemy'],
    'neutral': ['neutral'],
    'assign': ['assign', 'give'],
    'name': ['name'],
    'promote': ['promote'],
    'tax': ['tax'],
    'trade': ['buy', 'sell', 'trade'],
    'await': ['await', 'wait'],
    'repeat': ['repeat'],
    'scry': ['scry'],
    'free': ['free', 'release', 'discard', 'dismiss'],
    'study': ['study'],
    'teach': ['teach'],
    'summon': ['summon'],
    'collect': ['collect', 'gather'],
    'build': ['build', 'construct', 'make'],
    'mine': ['mine'],
    'kill': ['kill', 'execute'],
    'enslave': ['enslave'],
    'interrogate': ['interrogate'],
    'noncom': ['noncom', 'combatant'],
    'lurk': ['lurk', 'unlurk'],
    'get': ['get', 'take', 'obtain'],
    'transfer': ['transfer'],
    'unload': ['unload'],
    'pay': ['pay'],
    'borrow': ['borrow'],
    'repay': ['repay'],
    'halt': ['halt', 'stop'],
    'join': ['join'],
    'support': ['support'],
}


# "Have <character> ..." -- rules.md's form for delegating an order.
HAVE_PREFIX = re.compile(r'^\s*have\s+')


def strip_repeatedly(sentence: str) -> tuple[str, Optional[int]]:
    """
    Lift the adverb `repeatedly` (and its loop count) off a sentence.

    Returns the sentence without them, and the loop count: None when the
    sentence was not a repeat at all, 0 for a loop with no count -- which
    `rules.md` says runs until a HALT or STOP.
    """
    if not re.search(r'\brepeatedly\b', sentence):
        return sentence, None

    count_match = re.search(r'\b(\d+)\s+times?\b', sentence)
    times = int(count_match.group(1)) if count_match else 0

    stripped = re.sub(r'\brepeatedly\b|\b\d+\s+times?\b', ' ', sentence)
    return ' '.join(stripped.split()), times


def parse_orders(raw_text: str, game_state: GameState, player_id: str) -> list[Order]:
    """
    Parse raw order text into a list of Order objects.

    This is the main entry point for order parsing. It can be replaced
    with an LLM-based implementation that has the same signature.

    `repeatedly` is an adverb rather than a verb, so it is lifted off its
    sentence before the verb dispatch below and emitted as its own REPEAT order
    in front of the command it governs. The engine's queue then treats
    everything after that REPEAT as the loop body.

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

        original_sentence = sentence
        sentence, repeat_times = strip_repeatedly(sentence)

        order = None

        if any(kw in sentence for kw in ORDER_KEYWORDS['halt']):
            order = parse_halt_order(sentence, game_state, player_id)

        # Try each parser based on keywords (optimization)
        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['move']):
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

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['pray']):
            order = parse_pray_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['bless']):
            order = parse_bless_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['curse']):
            order = parse_curse_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['resurrect']):
            order = parse_resurrect_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['secure']):
            order = parse_secure_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['fortify']):
            order = parse_fortify_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['unfortify']):
            order = parse_unfortify_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['ally']):
            order = parse_ally_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['enemy']):
            order = parse_enemy_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['neutral']):
            order = parse_neutral_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['assign']):
            order = parse_assign_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['name']):
            order = parse_name_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['promote']):
            order = parse_promote_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['tax']):
            order = parse_tax_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['trade']):
            order = parse_trade_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['await']):
            order = parse_await_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['repeat']):
            order = parse_repeat_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['scry']):
            order = parse_scry_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['capture']):
            order = parse_capture_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['free']):
            order = parse_free_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['study']):
            order = parse_study_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['teach']):
            order = parse_teach_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['summon']):
            order = parse_summon_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['collect']):
            order = parse_collect_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['build']):
            order = parse_build_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['mine']):
            order = parse_mine_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['kill']):
            order = parse_kill_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['enslave']):
            order = parse_enslave_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['interrogate']):
            order = parse_interrogate_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['noncom']):
            order = parse_noncom_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['lurk']):
            order = parse_lurk_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['get']):
            order = parse_get_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['transfer']):
            order = parse_transfer_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['unload']):
            order = parse_unload_order(sentence, game_state, player_id)

        # repay before pay: "repay" contains the substring "pay"
        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['repay']):
            order = parse_repay_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['borrow']):
            order = parse_borrow_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['pay']):
            order = parse_pay_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['join']):
            order = parse_join_order(sentence, game_state, player_id)

        if not order and any(kw in sentence for kw in ORDER_KEYWORDS['support']):
            order = parse_support_order(sentence, game_state, player_id)

        if order:
            # rules.md's HAVE form delegates to a named character, and that
            # makes them a group leader. Not every parser routes through
            # resolve_actor, so the delegation is recognised centrally here.
            if HAVE_PREFIX.match(original_sentence):
                order.explicit_actor = True

            if repeat_times is not None:
                # The loop marker takes the same actor as the command it governs,
                # so the two can never drift apart.
                orders.append(RepeatOrder(
                    player_id=player_id,
                    original_text=original_sentence,
                    actor_id=getattr(order, 'actor_id', ''),
                    times=repeat_times,
                ))
            orders.append(order)
        else:
            # Unparseable order - create placeholder with warning
            generic_order = MoveOrder(player_id=player_id, original_text=sentence)
            generic_order.warnings.append(f"Could not parse order: '{sentence}'")
            orders.append(generic_order)

    return orders
