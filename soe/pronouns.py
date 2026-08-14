"""
Pronoun resolution for order text.

the design devotes a section to pronouns because terse orders need them:
"Have Donald Nap go to Highfell and give him 100 gold" is how a player
actually writes. The rules fix each pronoun's referent precisely:

- `I`, `me`, `you` always mean your lead character, whoever is acting.
- `him` / `her` mean the most recently named person of that gender who is
  neither the agent of the current order nor your leader.
- `it` means the most recently mentioned single item, unnamed character, or
  quantity of a mass noun (wood, iron, armor -- English demands `it` there
  even for a hundred of them).
- `them` means the most recently mentioned group or list.
- The reflexives (`myself`, `yourself`, `himself`, `herself`, `themselves`)
  mean the agent of the order they appear in.

This runs as a substitution pass over the sentence *before* verb dispatch, so
the thirty-odd verb parsers never see a pronoun and need no knowledge of one.
By the time `parse_orders` hands a sentence to a parser, every pronoun has
become the name it stood for.

Each pronoun binds to what was most recently named *before it* in the
submission, which is what the rules' own chains require:

    Have Mark Bolton study combat for 4 weeks.
    Have Donald Nap go to Highfell and give him 100 gold.

`him` is Mark Bolton -- not Donald Nap, who is the agent of his own order.
And in "have him go to Ashford, and say ... to King Bodo Bunji, and give him
100 gold" the first `him` is the man from the earlier sentence while the
second is the king, because the king was named in between. A pronoun sitting
directly after `have` is the agent of its own command, so the agent exclusion
never applies to it -- only your leader is barred.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from soe.models import Character, GameState


_POSSESSIVE_AFTER_HER = re.compile(
    r"\s+(gold|soldiers?|sailors?|workers?|slaves?|horses?|units?|items?|"
    r"wood|stone|iron|copper|silver|gems?|group|purse|troops?)\b"
)


def _is_independent_npc(char: Character, game_state: GameState) -> bool:
    faction = game_state.factions.get(char.faction_id)
    return bool(faction and faction.is_npc)


# `I` is included even though orders are lowercased before this runs.
LEADER_PRONOUNS = ("i", "me", "you")
REFLEXIVE_PRONOUNS = ("myself", "yourself", "himself", "herself",
                      "themselves", "itself")

# Nouns an order can count. Anything here can become the referent of `it` (one
# of them) or `them` (several).
COUNTABLE_NOUNS = (
    "soldier", "sailor", "worker", "slave",
    "galley", "ship", "catapult", "weapon", "horse",
)

# Design: "you must use it when referring to more than one unit of
# substances (i.e. mass nouns) such as wood, iron, or armor". These take `it`
# however many there are.
MASS_NOUNS = (
    "wood", "stone", "iron", "gold", "silver", "copper", "gems", "armor",
)


@dataclass
class ReferentContext:
    """
    What each pronoun currently stands for.

    One of these lives for the length of a single player's submission, so a
    pronoun can look back to an earlier sentence. Everything is stored as the
    *text* to substitute in, because resolution happens before parsing and the
    verb parsers work on text.

    People are kept as a history rather than a single name because the
    exclusions are per sentence: someone barred from being `him` in the
    sentence where they are the agent is a perfectly good `him` in the next
    one. The history is oldest-first, so resolution walks it backwards to find
    the most recent name that is allowed here.
    """
    leader_name: str = ""
    male_history: list[str] = field(default_factory=list)    # -> him
    female_history: list[str] = field(default_factory=list)  # -> her
    last_singular: str = ""                                  # -> it
    last_plural: str = ""                                    # -> them


def _word(pattern: str) -> re.Pattern:
    """Compile a whole-word pattern, so `me` never matches inside `mine`."""
    return re.compile(rf"\b(?:{pattern})\b")


_LEADER_RE = _word("|".join(LEADER_PRONOUNS))
_REFLEXIVE_RE = _word("|".join(REFLEXIVE_PRONOUNS))
_IT_THEM_RE = _word(r"(?:it|them)")

# Bare mass nouns ("gather stone", "collect wood") still give `it` something
# to stand for: `it` refers to whatever was successfully collected.
_BARE_MASS_RE = re.compile(rf"\b(?:{'|'.join(MASS_NOUNS)})\b")

# Any counted thing and the `and`-run that may follow it, used by the
# position-aware it/them scan below.
_THING_ITEM_RE = re.compile(
    rf"\d+\s+(?:{'|'.join(COUNTABLE_NOUNS + MASS_NOUNS)})s?")
_THING_RUN_RE = re.compile(
    rf"\s+and\s+\d+\s+(?:{'|'.join(COUNTABLE_NOUNS + MASS_NOUNS)})s?")
_IT_THEM_RE = _word(r"(?:it|them)")


# ============================================================================
# FINDING THE AGENT
# ============================================================================

def find_agent(sentence: str, game_state: GameState,
               player_id: str) -> Optional[Character]:
    """
    The character acting in this sentence.

    Design: "The agent of an order is the name following have (or your lead
    character if have is not used)." The name is matched against the player's
    real characters rather than guessed from the grammar, so a two-word name
    like "Alan Reed" is found whole.
    """
    match = re.search(r"\bhave\s+(.+)$", sentence)
    if match:
        named = _leading_character(match.group(1), game_state, player_id)
        if named:
            return named
    return player_leader(game_state, player_id)


def _leading_character(text: str, game_state: GameState,
                       player_id: str) -> Optional[Character]:
    """
    The player's character whose name starts `text`, longest name first.

    Longest-first matters when one name is a prefix of another: "Joe" and
    "Alan Reed" must not race.
    """
    candidates = [c for c in game_state.characters.values()
                  if c.faction_id == player_id or _is_independent_npc(c, game_state)]
    for char in sorted(candidates, key=lambda c: -len(c.name)):
        if text.startswith(char.name.lower()):
            return char
    # A leading title ("have Captain Jane Tucker go to Ashford") is ignored
    # in orders; the name is what follows it.
    from soe.models import TITLE_WORDS
    words = text.split()
    if words and words[0] in TITLE_WORDS:
        return _leading_character(" ".join(words[1:]), game_state, player_id)
    return None


def player_leader(game_state: GameState, player_id: str) -> Optional[Character]:
    """The faction's lead character, who `me`, `I` and `you` always mean."""
    for char in game_state.characters.values():
        if char.faction_id == player_id and char.is_leader:
            return char
    return None


