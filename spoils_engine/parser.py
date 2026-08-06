"""
Natural-language order parser (rule-based) - REFACTORED.

Parses English-like commands into structured Order objects.
This implementation uses regex and string matching, but the
interface is designed to be replaceable with an LLM-based parser.
"""

import math
import re
from typing import Optional, Type
from dataclasses import dataclass, fields as dc_fields

from spoils_engine.models import (GameState, UnitType, ShipType, Character,
                                  LocationPosition, TITLE_WORDS)
from spoils_engine.orders import (
    Order, MoveOrder, SailOrder, RecruitOrder, BuyShipOrder, AttackOrder, TeleportOrder, FlyOrder, HealOrder,
    SecureOrder, FortifyOrder, UnfortifyOrder, AllyOrder, EnemyOrder, NeutralOrder, AssignOrder, NameOrder,
    PromoteOrder, TaxOrder, CaptureOrder, FreeOrder, StudyOrder, TeachOrder, SummonOrder, CollectOrder,
    BuildOrder, MineOrder, PrayOrder, BlessOrder, CurseOrder, ResurrectOrder, TradeOrder, AwaitOrder,
    RepeatOrder, ScryOrder, KillOrder, EnslaveOrder, InterrogateOrder, NoncomOrder, LurkOrder,
    ProbeOrder, SearchOrder, ScanOrder,
    ConjureOrder, ChargeOrder, AbsorbOrder, ItemPowerTransfer,
    MessageOrder, PostOrder, ReportOrder, AddressOrder, PasswordOrder,
    GetOrder, TransferOrder, UnloadOrder, PayOrder, BorrowOrder, RepayOrder,
    HaltOrder, StopOrder, JoinOrder, SupportOrder,
    WorkOrder, TrainOrder, UnnameOrder, CreateOrder, InvestOrder,
    PassageOrder, PreachOrder, OfferOrder, IfOrder,
)
from spoils_engine import config, items, pronouns
from spoils_engine.fog import parse_position_prefix


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


# A placeholder standing in for a quoted message while the order text is
# normalised. It has to survive lowercasing, comma stripping and the split on
# periods, so it is bare lowercase letters and digits and nothing else.
_QUOTE_TOKEN = "zqz{}zqz"
_QUOTE_TOKEN_RE = re.compile(r"zqz(\d+)zqz")


def protect_quotes(raw_text: str) -> tuple[str, list[str]]:
    """
    Lift double-quoted message bodies out of the raw order text.

    A message is the one place in an order where the player's exact characters
    matter. Everything else is lowercased, has its commas stripped and is split
    into sentences on periods -- all three of which would wreck

        Have Joe Flint post "Welcome to Madegi Doy. Recruiting is forbidden."

    So quoted spans come out first, each replaced by a placeholder, and go back
    in once parsing is done. This also keeps pronoun resolution out of message
    text, so a message that says "meet me at dawn" still says `me`.

    Returns the text with placeholders, and the quoted strings in order.
    """
    quoted: list[str] = []

    def take(match: re.Match) -> str:
        quoted.append(match.group(1))
        return _QUOTE_TOKEN.format(len(quoted) - 1)

    # Tabs are removed from messages per rules.md; the rest is left verbatim.
    return re.sub(r'"([^"]*)"', take, raw_text).replace("\t", " "), quoted


def restore_quotes(text: str, quoted: list[str]) -> str:
    """Put the original message text back where a placeholder stands."""
    def give(match: re.Match) -> str:
        index = int(match.group(1))
        return quoted[index] if index < len(quoted) else ""
    return _QUOTE_TOKEN_RE.sub(give, text)


def restore_order_quotes(order: Order, quoted: list[str]) -> None:
    """
    Put message text back into every string field of a parsed order.

    Done generically rather than per order type so that a new field carrying
    player text cannot quietly ship with a placeholder still in it.
    """
    if not quoted:
        return
    for f in dc_fields(order):
        value = getattr(order, f.name, None)
        if isinstance(value, str) and "zqz" in value:
            setattr(order, f.name, restore_quotes(value, quoted))


def strip_wand(sentence: str, game_state: GameState) -> tuple[str, str]:
    """
    Lift a trailing `with`/`using <wand>` clause off a spell order.

    rules.md casts a wand spell as the ordinary order "followed by the word
    with or using and the name of the wand", e.g. "teleport me to Kitesta
    using *Opistama*". Taking the clause off first keeps it out of the city or
    creature name the rest of the parser is trying to read.

    The clause is only recognised when it names an item that actually exists,
    so ordinary uses of `with` ("attack them with 50 soldiers") are untouched.
    Returns (sentence without the clause, wand name or "").
    """
    match = re.search(r'\s+(?:with|using)\s+(\S+)\s*$', sentence)
    if not match:
        return sentence, ""
    name = match.group(1)
    if not items.find_item_by_name(name, game_state):
        return sentence, ""
    return sentence[:match.start()].strip(), name


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
        char = _match_without_title(name_text, game_state, player_id)
        if char:
            return ResolvedEntity(char.id, char.name)
        # Independent characters (NPC factions) are recruitable: orders may
        # name them -- "Offer Bishop Nancy Lopenda 100 gold and have her come
        # to Pomye" -- so they resolve even before the player controls them.
        # The HAVE form on an NPC only becomes the player's own when the
        # offer is accepted (see engine.process_offer).
        char = game_state.get_character_by_name(name_text)
        if not char:
            words = name_text.split()
            if words and words[0] in TITLE_WORDS:
                char = game_state.get_character_by_name(" ".join(words[1:]))
        if char and _is_npc(char, game_state):
            return ResolvedEntity(char.id, char.name)
        if not enemy_ok:
            return ResolvedEntity("", name_text, found=False)

    # Search all factions (targets, or no issuing player given)
    char = game_state.get_character_by_name(name_text)
    if char:
        return ResolvedEntity(char.id, char.name)

    return ResolvedEntity("", name_text, found=False)


def _is_npc(char: Character, game_state: GameState) -> bool:
    """True when the character belongs to a computer-controlled faction."""
    faction = game_state.factions.get(char.faction_id)
    return bool(faction and faction.is_npc)


# rules.md: "Titles are ignored except in the NAME and PROMOTE commands, where
# they are mandatory." A player writes "Assign 200 soldiers to Captain Bill
# Jones" and means Bill Jones, so a leading title word is dropped before the
# name lookup.
def _match_without_title(name_text: str, game_state: GameState,
                         player_id: str) -> Optional[Character]:
    """A character whose name follows a leading title word."""
    words = name_text.split()
    if not words or words[0] not in TITLE_WORDS:
        return None
    return game_state.get_character_by_name(
        " ".join(words[1:]), faction_id=player_id)


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

