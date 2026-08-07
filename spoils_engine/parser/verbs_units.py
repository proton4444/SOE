"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from spoils_engine.models import (
    GameState,
)
from spoils_engine.orders import (
    AssignOrder, NameOrder,
    PromoteOrder, GetOrder, TransferOrder, UnloadOrder, PayOrder, BorrowOrder, RepayOrder,
    UnnameOrder, CreateOrder,
)
from spoils_engine import items
from spoils_engine.parser.text import (
    _strip_clause_adverbs,
)
from spoils_engine.parser.resolve import (
    resolve_character, get_player_leader,
    OrderParserBase,
)


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

