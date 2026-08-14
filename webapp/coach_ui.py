"""How the coach's browser presents a debrief.

The JSON payload is already the view from one chair. This module only names
the three things a new user has to read without help: the result, the error
worth acting on, and what the match cost. It does not read a live game.
"""

from __future__ import annotations

from typing import Mapping

from webapp.blueprints import DOCTRINE_SECTIONS

#: Strategic first: that is the only bucket worth rewriting a blueprint over.
#: Syntax is a prompt problem. Provider is nobody's doctrine.
_ERROR_PRIORITY = ("strategic", "syntax", "provider")


def doctrine_from_mapping(data: Mapping[str, object]) -> dict[str, str]:
    """Read the four doctrine sections out of a form or JSON body."""
    return {
        key: str(data.get(key) or data.get(f"doctrine_{key}") or "")
        for key in DOCTRINE_SECTIONS
    }


def runtime_from_mapping(data: Mapping[str, object]) -> dict:
    """Optional model and temperature; empty fields stay unset."""
    runtime: dict = {}
    model = str(data.get("model") or "").strip()
    if model:
        runtime["model"] = model
    temperature = str(data.get("temperature") or "").strip()
    if temperature:
        runtime["temperature"] = temperature
    return runtime


def outcome_kind(headline: Mapping[str, object]) -> str:
    """won, lost, drawn, or split — one word for the result card."""
    games = _as_int(headline.get("games"))
    won = _as_int(headline.get("won"))
    lost = _as_int(headline.get("lost"))
    drawn = _as_int(headline.get("drawn"))
    if games and won == games:
        return "won"
    if games and lost == games:
        return "lost"
    if games and drawn == games:
        return "drawn"
    return "split"


def outcome_line(headline: Mapping[str, object]) -> str:
    """The sentence on the result card."""
    games = _as_int(headline.get("games"))
    won = _as_int(headline.get("won"))
    lost = _as_int(headline.get("lost"))
    drawn = _as_int(headline.get("drawn"))
    if games and won == games:
        return "Won every game"
    if games and lost == games:
        return "Lost every game"
    if games and drawn == games:
        return "Drawn every game"
    return f"Won {won} · Lost {lost} · Drawn {drawn}"


def main_error(errors: Mapping[str, object]) -> dict:
    """The error a coach should act on, if any.

    Strategic errors come first because they are the only ones that justify
    rewriting doctrine. A discarded line is a prompt problem. A 429 is not.
    """
    strategic = _as_map(errors.get("strategic"))
    syntax = _as_map(errors.get("syntax"))
    provider = _as_map(errors.get("provider"))
    idle = _as_int(strategic.get("idle_turns"))
    silent = _as_int(strategic.get("silent_turns"))
    discarded = _as_int(syntax.get("discarded_lines"))
    provider_total = _as_int(provider.get("total"))

    if idle or silent:
        return {
            "kind": "strategic",
            "title": "Strategic",
            "summary": f"{silent} silent turn(s), {idle} idle turn(s).",
            "note": str(
                strategic.get("note")
                or "Legal orders that moved nothing. This is the one to rewrite."
            ),
        }
    if discarded:
        examples = syntax.get("examples") or []
        example = examples[0] if isinstance(examples, list) and examples else ""
        return {
            "kind": "syntax",
            "title": "Syntax",
            "summary": f"{discarded} line(s) the parser threw out.",
            "note": str(example or "The engine rejected what the agent wrote."),
        }
    if provider_total:
        return {
            "kind": "provider",
            "title": "Provider",
            "summary": f"{provider_total} provider failure(s).",
            "note": "A rate limit is not a reason to rewrite the doctrine.",
        }
    return {
        "kind": "none",
        "title": "None",
        "summary": "No syntax, provider, or strategic error.",
        "note": "",
    }


def cost_line(cost: Mapping[str, object]) -> str:
    """What the match spent, as a coach reads it."""
    usd = cost.get("usd")
    if usd is None:
        return "Cost not recorded"
    try:
        amount = f"${float(str(usd)):.4f}"
    except (TypeError, ValueError):
        return "Cost not recorded"
    calls = cost.get("calls")
    if calls is None:
        return amount
    return f"{amount} · {_as_int(calls)} call(s)"


def _as_map(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0
