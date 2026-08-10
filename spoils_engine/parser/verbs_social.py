"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from spoils_engine.models import (
    GameState,
)
from spoils_engine.orders import (
    SecureOrder, FortifyOrder, UnfortifyOrder, AllyOrder, EnemyOrder,
    NeutralOrder, MessageOrder, PostOrder, ReportOrder, AddressOrder, PasswordOrder,
    JoinOrder, SupportOrder,
    PreachOrder, OfferOrder,
)
from spoils_engine import config
from spoils_engine.parser.text import (
    _strip_clause_adverbs,
    parse_duration_days, _QUOTE_TOKEN_RE,
)
from spoils_engine.parser.resolve import (
    resolve_character, resolve_city, OrderParserBase,
)


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

def _split_swallowed_command(part: str) -> tuple[str, str]:
    """
    Split a recipient phrase where the next order ran into it.

    SAY names its recipient last -- `say "..." to <who>` -- so the name runs to
    the end of the sentence. Leave the period off and the following command
    lands inside it: "Say "Ready" to Aurelia" then "Report" arrives as one
    recipient called `aurelia report`. rules.md recovers from a parse error by
    ignoring input to the next period, so the swallowed command is not obeyed;
    the player has to be told which words went missing, or the lost order is
    invisible. Returns (recipient, swallowed text), the latter "" when the
    phrase does not run into a command word.
    """
    # Lazy import: dispatch imports this module.
    from spoils_engine.parser.dispatch import _COMMAND_VERBS

    words = part.split()
    for index in range(1, len(words)):
        if words[index] in _COMMAND_VERBS:
            return " ".join(words[:index]), " ".join(words[index:])
    return part, ""


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
        if not _resolve_one_recipient(part, order, game_state, parser):
            # Only once the whole phrase has failed is a command word inside it
            # blamed, so a recipient whose name happens to contain one is safe.
            head, swallowed = _split_swallowed_command(part)
            if swallowed and _resolve_one_recipient(head, order, game_state,
                                                    parser):
                parser.add_warning(
                    order,
                    f"'{swallowed}' ran into the recipient and was ignored — "
                    f"put a period after '{head}' to start a new order")
            else:
                parser.add_warning(order, f"No character or town called '{part}'")


def _resolve_one_recipient(part: str, order, game_state: GameState,
                           parser: "OrderParserBase") -> bool:
    """Record one addressee. Returns False when the name matches nothing."""
    if part == "everyone":
        order.to_everyone = True
        return True

    city = resolve_city(part, game_state)
    if city.found:
        order.recipient_city_id = city.entity_id
        order.recipient_city_name = city.entity_name
        return True

    # enemy_ok: a message is not an order, so it may name anybody.
    person = resolve_character(part, game_state, parser.player_id, enemy_ok=True)
    if not person.found:
        return False
    order.recipient_ids.append(person.entity_id)
    order.recipient_names.append(person.entity_name)
    return True


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

