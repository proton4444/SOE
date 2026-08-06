"""
Pronoun resolution for order text.

`rules.md` devotes a section to pronouns because terse orders need them:
"Have Donald Nap go to Madegi Doy and give him 100 gold" is how a player
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

Referents carry from one sentence to the next, which is what the rules'
own examples require:

    Have Mark Bolton study combat for 4 weeks.
    Have Donald Nap go to Madegi Doy and give him 100 gold.

`him` is Mark Bolton -- not Donald Nap, who is the agent of his own order.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from spoils_engine.models import Character, GameState


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

# rules.md: "you must use it when referring to more than one unit of
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

    def remember_person(self, name: str, gender: str) -> None:
        """Record a named person as the newest candidate for him or her."""
        history = self.female_history if gender == "female" else self.male_history
        if name in history:
            history.remove(name)
        history.append(name)

    def gendered(self, gender: str, excluded: tuple[str, ...]) -> str:
        """
        The most recently named person of this gender who is allowed here.

        rules.md bars the agent of the current order and the player's leader,
        so those are passed in and skipped over rather than blocking the
        pronoun entirely.
        """
        history = self.female_history if gender == "female" else self.male_history
        for name in reversed(history):
            if name not in excluded:
                return name
        return ""


def _word(pattern: str) -> re.Pattern:
    """Compile a whole-word pattern, so `me` never matches inside `mine`."""
    return re.compile(rf"\b(?:{pattern})\b")


_LEADER_RE = _word("|".join(LEADER_PRONOUNS))
_REFLEXIVE_RE = _word("|".join(REFLEXIVE_PRONOUNS))
_HIM_RE = _word("him")
_HER_RE = _word("her")
_IT_RE = _word("it")
_THEM_RE = _word("them")

_COUNTED_RE = re.compile(
    rf"\b(\d+)\s+({'|'.join(COUNTABLE_NOUNS)})s?\b")
_MASS_RE = re.compile(
    rf"\b(\d+)\s+({'|'.join(MASS_NOUNS)})\b")


# ============================================================================
# FINDING THE AGENT
# ============================================================================

def find_agent(sentence: str, game_state: GameState,
               player_id: str) -> Optional[Character]:
    """
    The character acting in this sentence.

    rules.md: "The agent of an order is the name following have (or your lead
    character if have is not used)." The name is matched against the player's
    real characters rather than guessed from the grammar, so a two-word name
    like "Joe Flint" is found whole.
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
    "Joe Flint" must not race.
    """
    candidates = [c for c in game_state.characters.values()
                  if c.faction_id == player_id]
    for char in sorted(candidates, key=lambda c: -len(c.name)):
        if text.startswith(char.name.lower()):
            return char
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

    # Reflexives first: `himself` contains `him`, so resolving `him` ahead of
    # it would corrupt the word.
    if agent:
        sentence = _REFLEXIVE_RE.sub(agent.name.lower(), sentence)

    if context.leader_name:
        sentence = _LEADER_RE.sub(context.leader_name, sentence)

    # him / her never mean the agent and never mean the leader, so the context
    # is consulted only after those two are excluded.
    agent_name = agent.name.lower() if agent else ""
    barred = (agent_name, context.leader_name)
    for pattern, gender in ((_HIM_RE, "male"), (_HER_RE, "female")):
        referent = context.gendered(gender, barred)
        if referent:
            sentence = pattern.sub(referent, sentence)

    if context.last_singular:
        sentence = _IT_RE.sub(context.last_singular, sentence)
    if context.last_plural:
        sentence = _THEM_RE.sub(context.last_plural, sentence)

    _remember(sentence, context, game_state, player_id, agent_name)
    return sentence


def _remember(sentence: str, context: ReferentContext, game_state: GameState,
              player_id: str, agent_name: str) -> None:
    """
    Record what this sentence named, for the pronouns that follow it.

    "Most recently named" is read as last by position in the sentence, and a
    name that sits in a longer list of people and things is skipped: rules.md
    rules out "Doctor McCoy" as a referent in "Assign 10 soldiers and Doctor
    McCoy to Joe Flint" precisely because he is linked to the soldiers.
    """
    _remember_people(sentence, context, game_state, player_id, agent_name)
    _remember_things(sentence, context, game_state)


def _remember_people(sentence: str, context: ReferentContext,
                     game_state: GameState, player_id: str,
                     agent_name: str) -> None:
    """
    Update the him/her referents from the characters this sentence names.

    The agent of *this* sentence is still recorded: rules.md only bars them
    from being the referent of a pronoun in their own order, and the very next
    sentence may well say "have him go to Tashendi" meaning exactly them. The
    leader is dropped for good, since him and her never mean the leader.
    """
    listed = _listed_spans(sentence)

    mentions: list[tuple[int, Character]] = []
    for char in game_state.characters.values():
        name = char.name.lower()
        for match in re.finditer(rf"\b{re.escape(name)}\b", sentence):
            mentions.append((match.start(), char))

    for position, char in sorted(mentions, key=lambda m: m[0]):
        name = char.name.lower()
        if name == context.leader_name:
            continue
        # A name inside an enumeration is "part of a longer list of people
        # and/or items" and cannot be what him or her refers to.
        if any(start <= position < end for start, end in listed):
            continue
        context.remember_person(name, char.gender)

    # A run of people joined by `and` is what `them` refers to.
    group = _people_list(sentence, game_state, player_id)
    if group:
        context.last_plural = group


def _remember_things(sentence: str, context: ReferentContext,
                     game_state: GameState) -> None:
    """Update the it/them referents from the goods this sentence names."""
    # A magical item named in the order is a single thing: `it`.
    for item in game_state.magical_items.values():
        bare = item.name.strip("*").lower()
        if re.search(rf"\*?{re.escape(bare)}\*?", sentence):
            context.last_singular = item.name.lower()

    # Mass nouns take `it` however many there are; countables split on one.
    for match in _MASS_RE.finditer(sentence):
        context.last_singular = match.group(0)
    for match in _COUNTED_RE.finditer(sentence):
        if int(match.group(1)) == 1:
            context.last_singular = match.group(0)
        else:
            context.last_plural = match.group(0)


# An enumeration runs until a preposition hands the list to somebody.
_LIST_TAIL = r"(?=\s+(?:to|from|for|with|using|at|into|in|and\s+have)\b|$)"


def _listed_spans(sentence: str) -> list[tuple[int, int]]:
    """
    Spans of the sentence that enumerate several things joined by `and`.

    A person inside one of these is "part of a longer list of people and/or
    items" and so cannot be the referent of him or her. In "assign 10 soldiers
    and Doctor McCoy to Joe Flint" the enumeration is "10 soldiers and Doctor
    McCoy": it stops at `to`, which is why Joe Flint stays a candidate and
    McCoy does not.
    """
    nouns = "|".join(COUNTABLE_NOUNS + MASS_NOUNS)
    pattern = rf"\b\d+\s+(?:{nouns})s?(?:\s+and\s+.+?)?{_LIST_TAIL}"
    return [(m.start(), m.end()) for m in re.finditer(pattern, sentence)]


def _people_list(sentence: str, game_state: GameState,
                 player_id: str) -> str:
    """
    The text of a run of two or more of the player's characters joined by `and`.

    rules.md: "them" may refer to "the most recently mentioned group of agents
    who are not the agents of the current command", as in "Have Joe Flint and
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