def _resolve_destination(city_phrase: str, game_state: GameState,
                         order: MoveOrder, parser: "OrderParserBase") -> bool:
    """
    Resolve "outside Riverton" / "near Kitesta" / "Rome" onto a MoveOrder.

    Sets destination_city_id and destination_position. Returns False when the
    city cannot be found (a warning is already on the order).
    """
    position, city_name = parse_position_prefix(city_phrase)
    if not city_name:
        parser.add_warning(order, "No destination city given")
        return False
    city_resolved = resolve_city(city_name, game_state)
    if not city_resolved.found:
        parser.add_warning(order, f"City '{city_name}' not found")
        return False
    order.destination_city_id = city_resolved.entity_id
    order.destination_position = position.value
    return True


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
    match = re.search(r'have\s+(.+?)\s+(?:buy|purchase)\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
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
    match = re.search(r'^(?:buy|purchase)\s+(\d+)\s+(\w+)(?:\s+in\s+(.+))?', sentence)
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


# Everything GIVE, TAKE and ASSIGN move by the count: units, gold, and the
# mass resources the rules hand around ("Give 50 armor to Thomas Ames",
# "Take 10 copper and 20 silver from Bill Hawthorne").
_TRANSFER_KINDS = (r'soldier|sailor|worker|slave|gold|wood|stone|iron|'
                   r'silver|copper|gems|armor')
_RESOURCE_KINDS = ('wood', 'stone', 'iron', 'silver', 'copper', 'gems',
                   'armor')


def parse_assign_order(sentence: str, game_state: GameState, player_id: str) -> Optional[AssignOrder]:
    """Parse an assign/give order (simplified)."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AssignOrder)

    # Pattern: "have <donor> assign/give <quantity> <type> to <recipient>"
    # Example: "have Joe give 100 soldiers to Bill"
    match = re.search(
        rf'have\s+(.+?)\s+(?:assign|give)\s+(\d+)\s+({_TRANSFER_KINDS})s?\s+to\s+(.+)',
        sentence)
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

        _fill_assign(order, unit_or_gold, quantity, parser)
        return order

    # Pattern: "assign/give <quantity> <type> to <recipient>" (implicit leader as donor)
    match = re.search(
        rf'^(?:assign|give)\s+(\d+)\s+({_TRANSFER_KINDS})s?\s+to\s+(.+)', sentence)
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

        _fill_assign(order, unit_or_gold, quantity, parser)
        return order

    # Pattern: "assign <name> [and <name>] to <recipient>" -- named characters
    # rather than a count of unnamed units. rules.md: an assigned character
    # keeps whoever was already assigned to them, so a whole branch of the
    # group moves at once. A counted kind may sit in the same list ("Assign
    # 10 soldiers and Doctor McCoy to Joe Flint"): the count fills the
    # transfer and the names ride along.
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
            # A magical item is given by name exactly as a character is, so
            # try the item registry before reporting an unknown character.
            item = items.find_item_by_name(name, game_state)
            if item:
                order.item_ids.append(item.id)
                order.item_names.append(item.name)
                continue

            # A counted kind in a name list: "assign 10 soldiers and Doctor
            # McCoy to Joe Flint". One kind fills the transfer; the splitter
            # turns several kinds into one order each, so this is rare.
            counted = re.match(rf'^(\d+)\s+({_TRANSFER_KINDS})s?$', name)
            if counted:
                _fill_assign(order, counted.group(2).lower(),
                             int(counted.group(1)), parser)
                continue

            # A bare resource ("give stone to X" after "gather stone") hands
            # over whatever the donor holds. rules.md: "the pronoun it can
            # be used to refer to whatever was successfully collected".
            bare = re.fullmatch(rf"(?:{'|'.join(_RESOURCE_KINDS)})s?", name)
            if bare:
                order.resources[bare.group(0).rstrip('s')] = -1
                continue

            subject_resolved = resolve_character(name, game_state, player_id)
            if not subject_resolved.found:
                parser.add_warning(order, f"Character '{name}' not found")
                continue
            order.character_ids.append(subject_resolved.entity_id)
            order.character_names.append(subject_resolved.entity_name)

        return order

    # Pattern: "give <recipient> <quantity> <type>" -- the prepositionless
    # form. rules.md: "Have Joe give me 50 gold" and "Give Pindimya 10 gold"
    # mean the same as their `to` equivalents.
    match = re.search(
        rf'(?:have\s+(.+?)\s+)?(?:assign|give)\s+(.+?)\s+(\d+)\s+({_TRANSFER_KINDS})s?\s*$',
        sentence)
    if match:
        donor_name, recipient_name, quantity, unit_or_gold = match.groups()

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

        recipient_resolved = resolve_character(recipient_name.strip(), game_state, player_id, enemy_ok=True)
        if not recipient_resolved.found:
            parser.add_warning(order, f"Recipient '{recipient_name.strip()}' not found")
            return order
        order.recipient_id = recipient_resolved.entity_id

        _fill_assign(order, unit_or_gold.lower(), int(quantity), parser)
        return order

    return None


def _fill_assign(order: AssignOrder, kind: str, quantity: int,
                 parser: OrderParserBase) -> None:
    """Load one counted kind onto an AssignOrder."""
    if kind == 'gold':
        order.gold_amount += quantity
    elif kind in _RESOURCE_KINDS:
        order.resources[kind] = order.resources.get(kind, 0) + quantity
    else:
        # An order carries one unit kind. The splitter normally turns
        # "assign 5 soldiers and 3 workers to X" into one order per kind, so
        # a second kind here is a surprise rather than the common path.
        if order.unit_type and order.unit_type != kind.upper():
            parser.add_warning(
                order, f"Only one unit kind per GIVE; {kind}s not transferred")
            return
        order.unit_type = kind.upper()
        order.unit_count = quantity


def _fill_take(order: GetOrder, kind: str, quantity: int,
               parser: OrderParserBase) -> None:
    """Load one counted kind onto a GetOrder."""
    if kind == 'gold':
        order.gold_amount += quantity
    elif kind in _RESOURCE_KINDS:
        order.resources[kind] = order.resources.get(kind, 0) + quantity
    else:
        if order.unit_type and order.unit_type != kind.upper():
            parser.add_warning(
                order, f"Only one unit kind per TAKE; {kind}s not taken")
            return
        order.unit_type = kind.upper()
        order.unit_count = quantity


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
    sentence, wand_name = strip_wand(sentence, game_state)
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(SummonOrder)
    order.wand_name = wand_name

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

    match = re.search(r'have\s+(.+?)\s+(buy|purchase|sell)\s+(\d+)\s+([a-z]+)', sentence)
    if match:
        actor_name = match.group(1).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
        order.action = 'buy' if match.group(2) == 'purchase' else match.group(2)
        order.amount = int(match.group(3))
        order.resource_type = match.group(4)
        return order

    match = re.search(r'^(buy|purchase|sell)\s+(\d+)\s+([a-z]+)', sentence)
    if match:
        order.action = 'buy' if match.group(1) == 'purchase' else match.group(1)
        order.amount = int(match.group(2))
        order.resource_type = match.group(3)
        parser.resolve_actor(order, None)
        return order

    return None


# ============================================================================
# V1.1 PARSERS: WORK, TRAIN, UNNAME, CREATE, INVEST, PASSAGE, PREACH, OFFER
# ============================================================================

def _strip_clause_adverbs(sentence: str) -> str:
    r"""Remove the adverb words from a clause so they cannot be eaten into an
    actor name by a `have\s+(.+?)\s+<verb>` capture ("have joe flint
    definitely buy passage to amesbok" must name joe flint)."""
    return re.sub(r'\b(?:definitely|quietly|silently|briefly|carefully|'
                  r'exactly|repeatedly|then)\b', ' ', sentence)


def parse_work_order(sentence: str, game_state: GameState, player_id: str) -> Optional[WorkOrder]:
    """
    Parse a WORK order: work for wages for a duration.

    Examples:
        - "Work for 18 hours"
        - "Have Mike Foster work for 10 weeks"
        - "Have Billy Bob work."  # one game week by default
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(WorkOrder)

    if not re.search(r'\bwork\b', sentence):
        return None

    cleaned = _strip_clause_adverbs(sentence)
    actor_match = re.search(r'have\s+(.+?)\s+work\b', cleaned)
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    duration = parse_duration_days(sentence)
    order.duration_days = duration if duration is not None else config.DAYS_PER_TURN
    return order


def parse_train_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TrainOrder]:
    """
    Parse a TRAIN order: convert workers into soldiers or sailors.

    Examples:
        - "Train 20 soldiers"
        - "Have Admiral Bill Cunningham train 40 sailors"
        - "Have Genghis Khan train soldiers."  # every worker in his group
        - "train them"  # "them" is pronoun-resolved to the workers: train
          them *into* soldiers, per rules.md's "simply say 'train them'"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TrainOrder)

    if not re.search(r'\btrain\b', sentence):
        return None

    cleaned = _strip_clause_adverbs(sentence)
    actor_match = re.search(r'have\s+(.+?)\s+train\b', cleaned)
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    match = re.search(r'train\s+(?:(\d+)\s+)?(soldiers?|sailors?|workers?)', sentence)
    if match:
        count = int(match.group(1)) if match.group(1) else 0
        unit = match.group(2)
        if unit.startswith('sailor'):
            order.unit_type = 'sailor'
        else:
            # "train 30 workers" (what `train them` resolves to) means turn
            # 30 workers into soldiers -- soldiers are the default target.
            order.unit_type = 'soldier'
        order.count = count
    else:
        # Bare "train": every worker in the group becomes a soldier.
        order.unit_type = 'soldier'
        order.count = 0

    return order


def parse_unname_order(sentence: str, game_state: GameState, player_id: str) -> Optional[UnnameOrder]:
    """
    Parse an UNNAME order: convert a named character back to a worker.

    Examples:
        - "Unname Joe Flint"
        - "Have Mike Felton unname Charles Dickens"
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(UnnameOrder)

    if not re.search(r'\bunname\b', sentence):
        return None

    actor_match = re.search(r'have\s+(.+?)\s+unname\b', _strip_clause_adverbs(sentence))
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    target_match = re.search(r'unname\s+(.+)$', sentence)
    if not target_match:
        return None
    target_name = target_match.group(1).strip()

    resolved = resolve_character(target_name, game_state, player_id)
    if not resolved.found:
        return parser.add_warning(order, f"Character '{target_name}' not found")
    order.target_id = resolved.entity_id
    return order


def parse_create_order(sentence: str, game_state: GameState, player_id: str) -> Optional[CreateOrder]:
    """
    Parse a CREATE order: form an elite troop unit from soldiers.

    Examples:
        - "Create Gordy's Killers using 250 soldiers."
        - "Have General Wazawaza create The Wazoo Troop with 1200 soldiers."
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(CreateOrder)

    if not re.search(r'\bcreate\b', sentence):
        return None

    actor_match = re.search(r'have\s+(.+?)\s+create\b', _strip_clause_adverbs(sentence))
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    match = re.search(r'create\s+(.+?)\s+(?:using|with)\s+(\d+)\s+soldiers?', sentence)
    if not match:
        return None
    unit_name = match.group(1).strip()
    if len(unit_name) > 32:
        return parser.add_warning(order, f"Elite unit name too long (max 32 characters): '{unit_name}'")
    order.unit_name = unit_name
    order.count = int(match.group(2))
    return order


def parse_invest_order(sentence: str, game_state: GameState, player_id: str) -> Optional[InvestOrder]:
    """
    Parse an INVEST order: invest gold in a town's growth.

    Examples:
        - "Invest 400 gold in Ostrina'o."
        - "Have Bill Harrington invest all of his gold in Yodrina."
        - "Have Jane invest 75 percent of her gold in Kitesta."
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(InvestOrder)

    if not re.search(r'\binvest\b', sentence):
        return None

    actor_match = re.search(r'have\s+(.+?)\s+invest\b', _strip_clause_adverbs(sentence))
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    city_match = re.search(r'invest\b.*?\bin\s+(.+)$', sentence)
    if not city_match:
        return None
    city_name = city_match.group(1).strip()
    city = resolve_city(city_name, game_state)
    if not city.found:
        return parser.add_warning(order, f"City '{city_name}' not found")
    order.city_id = city.entity_id

    # Amount: a number, a percent of the actor's gold (stored negative), or
    # -1 for everything the actor has.
    percent_match = re.search(r'invest\s+(\d+)\s*(?:percent|%)\s*of\s+(?:his|her)\s+gold', sentence)
    if percent_match:
        order.amount = -float(percent_match.group(1))
    elif re.search(r'invest\s+(?:all|any)\b', sentence):
        order.amount = -1.0
    else:
        match = re.search(r'invest\s+(\d+(?:\.\d+)?)\s*(?:gold)?\b', sentence)
        if not match:
            return None
        order.amount = float(match.group(1))
    return order


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


def parse_preach_order(sentence: str, game_state: GameState, player_id: str) -> Optional[PreachOrder]:
    """
    Parse a PREACH order: preach for tithes and donations.

    Examples:
        - "Preach for 6 days."
        - "Have Bishop Jake Henderson preach for 2 weeks."
        - "Have Primate Melissa Davies preach."  # one game week by default
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(PreachOrder)

    if not re.search(r'\bpreach\b', sentence):
        return None

    actor_match = re.search(r'have\s+(.+?)\s+preach\b', _strip_clause_adverbs(sentence))
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    duration = parse_duration_days(sentence)
    order.duration_days = duration if duration is not None else config.DAYS_PER_TURN
    return order


def parse_offer_order(sentence: str, game_state: GameState, player_id: str) -> Optional[OfferOrder]:
    """
    Parse an OFFER order: offer gold to recruit an independent character.

    Examples:
        - "Offer Bishop Nancy Lopenda 100 gold and have her come to Pomye."
        - "Have Joe Bellin offer 75 percent of his gold to Engineer Tegwi Olafson."
        - "Offer 1500 to Wizard Ojibenmi and have him summon 3 dragons."
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(OfferOrder)

    if not re.search(r'\boffer\b', sentence):
        return None

    actor_match = re.search(r'have\s+(.+?)\s+offer\b', _strip_clause_adverbs(sentence))
    if not parser.resolve_actor(order, actor_match.group(1).strip() if actor_match else None):
        return order

    # Two spellings: "Offer 1500 to Wizard Ojibenmi" and the rules' favourite
    # "Offer Bishop Nancy Lopenda 100 gold" (name before the amount).
    target_name = None
    target_match = re.search(r'offer\b.*?\bto\s+(.+)$', sentence)
    if target_match:
        target_name = target_match.group(1).strip()
    else:
        named = re.search(r'offer\s+([a-z][a-z0-9\' ]*?)\s+(\d+(?:\.\d+)?)\s*(?:gold)?\b', sentence)
        if named:
            target_name = named.group(1).strip()
    if not target_name:
        return None
    resolved = resolve_character(target_name, game_state, player_id, enemy_ok=True)
    if not resolved.found:
        return parser.add_warning(order, f"Character '{target_name}' not found")
    order.target_id = resolved.entity_id

    percent_match = re.search(r'offer\s+(\d+)\s*(?:percent|%)\s*of\s+(?:his|her)\s+gold', sentence)
    if percent_match:
        order.amount = -float(percent_match.group(1))  # negative = percent
    elif re.search(r'offer\s+(?:all|any)\b', sentence):
        order.amount = -1.0  # everything the actor has
    else:
        # The amount is the first number after "offer": "Offer 1500 to
        # Wizard Ojibenmi" or "Offer Bishop Nancy Lopenda 100 gold".
        after = sentence[sentence.find('offer') + len('offer'):]
        amount_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:gold)?\b', after)
        if amount_match:
            order.amount = float(amount_match.group(1))
        else:
            return parser.add_warning(order, "Offer how much gold?")
    return order


def parse_if_order(sentence: str, game_state: GameState, player_id: str) -> Optional[IfOrder]:
    """
    Parse an IF statement: `if <condition> then <orders>` with an optional
    `otherwise`/`else` branch. Scope is the rest of the sentence, and IF may
    not be nested. The condition is stored unresolved (by name) and evaluated
    when the order is reached on the queue.

    The head of the sentence (commands before the `if`) is parsed by the
    caller; only the tail from the `if` onward lands here.
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(IfOrder)

    if_match = re.search(r'\bif\s+(.+?)\b(?:then|,)\s+(.+)$', sentence)
    if not if_match:
        return parser.add_warning(order, "If statement needs a condition and a 'then'")
    condition_text = if_match.group(1).strip()
    body_text = if_match.group(2).strip()

    else_match = re.search(r'\b(?:otherwise|else)\b\s+(.+)$', body_text)
    if else_match:
        then_text = body_text[:else_match.start()].strip()
        else_text = else_match.group(1).strip()
    else:
        then_text, else_text = body_text, ""

    condition = parse_if_condition(condition_text, game_state, player_id)
    if condition is None:
        return parser.add_warning(order, f"Unrecognised condition: '{condition_text}'")
    order.condition = condition
    if condition.get("subject_name"):
        subject = resolve_character(condition["subject_name"], game_state, player_id, enemy_ok=True)
        if subject.found:
            order.actor_id = subject.entity_id

    # Branch bodies parse as ordinary clauses: "then take it from her and fly
    # to Umadosh" is two orders. Per rules.md they do NOT inherit the head's
    # HAVE target -- "if he has 1000 soldiers then go to Kitesta" has the
    # player's own leader go, not the tested character.
    order.then_orders = _parse_clause_body(
        then_text, game_state, player_id, have_target="", prev_verb="")
    if else_text:
        order.else_orders = _parse_clause_body(
            else_text, game_state, player_id, have_target="", prev_verb="")
    if not order.then_orders and not order.else_orders:
        return parser.add_warning(order, "If statement has no orders in its branches")
    return order


_CONDITION_ITEMS = (
    "soldiers", "sailors", "workers", "slaves", "horses", "catapults",
    "weapons", "armor", "galleys", "ships",
    "skeletons", "zombies", "harpies", "minotaurs", "griffins", "chimeras",
    "dragons", "demons",
    "gold", "wood", "stone", "iron", "copper", "silver", "gems",
    "encumbrance", "power",
)

_CONDITION_COMPARATORS = (
    "less than", "fewer than", "more than", "at least", "at most", "exactly",
)

_IF_UNIT_TO_KEY = {
    "soldier": "soldier", "sailor": "sailor", "worker": "worker",
    "slave": "slave", "horse": "horse", "catapult": "catapult",
    "weapon": "weapon", "armor": "armor", "galley": "galley",
    "ship": "galley", "skeleton": "skeleton", "zombie": "zombie",
    "harpy": "harpy", "minotaur": "minotaur", "griffin": "griffin",
    "chimera": "chimera", "dragon": "dragon", "demon": "demon",
    "gold": "gold", "wood": "wood", "stone": "stone", "iron": "iron",
    "copper": "copper", "silver": "silver", "gem": "gems", "gems": "gems",
    "encumbrance": "encumbrance", "power": "power",
}


def parse_if_condition(text: str, game_state: GameState, player_id: str) -> Optional[dict]:
    """
    Parse the condition of an IF statement into a structured dict.

    The shape is "<who> has/have [magic|religious] <comparator> <amount>
    <item>". With no comparator it means `exactly`; `any`/`some` means more
    than zero. The subject is stored by name and resolved at evaluation time,
    because the order may sit on a queue and the character's existence (e.g.
    an NPC who joins later) may change before it runs.
    """
    has_match = re.search(r'^(.+?)\s+has\s+(.+)$', text)
    if not has_match:
        return None
    subject_name = has_match.group(1).strip()
    remainder = has_match.group(2).strip()

    power_modifier = ""
    for mod in ("magical", "magic", "religious", "religion"):
        if re.search(r'\b' + mod + r'\b', remainder):
            power_modifier = mod
            remainder = re.sub(r'\b' + mod + r'\b', ' ', remainder)
            break

    comparator = None
    for comp in _CONDITION_COMPARATORS:
        if re.search(r'\b' + comp + r'\b', remainder):
            comparator = comp
            remainder = re.sub(r'\b' + comp + r'\b', ' ', remainder)
            break

    if re.search(r'\b(?:any|some)\b', remainder):
        comparator = "more than"
        remainder = re.sub(r'\b(?:any|some)\b', ' ', remainder)

    amount = None
    amount_match = re.search(r'(\d+)', remainder)
    if amount_match:
        amount = int(amount_match.group(1))

    unit = ""
    for item in _CONDITION_ITEMS:
        if re.search(r'\b' + item + r'\b', remainder):
            unit = item
            break

    if unit == "power" and not power_modifier:
        # rules.md: no modifier means the higher of magic and religion power.
        power_modifier = "either"

    if comparator is None:
        comparator = "exactly"

    return {
        "subject_name": subject_name,
        "comparator": comparator,
        "amount": amount if amount is not None else 0,
        "unit": _IF_UNIT_TO_KEY.get(unit.rstrip('s'), unit),
        "power_modifier": power_modifier,
    }


def _parse_clause_body(text: str, game_state: GameState, player_id: str,
                       have_target: str, prev_verb: str) -> list[Order]:
    """Parse a run of clauses (an IF branch body) into orders."""
    orders: list[Order] = []
    for clause in split_clauses(text, game_state, player_id):
        clause = re.sub(r'^then\s+', '', clause.strip())
        if not clause:
            continue
        if clause.startswith("have "):
            have_target = _have_target(clause)
        elif _leading_verb(clause):
            if have_target:
                clause = f"have {have_target} {clause}"
        elif prev_verb:
            clause = f"{prev_verb} {clause}"
        order = _dispatch_clause(clause, game_state, player_id)
        verb = _leading_verb(clause)
        if verb:
            prev_verb = verb
        if order:
            # The HAVE form delegates and promotes to group leader; mirror
            # the central marking in parse_orders so branch orders promote.
            if clause.startswith("have "):
                order.explicit_actor = True
            orders.append(order)
    return orders


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


def parse_probe_order(sentence: str, game_state: GameState, player_id: str) -> Optional[ProbeOrder]:
    """Parse PROBE <character> / have X probe Y."""
    sentence, wand_name = strip_wand(sentence, game_state)
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(ProbeOrder)
    order.wand_name = wand_name

    match = re.search(r'have\s+(.+?)\s+probe\s+(.+)', sentence)
    if match:
        actor_name = match.group(1).strip()
        target_name = match.group(2).strip()
        if not parser.resolve_actor(order, actor_name):
            return order
    else:
        match = re.search(r'^probe\s+(.+)', sentence)
        if not match:
            return None
        target_name = match.group(1).strip()
        if not parser.resolve_actor(order, None):
            return order

    target = resolve_character(target_name, game_state)
    if not target.found:
        parser.add_warning(order, f"Character '{target_name}' not found")
        return order
    order.target_id = target.entity_id
    order.target_name = target.entity_name
    return order


def parse_search_order(sentence: str, game_state: GameState, player_id: str) -> Optional[SearchOrder]:
    """Parse SEARCH / EXPLORE (optional 'for N days/weeks')."""
    if not re.search(r'\b(?:search|explore)\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(SearchOrder)

    match = re.search(r'have\s+(.+?)\s+(?:search|explore)\b', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
    else:
        if not parser.resolve_actor(order, None):
            return order

    weeks = re.search(r'for\s+(\d+)\s+weeks?', sentence)
    days = re.search(r'for\s+(\d+)\s+days?', sentence)
    if weeks:
        order.duration_days = int(weeks.group(1)) * 7
    elif days:
        order.duration_days = int(days.group(1))
    else:
        order.duration_days = 7
    return order


def parse_scan_order(sentence: str, game_state: GameState, player_id: str) -> Optional[ScanOrder]:
    """Parse SCAN <cities> using/with <orb>."""
    if not re.search(r'\bscan\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(ScanOrder)

    match = re.search(r'have\s+(.+?)\s+scan\s+(.+)', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        rest = match.group(2).strip()
    else:
        match = re.search(r'^scan\s+(.+)', sentence)
        if not match:
            return None
        if not parser.resolve_actor(order, None):
            return order
        rest = match.group(1).strip()

    # An orb is named by a trailing `using`/`with` clause. rules.md also allows
    # pairing several city groups with several orbs in one sentence ("scan
    # Plugby and Irontown using Jamibo and Tashendi using Akitemba"); that form
    # is rejected rather than silently misread, since one order carries one orb.
    orb_clauses = list(re.finditer(r'\b(?:using|with)\s+(\S+)', rest))
    if len(orb_clauses) > 1:
        return parser.add_warning(
            order, "SCAN names more than one orb; give each orb its own order")
    if orb_clauses:
        order.orb_name = orb_clauses[0].group(1).strip()
        rest = rest[:orb_clauses[0].start()].strip()

    city_parts = re.split(r'\s+and\s+', rest)
    for part in city_parts:
        part = part.strip()
        if not part:
            continue
        resolved = resolve_city(part, game_state)
        if not resolved.found:
            parser.add_warning(order, f"City '{part}' not found")
            continue
        order.city_ids.append(resolved.entity_id)
        order.city_names.append(resolved.entity_name)
    if not order.city_ids and not order.warnings:
        parser.add_warning(order, "No cities to scan")
    return order


def _resolve_recipients(text: str, order, game_state: GameState,
                        parser: "OrderParserBase") -> None:
    """
    Work out who a SAY or TELL is addressed to.

    rules.md allows three kinds of addressee, and they are told apart by what
    the name matches: `everyone` reaches every player, a town's name reaches
    everyone in it, and anything else must be a named character — of any
    faction, since messaging an opponent is the point of the verb.
    """
    for part in re.split(r'\s+and\s+', text):
        part = part.strip().rstrip('.')
        if not part:
            continue
        if part == "everyone":
            order.to_everyone = True
            continue

        city = resolve_city(part, game_state)
        if city.found:
            order.recipient_city_id = city.entity_id
            order.recipient_city_name = city.entity_name
            continue

        # enemy_ok: a message is not an order, so it may name anybody.
        person = resolve_character(part, game_state, parser.player_id,
                                   enemy_ok=True)
        if not person.found:
            parser.add_warning(order, f"No character or town called '{part}'")
            continue
        order.recipient_ids.append(person.entity_id)
        order.recipient_names.append(person.entity_name)


def parse_message_order(sentence: str, game_state: GameState,
                        player_id: str) -> Optional[MessageOrder]:
    """
    Parse SAY and TELL.

    rules.md: "With SAY, the name of the recipient must follow the preposition
    to which, in turn, follows the message. With TELL, the order is reversed
    and the preposition to is not used."

        Have Joe Flint say "Not on your life!" to King Bodo Bunji.
        Tell everyone "Emperor John May has declared himself ruler!"
    """
    if not re.search(r'\b(?:say|tell)\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(MessageOrder)

    match = re.search(r'have\s+(.+?)\s+(say|tell)\b\s*(.*)$', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        verb, rest = match.group(2), match.group(3).strip()
    else:
        match = re.search(r'\b(say|tell)\b\s*(.*)$', sentence)
        if not match:
            return None
        if not parser.resolve_actor(order, None):
            return order
        verb, rest = match.group(1), match.group(2).strip()

    body = _QUOTE_TOKEN_RE.search(rest)
    if not body:
        return parser.add_warning(
            order, f"{verb.upper()} needs a message in double quotes")
    order.message = body.group(0)

    if verb == "say":
        # say "<message>" to <who>
        tail = rest[body.end():].strip()
        recipients = re.sub(r'^to\s+', '', tail).strip()
    else:
        # tell <who> "<message>"
        recipients = rest[:body.start()].strip()
        # Anything after the message means the player forgot the period that
        # ends the sentence, so the next order ran into this one. Say so
        # rather than dropping it: a swallowed order is invisible otherwise.
        trailing = rest[body.end():].strip()
        if trailing:
            parser.add_warning(
                order,
                f"'{trailing}' follows the message and was ignored — put a "
                f"period after the closing quote to start a new order")

    if not recipients:
        return parser.add_warning(order, f"{verb.upper()} names no recipient")
    _resolve_recipients(recipients, order, game_state, parser)
    return order


def parse_post_order(sentence: str, game_state: GameState,
                     player_id: str) -> Optional[PostOrder]:
    """Parse POST "<message>" — a notice at the gates of a secured town."""
    if not re.search(r'\bpost\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(PostOrder)

    match = re.search(r'have\s+(.+?)\s+post\b\s*(.*)$', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        rest = match.group(2).strip()
    else:
        match = re.search(r'\bpost\b\s*(.*)$', sentence)
        if not match:
            return None
        if not parser.resolve_actor(order, None):
            return order
        rest = match.group(1).strip()

    body = _QUOTE_TOKEN_RE.search(rest)
    if not body:
        return parser.add_warning(
            order, 'POST needs a message in double quotes (use "" to take one down)')
    order.message = body.group(0)
    return order


def parse_report_order(sentence: str, game_state: GameState,
                       player_id: str) -> Optional[ReportOrder]:
    """
    Parse REPORT and QUERY, with the optional `briefly` adverb.

        Report.
        Query Bill Johnson and Joe Flint.
        Have Jane Edwards go to Nodim and briefly report.
    """
    match = re.search(r'\b(report|query)\b', sentence)
    if not match:
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(ReportOrder)
    order.immediate = match.group(1) == "query"
    order.brief = bool(re.search(r'\bbriefly\b', sentence))

    have = re.search(r'have\s+(.+?)\s+(?:briefly\s+)?(?:report|query)\b', sentence)
    if have:
        if not parser.resolve_actor(order, have.group(1).strip()):
            return order
    elif not parser.resolve_actor(order, None):
        return order

    # Anything after the verb names the characters being asked. With nothing
    # there, the actor reports on themselves.
    tail = sentence[match.end():].strip().rstrip('.')
    tail = re.sub(r'^(?:on|about|from)\s+', '', tail).strip()
    if not tail or tail.startswith("my "):
        order.subject_ids = [order.actor_id]
        subject = game_state.characters.get(order.actor_id)
        order.subject_names = [subject.name] if subject else []
        return order

    for part in re.split(r'\s+and\s+', tail):
        part = part.strip()
        if not part:
            continue
        person = resolve_character(part, game_state, player_id)
        if not person.found:
            parser.add_warning(order, f"Character '{part}' not found")
            continue
        order.subject_ids.append(person.entity_id)
        order.subject_names.append(person.entity_name)

    if not order.subject_ids and not order.warnings:
        order.subject_ids = [order.actor_id]
    return order


def parse_address_order(sentence: str, game_state: GameState,
                        player_id: str) -> Optional[AddressOrder]:
    """Parse ADDRESS "<email>"."""
    if not re.search(r'\baddress\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AddressOrder)

    body = _QUOTE_TOKEN_RE.search(sentence)
    if not body:
        return parser.add_warning(
            order, "ADDRESS needs an email address in double quotes")
    order.address = body.group(0)
    return order


def parse_password_order(sentence: str, game_state: GameState,
                         player_id: str) -> Optional[PasswordOrder]:
    """
    Parse PASSWORD, quoted or bare.

    rules.md accepts `Password SerendipityDoDah` as well as the quoted form,
    and requires quotes only when the password contains spaces or punctuation.
    """
    match = re.search(r'\bpassword\b\s*(.*)$', sentence)
    if not match:
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(PasswordOrder)

    rest = match.group(1).strip().rstrip('.')
    body = _QUOTE_TOKEN_RE.search(rest)
    if body:
        order.password = body.group(0)
    elif rest:
        order.password = rest
    else:
        return parser.add_warning(order, "PASSWORD needs a password")
    return order


def parse_conjure_order(sentence: str, game_state: GameState,
                        player_id: str) -> Optional[ConjureOrder]:
    """
    Parse CONJURE <item kind> [of <skill|spell>].

    e.g. "conjure an amulet of trading", "have delphinus conjure an orb",
    "conjure a wand of teleport".
    """
    if not re.search(r'\bconjure\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(ConjureOrder)

    match = re.search(r'have\s+(.+?)\s+conjure\b', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
    elif not parser.resolve_actor(order, None):
        return order

    body = re.search(r'conjure\s+(?:an?|the)?\s*'
                     r'(amulet|crystal|orb|ring|wand)\b'
                     r'(?:\s+(?:of|for)\s+(\w+))?', sentence)
    if not body:
        return parser.add_warning(
            order, "CONJURE needs an item kind: amulet, crystal, orb, ring or wand")

    order.item_type = body.group(1)
    qualifier = (body.group(2) or "").strip()

    if order.item_type == "amulet":
        if not qualifier:
            return parser.add_warning(
                order, "Conjuring an amulet needs a skill, e.g. 'an amulet of trading'")
        if qualifier in items.AMULET_FORBIDDEN_SKILLS:
            return parser.add_warning(
                order, f"An amulet never provides skill in {qualifier}")
        if qualifier not in items.AMULET_SKILLS:
            return parser.add_warning(order, f"Unknown amulet skill '{qualifier}'")
        order.skill = qualifier
    elif order.item_type == "wand":
        if not qualifier:
            return parser.add_warning(
                order, "Conjuring a wand needs a spell, e.g. 'a wand of teleport'")
        spell = items.canonical_spell(qualifier)
        if not spell:
            return parser.add_warning(order, f"No wand provides '{qualifier}'")
        order.spell = spell

    return order


def _parse_item_transfers(clause: str, game_state: GameState,
                          parser: "OrderParserBase", order: Order,
                          absorbing: bool) -> list[ItemPowerTransfer]:
    """
    Pull the item/quantity pairs out of a CHARGE or ABSORB clause.

    Both verbs list their items with `and`, and each item may carry its own
    quantity. CHARGE puts the quantity after the item (`Ampu to 75 power`),
    ABSORB puts it before (`10 points from Madingo`), and either may leave it
    out to mean as much as possible.
    """
    transfers = []
    for part in re.split(r'\s+and\s+', clause):
        part = part.strip().rstrip('.')
        if not part:
            continue

        amount, to_level = -1, False
        if absorbing:
            # "10 points from Madingo", "all power from Gendari", "Madingo"
            qty = re.match(r'(?:(\d+)|all|everything)\s*(?:points?|power)?\s*'
                           r'(?:from\s+)?(.*)$', part)
            if qty:
                if qty.group(1):
                    amount = int(qty.group(1))
                part = qty.group(2).strip()
        else:
            # "Hasimpa by 10 points", "Ampu to 75 power", "Madingo"
            qty = re.search(r'\s+(by|to)\s+(\d+)\s*(?:points?|power)?\s*$', part)
            if qty:
                to_level = qty.group(1) == "to"
                amount = int(qty.group(2))
                part = part[:qty.start()].strip()

        # A bare "it" refers back to the item the previous clause named.
        if part in ("it", "them") and transfers:
            part = transfers[-1].item_name
        if not part:
            continue

        item = items.find_item_by_name(part, game_state)
        if not item:
            parser.add_warning(order, f"No magical item called '{part}'")
            continue
        transfers.append(ItemPowerTransfer(
            item_id=item.id, item_name=item.name,
            amount=amount, to_level=to_level,
        ))
    return transfers


def parse_charge_order(sentence: str, game_state: GameState,
                       player_id: str) -> Optional[ChargeOrder]:
    """
    Parse CHARGE / RECHARGE <item> [by N | to N] [and <item> ...].

    e.g. "recharge madingo", "have merlinus recharge hasimpa by 10 points",
    "charge ampu to 75 power".
    """
    if not re.search(r'\b(?:re)?charge\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(ChargeOrder)

    match = re.search(r'have\s+(.+?)\s+(?:re)?charge\s+(.+)', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        rest = match.group(2)
    else:
        match = re.search(r'\b(?:re)?charge\s+(.+)', sentence)
        if not match:
            return None
        if not parser.resolve_actor(order, None):
            return order
        rest = match.group(1)

    order.targets = _parse_item_transfers(rest, game_state, parser, order,
                                          absorbing=False)
    if not order.targets and not order.warnings:
        parser.add_warning(order, "CHARGE names no magical item")
    return order


def parse_absorb_order(sentence: str, game_state: GameState,
                       player_id: str) -> Optional[AbsorbOrder]:
    """
    Parse ABSORB [N points] [from] <item> [and ...].

    e.g. "absorb 10 points from madingo", "absorb all power from gendari",
    "have merlinus absorb everything from umiki".
    """
    if not re.search(r'\babsorb\b', sentence):
        return None
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AbsorbOrder)

    match = re.search(r'have\s+(.+?)\s+absorb\s+(.+)', sentence)
    if match:
        if not parser.resolve_actor(order, match.group(1).strip()):
            return order
        rest = match.group(2)
    else:
        match = re.search(r'\babsorb\s+(.+)', sentence)
        if not match:
            return None
        if not parser.resolve_actor(order, None):
            return order
        rest = match.group(1)

    order.targets = _parse_item_transfers(rest, game_state, parser, order,
                                          absorbing=True)
    if not order.targets and not order.warnings:
        parser.add_warning(order, "ABSORB names no magical item")
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

    # have X take N gold|units|resources from Y
    match = re.search(
        rf'have\s+(.+?)\s+(?:get|take|obtain)\s+(\d+)\s+({_TRANSFER_KINDS})s?\s+from\s+(.+)',
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
        _fill_take(order, kind, qty, parser)
        return order

    # take N gold|units|resources from Y (leader is recipient)
    match = re.search(
        rf'^(?:get|take|obtain)\s+(\d+)\s+({_TRANSFER_KINDS})s?\s+from\s+(.+)',
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
        _fill_take(order, kind, qty, parser)
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
    'buy': ['buy', 'purchase'],
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
    'trade': ['buy', 'sell', 'trade', 'purchase'],
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
    'probe': ['probe'],
    'search': ['search', 'explore'],
    'scan': ['scan'],
    'message': ['say', 'tell'],
    'post': ['post'],
    'report': ['report', 'query'],
    'address': ['address'],
    'password': ['password'],
    'conjure': ['conjure'],
    'charge': ['charge', 'recharge'],
    'absorb': ['absorb'],
    'get': ['get', 'take', 'obtain'],
    'transfer': ['transfer'],
    'unload': ['unload'],
    'pay': ['pay'],
    'borrow': ['borrow'],
    'repay': ['repay'],
    'halt': ['halt', 'stop'],
    'join': ['join'],
    'support': ['support'],
    'work': ['work'],
    'train': ['train'],
    'unname': ['unname'],
    'create': ['create'],
    'invest': ['invest'],
    'passage': ['passage'],
    'offer': ['offer'],
    'preach': ['preach'],
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


# ============================================================================
# AND-CHAINED COMMANDS
# ============================================================================

# Adverbs that may sit between `and` and the verb of the next chained command:
# "Buy 10 horses and briefly query Joe Flint" (rules.md) or "and have him and
# Joe Bunnions ... immediately charge it". They belong to the clause that
# follows them, and are skipped when reading the head of a clause. `then` is
# included so "wait for 2 weeks and then go to Salem" chains like any other
# command (see rules.md's THEN sequencing).
_CLAUSE_ADVERBS = ("immediately", "silently", "quietly", "definitely",
                   "briefly", "exactly", "carefully", "repeatedly", "then")

# Every word that can start a command, for recognising where a clause begins.
_COMMAND_VERBS = frozenset(
    word for words in ORDER_KEYWORDS.values() for word in words) | {"have"}

# Prepositions that hand an assign-style list to its target, used to fold the
# target back onto an unfinished clause ("assign 20 soldiers and 23 horses to
# Bill Jenkins" splits into one order per kind, both naming Bill Jenkins).
_TARGET_PREPOSITIONS = ("to", "from", "by", "in")


def _first_word_after_adverbs(text: str) -> str:
    """The first significant word of a clause, skipping leading adverbs."""
    for word in text.split():
        if word in _CLAUSE_ADVERBS:
            continue
        return word
    return ""


def _leading_verb(clause: str) -> str:
    """The first command verb word of a clause, after the HAVE marker.

    "recruit" for "have mary anderson recruit 5 soldiers and 3 workers"; ""
    for a clause that continues the previous command ("20 horses to Bill
    Fenton"). `have` is the delegation marker rather than a verb, so it is
    passed over: the elided continuation of a have-clause is its *action*.
    """
    for word in clause.split():
        if word in _COMMAND_VERBS and word != "have":
            return word
    return ""


def _have_target(clause: str) -> str:
    """The name(s) `have` hands the order to, up to the first verb.

    "bill jenkins" for "have bill jenkins go to riverton", and the whole
    list for "have merlinus and joe bunnions charge it". A "to" between the
    name and the verb ("have him to go to Kitesta", which rules.md uses) is
    skipped rather than swallowed into the name.
    """
    words = clause.split()
    if not words or words[0] != "have":
        return ""
    taken = []
    for word in words[1:]:
        if word in _COMMAND_VERBS:
            break
        if word in _CLAUSE_ADVERBS or word == "to":
            continue
        taken.append(word)
    return " ".join(taken)


def _replicate_target(prefix: str, remainder: str, elided_verb: str,
                      game_state: GameState, player_id: str) -> Optional[str]:
    """
    Fold the tail's target phrase back onto an unfinished clause.

    In "assign 20 soldiers and 23 horses to Bill Jenkins" the first clause is
    not complete until its target arrives, and the target sits in the tail.
    Taking the tail up to its first preposition gives "assign 20 soldiers to
    Bill Jenkins", which is a complete command -- so the `and` is a boundary
    and the tail can start its own clause. Returns the completed clause, or
    None when the tail does not complete it.
    """
    words = remainder.split()
    for index, word in enumerate(words):
        if word not in _TARGET_PREPOSITIONS:
            continue
        # The target phrase runs to the next `and` (the next clause) or the
        # end of the sentence.
        cut = next((j for j in range(index, len(words)) if words[j] == "and"),
                   len(words))
        tail = " ".join(words[index:cut])
        candidate = f"{prefix} {tail}"
        if _clause_complete(candidate, elided_verb, game_state, player_id):
            return candidate
        return None
    return None


def _clause_complete(clause: str, elided_verb: str, game_state: GameState,
                     player_id: str) -> bool:
    """
    Whether `clause` is a whole command on its own.

    A clause that starts with a quantity or a name rather than a verb is a
    continuation of the previous command ("20 horses to Bill Fenton" after
    "give 50 gold to Nancy Myers"), so it is judged with the previous verb
    put back in front. A parser that matched the grammar counts as complete
    even when entity resolution failed: the order it returns carries its own
    honest warning.
    """
    if not _leading_verb(clause) and elided_verb:
        clause = f"{elided_verb} {clause}"
    if not _leading_verb(clause):
        return False
    return _dispatch_clause(clause, game_state, player_id) is not None


def split_clauses(sentence: str, game_state: GameState,
                  player_id: str) -> list[str]:
    """
    Split one sentence into command clauses at its `and` boundaries.

    `and` joins either items within one command or whole commands:
    "Assign 20 soldiers and 23 horses to Bill Jenkins, and have him go to
    Riverton and attack Mike May" is three commands. A boundary is an `and`
    whose clause so far is complete and whose tail starts a new one -- with
    a verb, with `have`, or with a quantity that continues the previous verb
    ("give 50 gold to Nancy Myers and 20 horses to Bill Fenton"). When the
    clause so far is unfinished but would be complete with the tail's target
    folded back onto it, the target is replicated instead.

    The sentence is already pronoun-resolved, so the clauses it yields are
    ready for verb dispatch.
    """
    clauses: list[str] = []
    start = 0
    prev_verb = ""

    for match in re.finditer(r"\s+and\s+", sentence):
        prefix = sentence[start:match.start()].strip()
        if not prefix:
            continue
        head = _first_word_after_adverbs(sentence[match.end():])
        if head not in _COMMAND_VERBS and not head.isdigit():
            continue

        if _clause_complete(prefix, prev_verb, game_state, player_id):
            clauses.append(prefix)
            start = match.end()
            verb = _leading_verb(prefix)
            if verb:
                prev_verb = verb
            continue

        # The clause so far lacks its target but the tail carries it.
        if head.isdigit():
            completed = _replicate_target(prefix, sentence[match.end():],
                                          prev_verb, game_state, player_id)
            if completed is not None:
                clauses.append(completed)
                start = match.end()
                # A replicated clause is a continuation ("2 workers to Bill
                # Gershwin"), so the verb stays the previous clause's.
                verb = _leading_verb(completed)
                if verb:
                    prev_verb = verb

    tail = sentence[start:].strip()
    if tail:
        clauses.append(tail)
    return clauses


def _dispatch_clause(sentence: str, game_state: GameState,
                     player_id: str) -> Optional[Order]:
    """
    Route one clause to the verb parser that handles it.

    This is the shared heart of order parsing: `parse_orders` calls it once
    per clause of a sentence, and `split_clauses` calls it to judge whether
    text so far is a complete command. It never mutates state.

    Keyword checks are only a routing hint: a parser that returns None (the
    clause does not match its grammar) falls through to the next candidate,
    which is why every branch is a match-and-return rather than a shortcut.
    """
    if any(kw in sentence for kw in ORDER_KEYWORDS['halt']):
        order = parse_halt_order(sentence, game_state, player_id)
        if order:
            return order

    # Try each parser based on keywords (optimization)
    if any(kw in sentence for kw in ORDER_KEYWORDS['move']):
        order = parse_move_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['sail']):
        order = parse_sail_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['recruit']):
        order = parse_recruit_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['buy']):
        order = parse_buy_ship_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['attack']):
        order = parse_attack_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['teleport']):
        order = parse_teleport_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['fly']):
        order = parse_fly_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['heal']):
        order = parse_heal_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['pray']):
        order = parse_pray_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['bless']):
        order = parse_bless_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['curse']):
        order = parse_curse_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['resurrect']):
        order = parse_resurrect_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['secure']):
        order = parse_secure_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['fortify']):
        order = parse_fortify_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['unfortify']):
        order = parse_unfortify_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['ally']):
        order = parse_ally_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['enemy']):
        order = parse_enemy_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['neutral']):
        order = parse_neutral_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['assign']):
        order = parse_assign_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['name']):
        order = parse_name_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['promote']):
        order = parse_promote_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['tax']):
        order = parse_tax_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['trade']):
        order = parse_trade_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['await']):
        order = parse_await_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['repeat']):
        order = parse_repeat_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['scry']):
        order = parse_scry_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['capture']):
        order = parse_capture_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['free']):
        order = parse_free_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['study']):
        order = parse_study_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['teach']):
        order = parse_teach_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['summon']):
        order = parse_summon_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['collect']):
        order = parse_collect_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['build']):
        order = parse_build_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['mine']):
        order = parse_mine_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['kill']):
        order = parse_kill_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['enslave']):
        order = parse_enslave_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['interrogate']):
        order = parse_interrogate_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['noncom']):
        order = parse_noncom_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['lurk']):
        order = parse_lurk_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['probe']):
        order = parse_probe_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['search']):
        order = parse_search_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['scan']):
        order = parse_scan_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['password']):
        order = parse_password_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['address']):
        order = parse_address_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['message']):
        order = parse_message_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['post']):
        order = parse_post_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['report']):
        order = parse_report_order(sentence, game_state, player_id)
        if order:
            return order

    # conjure before charge: "a wand of conjuring" would otherwise be read
    # as a CHARGE by the bare substring test below.
    if any(kw in sentence for kw in ORDER_KEYWORDS['conjure']):
        order = parse_conjure_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['charge']):
        order = parse_charge_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['absorb']):
        order = parse_absorb_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['get']):
        order = parse_get_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['transfer']):
        order = parse_transfer_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['unload']):
        order = parse_unload_order(sentence, game_state, player_id)
        if order:
            return order

    # repay before pay: "repay" contains the substring "pay"
    if any(kw in sentence for kw in ORDER_KEYWORDS['repay']):
        order = parse_repay_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['borrow']):
        order = parse_borrow_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['pay']):
        order = parse_pay_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['join']):
        order = parse_join_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['support']):
        order = parse_support_order(sentence, game_state, player_id)
        if order:
            return order

    # "Buy passage to Kitesta": the buy branch above already tried and failed
    # (a passage order names no galley), so the passage branch can be last.
    if any(kw in sentence for kw in ORDER_KEYWORDS['passage']):
        order = parse_passage_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['work']):
        order = parse_work_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['train']):
        order = parse_train_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['unname']):
        order = parse_unname_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['create']):
        order = parse_create_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['invest']):
        order = parse_invest_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['offer']):
        order = parse_offer_order(sentence, game_state, player_id)
        if order:
            return order

    if any(kw in sentence for kw in ORDER_KEYWORDS['preach']):
        order = parse_preach_order(sentence, game_state, player_id)
        if order:
            return order

    return None


