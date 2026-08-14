"""Text normalization and quote / duration helpers for the order parser."""

from __future__ import annotations

import math
import re
from typing import Optional
from dataclasses import fields as dc_fields

from soe.models import GameState
from soe.orders import Order
from soe import config, items


def normalize_text(text: str) -> str:
    """Normalize text for parsing (lowercase, clean whitespace)."""
    # Remove comments (# to end of line)
    text = re.sub(r'#.*?$', '', text, flags=re.MULTILINE)
    # Thousands separators stay attached to the number ("1,000" → "1000")
    # before leftover commas are blanked.
    while True:
        stripped = re.sub(r'(\d),(\d{3})\b', r'\1\2', text)
        if stripped == text:
            break
        text = stripped
    # Remove commas, colons, semicolons (rules say they're ignored)
    text = text.replace(',', ' ').replace(':', ' ').replace(';', ' ')
    # Normalize whitespace
    text = ' '.join(text.split())
    return text.lower()


def extract_sentences(text: str) -> list[str]:
    """Split text into sentences (periods delimit sentences)."""
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    return sentences


# A placeholder standing in for a quoted message while the order text is
# normalised. It has to survive lowercasing, comma stripping and the split on
# periods, so it is bare lowercase letters and digits and nothing else.
_QUOTE_TOKEN = "zqz{}zqz"
_QUOTE_TOKEN_RE = re.compile(r"zqz(\d+)zqz")


def protect_quotes(raw_text: str) -> tuple[str, list[str]]:
    """
    Lift double-quoted message bodies out of the raw order text.

    A message is the one place in an order where the player's exact characters
    matter. Everything else is lowercased, has its commas stripped and is split
    into sentences on periods -- all three of which would wreck

        Have Alan Reed post "Welcome to Highfell. Recruiting is forbidden."

    So quoted spans come out first, each replaced by a placeholder, and go back
    in once parsing is done. This also keeps pronoun resolution out of message
    text, so a message that says "meet me at dawn" still says `me`.

    Returns the text with placeholders, and the quoted strings in order.
    """
    quoted: list[str] = []

    def take(match: re.Match) -> str:
        quoted.append(match.group(1))
        return _QUOTE_TOKEN.format(len(quoted) - 1)

    # Tabs are removed from messages per the design; the rest is left verbatim.
    return re.sub(r'"([^"]*)"', take, raw_text).replace("\t", " "), quoted


def restore_quotes(text: str, quoted: list[str]) -> str:
    """Put the original message text back where a placeholder stands."""
    def give(match: re.Match) -> str:
        index = int(match.group(1))
        return quoted[index] if index < len(quoted) else ""
    return _QUOTE_TOKEN_RE.sub(give, text)


def restore_order_quotes(order: Order, quoted: list[str]) -> None:
    """
    Put message text back into every string field of a parsed order.

    Done generically rather than per order type so that a new field carrying
    player text cannot quietly ship with a placeholder still in it.
    """
    if not quoted:
        return
    for f in dc_fields(order):
        value = getattr(order, f.name, None)
        if isinstance(value, str) and "zqz" in value:
            setattr(order, f.name, restore_quotes(value, quoted))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, Order):
                    restore_order_quotes(item, quoted)


def strip_wand(sentence: str, game_state: GameState) -> tuple[str, str]:
    """
    Lift a trailing `with`/`using <wand>` clause off a spell order.

    A wand spell is cast as the ordinary order followed by the word
    with or using and the name of the wand", e.g. "teleport me to Redport
    using *Doramba*". Taking the clause off first keeps it out of the city or
    creature name the rest of the parser is trying to read.

    The clause is only recognised when it names an item that actually exists,
    so ordinary uses of `with` ("attack them with 50 soldiers") are untouched.
    Returns (sentence without the clause, wand name or "").
    """
    match = re.search(r'\s+(?:with|using)\s+(\S+)\s*$', sentence)
    if not match:
        return sentence, ""
    name = match.group(1)
    if not items.find_item_by_name(name, game_state):
        return sentence, ""
    return sentence[:match.start()].strip(), name

def _strip_clause_adverbs(sentence: str) -> str:
    r"""Remove the adverb words from a clause so they cannot be eaten into an
    actor name by a `have\s+(.+?)\s+<verb>` capture ("have alan reed
    definitely buy passage to amesbok" must name alan reed)."""
    return re.sub(r'\b(?:definitely|quietly|silently|briefly|carefully|'
                  r'exactly|repeatedly|then)\b', ' ', sentence)

TIME_UNIT_DAYS = {
    'minute': 1 / (24 * 60),
    'hour': 1 / 24,
    'day': 1.0,
    'week': 7.0,
    'month': float(config.DAYS_PER_MONTH),
}


def parse_duration_days(sentence: str) -> Optional[int]:
    """
    Read a "<number> <unit>" duration out of a sentence, in whole days.

    Rounded up, because the queue cannot hold work for less than a turn. The
    rules' one-hour minimum therefore lands on a single day here.
    """
    match = re.search(
        r'(\d+)\s+(minute|hour|day|week|month)s?\b', sentence
    )
    if not match:
        return None

    days = int(match.group(1)) * TIME_UNIT_DAYS[match.group(2)]
    return max(1, math.ceil(days))


def parse_duration_hours(sentence: str) -> Optional[int]:
    """Read a rules duration at the clock's one-hour resolution."""
    match = re.search(
        r'(\d+)\s+(minute|hour|day|week|month)s?\b', sentence
    )
    if not match:
        return None
    hours_per_unit = {
        'minute': 1 / 60,
        'hour': 1,
        'day': config.HOURS_PER_DAY,
        'week': 7 * config.HOURS_PER_DAY,
        'month': config.DAYS_PER_MONTH * config.HOURS_PER_DAY,
    }
    return max(1, math.ceil(int(match.group(1)) * hours_per_unit[match.group(2)]))

def strip_repeatedly(sentence: str) -> tuple[str, Optional[int]]:
    """
    Lift the adverb `repeatedly` (and its loop count) off a sentence.

    Returns the sentence without them, and the loop count: None when the
    sentence was not a repeat at all, 0 for a loop with no count -- which
    the design says runs until a HALT or STOP.
    """
    if not re.search(r'\brepeatedly\b', sentence):
        return sentence, None

    count_match = re.search(r'\b(\d+)\s+times?\b', sentence)
    times = int(count_match.group(1)) if count_match else 0

    stripped = re.sub(r'\brepeatedly\b|\b\d+\s+times?\b', ' ', sentence)
    return ' '.join(stripped.split()), times

