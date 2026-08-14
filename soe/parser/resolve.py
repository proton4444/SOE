"""Entity resolution and shared order-parser base class."""

from __future__ import annotations

from typing import Optional, Type, TypeVar
from dataclasses import dataclass

from soe.models import GameState, Character, TITLE_WORDS
from soe.orders import MoveOrder, Order
from soe.fog import parse_position_prefix

#: Preserves the concrete order subclass through ``create_order`` and
#: ``add_warning``, so a parser that returns ``Optional[NameOrder]`` keeps
#: seeing a ``NameOrder`` and its fields.
OrderT = TypeVar('OrderT', bound=Order)


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
            without_title = strip_leading_title(name_text, game_state)
            if without_title:
                char = game_state.get_character_by_name(without_title)
        if char and _is_npc(char, game_state):
            return ResolvedEntity(char.id, char.name)
        if not enemy_ok:
            return ResolvedEntity("", name_text, found=False)

    # Search all factions (targets, or no issuing player given)
    char = game_state.get_character_by_name(name_text)
    if char:
        return ResolvedEntity(char.id, char.name)

    # A title is ignored on a target too, so "attack Wizard Yemishoka" and
    # "attack Regent Aurelia" find the same people the player's own orders do.
    without_title = strip_leading_title(name_text, game_state)
    if without_title:
        char = game_state.get_character_by_name(without_title)
        if char:
            return ResolvedEntity(char.id, char.name)

    return ResolvedEntity("", name_text, found=False)


def _is_npc(char: Character, game_state: GameState) -> bool:
    """True when the character belongs to a computer-controlled faction."""
    faction = game_state.factions.get(char.faction_id)
    return bool(faction and faction.is_npc)


# Design: "Titles are ignored except in the NAME and PROMOTE commands, where
# they are mandatory." A player writes "Assign 200 soldiers to Captain Bill
# Jones" and means Bill Jones, so a leading title word is dropped before the
# name lookup.
def strip_leading_title(name_text: str, game_state: Optional[GameState] = None) -> str:
    """
    `name_text` without its leading title word, or "" when it has none.

    TITLE_WORDS holds the standard ranks. PROMOTE, though, lets a player invent
    a title ("Promote Aurelia to Regent"), so a word actually worn as a title
    somewhere in this game counts as well -- otherwise "attack Regent Aurelia"
    goes looking for a character of that full name and quietly finds nobody.
    """
    words = name_text.split()
    if len(words) < 2:
        return ""
    first = words[0].lower()
    if first in TITLE_WORDS:
        return " ".join(words[1:])
    if game_state and any(
            first in char.title.lower().split()
            for char in game_state.characters.values() if char.title):
        return " ".join(words[1:])
    return ""


def _match_without_title(name_text: str, game_state: GameState,
                         player_id: str) -> Optional[Character]:
    """A character whose name follows a leading title word."""
    without_title = strip_leading_title(name_text, game_state)
    if not without_title:
        return None
    return game_state.get_character_by_name(without_title, faction_id=player_id)


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

    def create_order(self, order_class: Type[OrderT]) -> OrderT:
        """Create an order instance with base attributes."""
        return order_class(player_id=self.player_id, original_text=self.original_text)

    def add_warning(self, order: OrderT, message: str) -> OrderT:
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
            # Explicit actor name -- the HAVE form. the design makes that
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

    def resolve_leader_id(self, order: Order) -> Optional[str]:
        """
        Return the faction leader's id, warning on the order if there is none.

        For orders that name their actor with a field of their own --
        ``teacher_id``, ``summoner_id`` -- instead of ``actor_id``.

        Returns:
            The leader's character ID, or None if the faction has no leader
        """
        leader = get_player_leader(self.game_state, self.player_id)
        if not leader:
            self.add_warning(order, "No leader character found")
            return None
        return leader.id

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

        Note:
            `order.city_implicit` records that the player named no city. The
            parse-time fill is then only a default: the order was written about
            wherever the character turns out to be standing, and a MOVE earlier
            in the same sentence has not happened yet. Execution re-reads the
            actor's location in that case.
        """
        order.city_implicit = not city_name
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
    Resolve "outside Ashford" / "near Redport" / "Rome" onto a MoveOrder.

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

