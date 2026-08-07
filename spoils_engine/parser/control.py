"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from spoils_engine.models import (
    GameState,
)
from spoils_engine.orders import (
    Order, AwaitOrder,
    RepeatOrder, HaltOrder, StopOrder, IfOrder,
)
from spoils_engine import config
from spoils_engine.parser.text import (
    parse_duration_days,
)
from spoils_engine.parser.resolve import (
    resolve_character, OrderParserBase,
)

# _parse_clause_body lazy-imports dispatch (breaks cycle)


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
    # Lazy import: dispatch imports control; body needs dispatch helpers.
    from spoils_engine.parser.dispatch import (
        split_clauses, _dispatch_clause, _have_target, _leading_verb,
    )
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