# ============================================================================
# RESOLUTION
# ============================================================================

def resolve(sentence: str, context: ReferentContext, game_state: GameState,
            player_id: str) -> str:
    """
    Replace every pronoun in one sentence with what it stands for.

    Returns the rewritten sentence, and updates `context` with the referents
    this sentence establishes for the sentences after it. A pronoun with no
    referent is left alone: the verb parser will then fail to resolve it and
    report an honest "not found" naming the pronoun, which beats silently
    binding the order to the wrong character.
    """
    agent = find_agent(sentence, game_state, player_id)
    leader = player_leader(game_state, player_id)
    if leader:
        context.leader_name = leader.name.lower()

    # Referents are remembered before substitution so that a pronoun can bind
    # to a name named earlier in the *same* sentence. The rules' own example
    # needs it: "Have Alan Reed give 10 horses to Billy Jones and have him go
    # to Highfell" resolves `him` to Alan Reed, who is named in the very
    # sentence that contains the pronoun. Remembering reads names and
    # quantities only, never pronouns, so the order is safe.
    agent_name = agent.name.lower() if agent else ""
    group = _people_list(sentence, game_state, player_id)

    # Reflexives first: `himself` contains `him`, so resolving `him` ahead of
    # it would corrupt the word.
    if agent:
        sentence = _REFLEXIVE_RE.sub(agent.name.lower(), sentence)

    if context.leader_name:
        sentence = _LEADER_RE.sub(context.leader_name, sentence)

    sentence = _resolve_him_her(sentence, context, game_state, player_id,
                                agent_name)

    return _resolve_it_them(sentence, context, game_state, group)


