"""Order-language parsers — extracted from parser without behavior change."""

from __future__ import annotations

import re
from typing import Optional

from spoils_engine.models import (
    GameState,
)
from spoils_engine.orders import (
    Order, MoveOrder, RepeatOrder,
)
from spoils_engine import pronouns
from spoils_engine.parser.text import (
    normalize_text, extract_sentences, protect_quotes, restore_order_quotes, strip_repeatedly,
)

from spoils_engine.parser.verbs_movement import (
    parse_move_order, parse_sail_order, parse_fly_order, parse_teleport_order,
    parse_passage_order,
)
from spoils_engine.parser.verbs_combat import (
    parse_attack_order, parse_capture_order, parse_free_order,
    parse_kill_order, parse_enslave_order, parse_interrogate_order,
    parse_noncom_order, parse_lurk_order,
)
from spoils_engine.parser.verbs_economy import (
    parse_recruit_order, parse_buy_ship_order, parse_tax_order, parse_trade_order,
    parse_collect_order, parse_build_order, parse_mine_order,
    parse_work_order, parse_train_order, parse_invest_order,
)
from spoils_engine.parser.verbs_magic import (
    parse_heal_order, parse_pray_order, parse_bless_order, parse_curse_order,
    parse_resurrect_order, parse_summon_order, parse_study_order, parse_teach_order,
    parse_scry_order, parse_probe_order, parse_search_order, parse_scan_order,
    parse_conjure_order, parse_charge_order, parse_absorb_order,
)
from spoils_engine.parser.verbs_social import (
    parse_secure_order, parse_fortify_order, parse_unfortify_order,
    parse_ally_order, parse_enemy_order, parse_neutral_order,
    parse_preach_order, parse_offer_order,
    parse_join_order, parse_support_order,
    parse_message_order, parse_post_order, parse_report_order,
    parse_address_order, parse_password_order,
)
from spoils_engine.parser.verbs_units import (
    parse_assign_order, parse_name_order, parse_promote_order,
    parse_get_order, parse_transfer_order, parse_unload_order,
    parse_pay_order, parse_borrow_order, parse_repay_order,
    parse_unname_order, parse_create_order,
)
from spoils_engine.parser.control import (
    parse_if_order, parse_await_order, parse_repeat_order, parse_halt_order,
)


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

