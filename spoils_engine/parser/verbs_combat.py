"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from spoils_engine.models import (
    GameState,
)
from spoils_engine.orders import (
    AttackOrder,
    CaptureOrder, FreeOrder, KillOrder, EnslaveOrder, InterrogateOrder,
    NoncomOrder, LurkOrder,
)
from spoils_engine.parser.resolve import (
    resolve_character, resolve_city, get_player_leader,
    OrderParserBase,
)


# rules.md's ATTACK takes a character name and nothing else. The battle happens
# where the attacker already stands, and a location is reached with GO in the
# same sentence -- "have him go to Kitesta and attack John May". So a trailing
# "in Kitesta" is not a target qualifier, and folding it into the name sends the
# parser hunting for a character called "Regent Aurelia in Kitesta": the order
# is accepted, no such person exists, and the attack silently never happens.
_ATTACK_LOCATION_TAIL = re.compile(r'^(.+?)\s+(?:in|at|near|outside)\s+(.+)$')


def _resolve_attack_target(order: AttackOrder, parser: OrderParserBase,
                           target_name: str, game_state: GameState) -> None:
    """
    Bind an ATTACK to the character the player named, or say why it cannot.

    The whole phrase is tried as a name first, so a character whose name really
    does contain `in` or `at` is still reachable. Only when that fails is a
    trailing location blamed, and only when it names a city that exists.
    """
    order.target_name = target_name

    resolved = resolve_character(target_name, game_state, None)
    if resolved.found:
        target_char = game_state.characters.get(resolved.entity_id)
        if target_char:
            order.target_faction_id = target_char.faction_id
            order.target_character_id = target_char.id
            order.target_name = target_char.name
        return

    match = _ATTACK_LOCATION_TAIL.match(target_name)
    if match and resolve_city(match.group(2).strip(), game_state).found:
        person, place = match.group(1).strip(), match.group(2).strip()
        parser.add_warning(
            order,
            f"ATTACK takes only a name and is fought where the attacker "
            f"stands, so '{target_name}' was read as a name and nobody is "
            f"called that. Write 'go to {place} and attack {person}' instead.")
        return

    parser.add_warning(order, f"No character named '{target_name}' was found to attack")


def parse_attack_order(sentence: str, game_state: GameState, player_id: str) -> Optional[AttackOrder]:
    """Parse an attack order."""
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(AttackOrder)
    order.definitely = bool(re.search(r'\bdefinitely\b', sentence))
    for stance in ("cravenly", "cautiously", "bravely", "recklessly", "suicidally"):
        if re.search(rf'\b{stance}\b', sentence):
            order.stance = stance
            break
    sentence = re.sub(
        r'\b(?:definitely|cravenly|cautiously|bravely|recklessly|suicidally)\b',
        ' ', sentence,
    )
    sentence = ' '.join(sentence.split())

    # Pattern: "have <name> [go to <city> and] attack <target>"
    match = re.search(r'have\s+(.+?)\s+(?:go\s+to\s+(.+?)\s+and\s+)?attack\s+(.+)', sentence)
    if match:
        actor_name = match.group(1).strip()
        city_name = match.group(2).strip() if match.group(2) else None
        target_name = match.group(3).strip()

        if not parser.resolve_actor(order, actor_name):
            return order

        _resolve_attack_target(order, parser, target_name, game_state)

        # The GO in "go to Kitesta and attack" is what puts the attacker there,
        # and it runs in the movement phase before combat. Recording the city
        # keeps the order readable, but process_combat fights the battle where
        # the attacker actually ends up -- if the march failed, so does this.
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

        _resolve_attack_target(order, parser, target_name, game_state)

        # A default only: process_combat re-reads the attacker's location.
        leader = get_player_leader(game_state, player_id)
        if leader:
            order.location_city_id = leader.location_city_id

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