def _resolve_him_her(sentence: str, context: ReferentContext,
                     game_state: GameState, player_id: str,
                     agent_name: str) -> str:
    """
    Substitute `him` and `her`, each at its own position in the sentence.

    A pronoun binds to the most recently named person of its gender before it
    in the sentence, which is how the rules' own chains read: "Have him go to
    Ashford, and say ... to King Bodo Bunji, and give him 100 gold" makes the
    first `him` the man from the earlier sentence and the second `him` the
    king, because the king was named in between.

    A pronoun sitting directly after `have` is the agent of its own command,
    so the agent exclusion never applies to it -- "have him go to Velika"
    binds to Alan Reed even though he is the agent of the sentence. An object
    pronoun is never the agent of the sentence and never the leader. The
    histories stay in `context` for the sentences that follow.
    """
    leader = context.leader_name
    listed = _listed_spans(sentence)

    mentions: list[tuple[int, str, str]] = []
    for char in game_state.characters.values():
        name = char.name.lower()
        if name == leader:
            continue
        for match in re.finditer(rf"\b{re.escape(name)}\b", sentence):
            # A name inside an enumeration is "part of a longer list of
            # people and/or items" and cannot be what him or her refers to.
            if any(start <= match.start() < end for start, end in listed):
                continue
            mentions.append((match.start(), char.gender, name))
    mentions.sort()

    male = list(context.male_history)
    female = list(context.female_history)

    def remember(gender: str, name: str) -> None:
        history = female if gender == "female" else male
        if name in history:
            history.remove(name)
        history.append(name)

    def referent(gender: str, barred: tuple[str, ...]) -> str:
        history = female if gender == "female" else male
        for name in reversed(history):
            if name not in barred:
                return name
        return ""

    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\b(?:him|her)\b", sentence):
        while mentions and mentions[0][0] < match.start():
            _, gender, name = mentions.pop(0)
            remember(gender, name)

        # Possessive `her gold` / `her soldiers` is not the object pronoun.
        if match.group(0) == "her" and _POSSESSIVE_AFTER_HER.match(sentence[match.end():]):
            continue

        have_position = bool(re.search(r"\bhave\s+$", sentence[:match.start()]))
        barred = (leader,) if have_position else (agent_name, leader)
        gender = "female" if match.group(0) == "her" else "male"
        name = referent(gender, barred)
        if not name and have_position:
            # A have-position pronoun may look forward: "Purchase 20
            # horses ... and have him go to <city> and assign them to
            # <character>" names its `him` only at the end of the sentence.
            for _, mention_gender, mention in mentions:
                if mention_gender == gender:
                    name = mention
                    break
        if not name:
            continue
        parts.append(sentence[cursor:match.start()] + name)
        cursor = match.end()

    # Mentions after the last pronoun are still the referents the next
    # sentence's pronouns will bind to.
    for _, gender, name in mentions:
        remember(gender, name)

    parts.append(sentence[cursor:])
    context.male_history = male
    context.female_history = female
    return "".join(parts)


def _thing_events(sentence: str,
                  game_state: GameState) -> list[tuple[int, str, str]]:
    """
    Everything in `sentence` that `it` or `them` can stand for, in order.

    Each event is (position, "singular" or "plural", the text to substitute).
    A run of two or more quantities joined by `and` is one plural thing --
    "recruit 5 soldiers and 3 workers" leaves `them` meaning both -- unless a
    quantity of one is mixed in, where the design keeps them apart ("Buy 1
    galley and recruit 40 sailors" still lets `it` mean the galley). A
    magical item named in the order and a bare mass noun ("gather stone")
    are single things.
    """
    events: list[tuple[int, str, str]] = []
    covered = 0

    def run_kind(text: str) -> Optional[tuple[str, str]]:
        """
        (kind, text) for a counted thing or run of things.

        A mass noun takes `it` however many there are ("10 stone and 20
        silver" is still `it`), and a run mixing in any countable is `them`
        ("10 armor and 10 horses" is `them`). A countable quantity of one
        keeps its own pronoun ("1 galley and 40 sailors" leaves `it` the
        galley), which is None here so the singles stay apart.
        """
        items = list(_THING_ITEM_RE.finditer(text))
        mass = "|".join(MASS_NOUNS)
        kinds = []
        for item in items:
            if re.search(rf"(?:{mass})\s*$", item.group(0)):
                kinds.append("mass")
            elif item.group(0).startswith("1 "):
                kinds.append("one")
            else:
                kinds.append("many")
        if all(k == "mass" for k in kinds):
            return ("singular", text)
        if len(items) > 1 and any(k == "one" for k in kinds):
            return None  # a single thing among several keeps its own pronoun
        if any(k == "one" for k in kinds):
            return ("singular", text)
        return ("plural", text)

    for match in _THING_ITEM_RE.finditer(sentence):
        if match.start() < covered:
            continue
        text = match.group(0)
        end = match.end()
        while True:
            run = _THING_RUN_RE.match(sentence, end)
            if not run:
                break
            text += run.group(0)
            end = run.end()
        covered = end

        kind = run_kind(text)
        if kind:
            events.append((match.start(), kind[0], kind[1]))
        else:
            # A single thing among several keeps its own pronoun.
            for inner in _THING_ITEM_RE.finditer(text):
                inner_kind = run_kind(inner.group(0))
                events.append((match.start() + inner.start(),
                               inner_kind[0], inner.group(0)))

    for item in game_state.magical_items.values():
        bare = item.name.strip("*").lower()
        found = re.search(rf"\*?{re.escape(bare)}\*?", sentence)
        if found and found.start() >= covered:
            events.append((found.start(), "singular", item.name.lower()))

    for match in _BARE_MASS_RE.finditer(sentence):
        if match.start() < covered:
            continue
        if re.search(r"\d+\s+$", sentence[max(0, match.start() - 6):match.start()]):
            continue  # quantified above
        events.append((match.start(), "singular", match.group(0)))

    return events


