"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from spoils_engine.models import (
    GameState, UnitType, ShipType,
)
from spoils_engine.orders import (
    RecruitOrder, BuyShipOrder, TaxOrder, CollectOrder,
    BuildOrder, MineOrder, TradeOrder, WorkOrder, TrainOrder, InvestOrder,
)
from spoils_engine import config
from spoils_engine.parser.text import (
    _strip_clause_adverbs,
    parse_duration_days,
)
from spoils_engine.parser.resolve import (
    resolve_character, resolve_city, OrderParserBase,
)


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

        # Only ship types belong here; resource buys fall through to TRADE
        # ("Buy 10 wood", "Have X purchase 5 stone").
        if ship_type not in [st.value for st in ShipType]:
            return None

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

        if ship_type not in [st.value for st in ShipType]:
            return None

        if not parser.resolve_actor(order, None):  # Use leader
            return order

        order.count = count
        order.ship_type = ship_type

        if not parser.resolve_location(order, city_name):
            return order

        return order

    return None

# A city named after TAX, with or without a preposition: "tax Kitesta",
# "tax in Kitesta", "tax for 2 weeks in Kitesta".
_TAX_PLACE = re.compile(r'\btax\b(?:\s+for\s+\d+\s+\w+)?(?:\s+(?:in|at|from))?\s+(.+?)\s*$')


def _tax_named_city(sentence: str, game_state: GameState) -> Optional[str]:
    """
    The city a TAX order names, if it names one that exists.

    rules.md: "A character that is given a TAX command will attempt to collect
    taxes in his current location." TAX has no location argument, so the parser
    used to drop the words after it -- and "tax Kitesta" became a tax on
    whichever town the character had actually reached. Nothing here changes
    where taxes come from; the named city is kept so execution can check it
    against where the character is standing, and refuse rather than quietly
    tax somewhere else.

    Anything that is not a known city is left alone, so wordings the parser
    already tolerated keep working.
    """
    match = _TAX_PLACE.search(sentence)
    if not match:
        return None
    resolved = resolve_city(match.group(1).strip(), game_state)
    return resolved.entity_id if resolved.found else None


def parse_tax_order(sentence: str, game_state: GameState, player_id: str) -> Optional[TaxOrder]:
    """
    Parse a TAX order.

    Examples:
        - "tax"
        - "tax for 2 weeks"
        - "have Captain Jones tax for 14 days"
        - "tax Kitesta" / "tax in Kitesta" (checked against where the actor is)
    """
    parser = OrderParserBase(game_state, player_id, sentence)
    order = parser.create_order(TaxOrder)

    named_city = _tax_named_city(sentence, game_state)
    if named_city:
        order.stated_city_id = named_city

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