def parse_orders(raw_text: str, game_state: GameState, player_id: str) -> list[Order]:
    """
    Parse raw order text into a list of Order objects.

    This is the main entry point for order parsing. It can be replaced
    with an LLM-based implementation that has the same signature.

    `repeatedly` is an adverb rather than a verb, so it is lifted off its
    clause before the verb dispatch below and emitted as its own REPEAT order
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
    # Quoted message bodies come out before anything touches the text, and go
    # back into the finished orders at the end.
    protected, quoted = protect_quotes(raw_text)
    normalized = normalize_text(protected)
    sentences = extract_sentences(normalized)

    # Pronoun referents carry from one sentence to the next within a single
    # submission, which is what the rules' own examples need: "Have Mark Bolton
    # study combat. Have Donald Nap go to Madegi Doy and give him 100 gold."
    referents = pronouns.ReferentContext()

    for sentence in sentences:
        if not sentence:
            continue

        # Every pronoun becomes the name it stands for before clause
        # splitting, so no verb parser below has to know pronouns exist.
        sentence = pronouns.resolve(sentence, referents, game_state, player_id)

        # IF statements govern the rest of their sentence, so the head (which
        # parses as ordinary chained commands) is split off before the `if`.
        if_match = re.search(r'(?:^|\s+)if\s+', sentence)
        head = sentence[:if_match.start()].strip() if if_match else sentence
        if_tail = sentence[if_match.start():].strip() if if_match else ""

        # `and` joins whole commands as well as items, so one sentence can
        # carry several orders: "Assign 20 soldiers and 23 horses to Bill
        # Jenkins, and have him go to Riverton and attack Mike May" is three.
        clauses = split_clauses(head, game_state, player_id)

        # The HAVE form hands its command to a named character, and the
        # character stays the actor of the chained commands that follow it:
        # "have him go to Riverton and tax for 3 weeks, and go to Ennistown
        # and tax" is four orders, all to the same character.
        have_target = ""
        prev_verb = ""

        for clause in clauses:
            clause = clause.strip()
            if not clause:
                continue

            # `then` sequencing ("wait for 2 weeks and then go to Salem") is
            # a clause boundary; the queue behind a wait already holds the
            # rest, so the marker itself can go.
            clause = re.sub(r'^then\s+', '', clause)

            if clause.startswith("have "):
                have_target = _have_target(clause)
            elif _leading_verb(clause):
                if have_target:
                    clause = f"have {have_target} {clause}"
            else:
                # Verb elision: "give 50 gold to Nancy Myers and 20 horses to
                # Bill Fenton" is two GIVE orders; "charge Ampu to 75 power
                # and Wasute by 7 power" is one CHARGE with both items (the
                # CHARGE parser reads the list itself), and the counted
                # continuation of a recruit ("recruit 5 soldiers and 3
                # workers") is a second RECRUIT.
                if prev_verb:
                    prefix = f"have {have_target} " if have_target else ""
                    clause = f"{prefix}{prev_verb} {clause}"

            clause_original = clause
            clause, repeat_times = strip_repeatedly(clause)

            order = _dispatch_clause(clause, game_state, player_id)
            verb = _leading_verb(clause_original)
            if verb:
                prev_verb = verb

            if order:
                # rules.md's HAVE form delegates to a named character, and
                # that makes them a group leader. Not every parser routes
                # through resolve_actor, so the delegation is recognised
                # centrally here.
                if HAVE_PREFIX.match(clause_original):
                    order.explicit_actor = True

                if repeat_times is not None:
                    # The loop marker takes the same actor as the command it
                    # governs, so the two can never drift apart.
                    orders.append(RepeatOrder(
                        player_id=player_id,
                        original_text=clause_original,
                        actor_id=getattr(order, 'actor_id', ''),
                        times=repeat_times,
                    ))
                orders.append(order)
            else:
                # Unparseable order - create placeholder with warning
                generic_order = MoveOrder(
                    player_id=player_id, original_text=clause)
                generic_order.warnings.append(
                    f"Could not parse order: '{clause}'")
                orders.append(generic_order)

        if if_tail:
            if_order = parse_if_order(if_tail, game_state, player_id)
            if if_order:
                orders.append(if_order)

    # Put the players' own words back where the placeholders stand.
    for order in orders:
        restore_order_quotes(order, quoted)

    return orders