def _resolve_it_them(sentence: str, context: ReferentContext,
                     game_state: GameState, group: str) -> str:
    """
    Substitute `it` and `them`, each at its own position in the sentence.

    A pronoun binds to what was most recently mentioned *before it*, which is
    what the rules' own two-them example needs: "Purchase 20 horses and
    assign them and 2 sailors to Watusingi, and have him go to Highfell and
    assign them to Alan Reed" -- the first `them` is the horses, the second is
    the horses and the sailors. A `them` followed by "and 2 sailors" grows
    into the longer list for the pronouns that come after it. The final
    referents stay in `context` for the next sentence.
    """
    events = sorted(_thing_events(sentence, game_state))
    if group:
        # A run of people is the most recent plural of all.
        events.append((len(sentence), "plural", group))

    last_singular = context.last_singular
    last_plural = context.last_plural
    parts: list[str] = []
    cursor = 0

    for match in _IT_THEM_RE.finditer(sentence):
        while events and events[0][0] < match.start():
            _, kind, text = events.pop(0)
            if kind == "plural":
                last_plural = text
            else:
                last_singular = text

        if match.group(0) == "it":
            if not last_singular:
                continue
            parts.append(sentence[cursor:match.start()] + last_singular)
            cursor = match.end()
            continue

        if not last_plural:
            continue
        parts.append(sentence[cursor:match.start()] + last_plural)
        cursor = match.end()
        run = _THING_RUN_RE.match(sentence, match.end())
        if run:
            # "assign them and 2 sailors": the list grows for later pronouns,
            # and the run's own mentions are part of it.
            last_plural = last_plural + run.group(0)
            while events and events[0][0] < match.end() + len(run.group(0)):
                events.pop(0)

    parts.append(sentence[cursor:])

    # Events after the last pronoun (or, with no pronouns, all of them) are
    # still the referents the next sentence's pronouns will bind to.
    for _, kind, text in events:
        if kind == "plural":
            last_plural = text
        else:
            last_singular = text

    context.last_singular = last_singular
    context.last_plural = last_plural
    return "".join(parts)


# An enumeration runs until a preposition hands the list to somebody.
_LIST_TAIL = r"(?=\s+(?:to|from|for|with|using|at|into|in|and\s+have)\b|$)"


def _listed_spans(sentence: str) -> list[tuple[int, int]]:
    """
    Spans of the sentence that enumerate several things joined by `and`.

    A person inside one of these is "part of a longer list of people and/or
    items" and so cannot be the referent of him or her. In "assign 10 soldiers
    and Doctor McCoy to Alan Reed" the enumeration is "10 soldiers and Doctor
    McCoy": it stops at `to`, which is why Alan Reed stays a candidate and
    McCoy does not.
    """
    nouns = "|".join(COUNTABLE_NOUNS + MASS_NOUNS)
    pattern = rf"\b\d+\s+(?:{nouns})s?(?:\s+and\s+.+?)?{_LIST_TAIL}"
    return [(m.start(), m.end()) for m in re.finditer(pattern, sentence)]


def _people_list(sentence: str, game_state: GameState,
                 player_id: str) -> str:
    """
    The text of a run of two or more of the player's characters joined by `and`.

    Design: "them" may refer to "the most recently mentioned group of agents
    who are not the agents of the current command", as in "Have Alan Reed and
    Mary Wise tax for 4 weeks. ... stop them and assign them to me."
    """
    names = sorted(
        (c.name.lower() for c in game_state.characters.values()
         if c.faction_id == player_id),
        key=len, reverse=True,
    )
    if not names:
        return ""
    alternation = "|".join(re.escape(n) for n in names)
    match = re.search(rf"\b(?:{alternation})(?:\s+and\s+(?:{alternation}))+\b",
                      sentence)
    return match.group(0) if match else ""
