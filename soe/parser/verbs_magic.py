"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from soe.models import (
    GameState,
)
from soe.orders import (
    Order, HealOrder,
    StudyOrder, TeachOrder,
    SummonOrder, PrayOrder, BlessOrder, CurseOrder, ResurrectOrder,
    ScryOrder, ProbeOrder, SearchOrder, ScanOrder,
    ConjureOrder, ChargeOrder, AbsorbOrder, ItemPowerTransfer,
)
from soe import items
from soe.parser.text import (
    strip_wand,
)
from soe.parser.resolve import (
    resolve_character, resolve_city, OrderParserBase,
)


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

    # An orb is named by a trailing `using`/`with` clause. The design also allows
    # pairing several city groups with several orbs in one sentence ("scan
    # Thornwick and Ironvale using Sarema and Velika using Doramba"); that form
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

