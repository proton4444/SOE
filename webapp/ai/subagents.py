"""
Per-turn subagents: bounded role calls that feed the strategist.

Two roles today:

- ``intel``: one analyst call — enemy sightings, threats, opportunities —
  summarized from the faction's observed world.
- ``field``: one call per group leader (capped) — draft 1-2 game-syntax
  orders per character from their local situation.

Subagents are cheap, short, and never authoritative: the strategist decides.
Their outputs are plain text with no marker convention. A failing subagent
degrades to an "(unavailable)" note rather than wedging the turn.
"""

from __future__ import annotations

import json
import os

from webapp import service
from webapp.ai import brain
from webapp.ai.registry import AgentProfile
from webapp.rooms import Room, RoomPlayer

SUBAGENT_MODEL = os.environ.get("SOE_SUBAGENT_MODEL", "").strip()
MAX_FIELD_CHARACTERS = int(os.environ.get("SOE_MAX_SUBAGENTS", "4"))
MAX_TOKENS = int(os.environ.get("SOE_SUBAGENT_TOKENS", "600"))

_INTEL_SYSTEM = (
    "You are an intel analyst in a fantasy strategy game. Summarize the "
    "enemy sightings, threats, and opportunities visible to your faction. "
    "Be concrete and terse: at most 150 words, plain text, no headers, no "
    "markers. Name exact factions, characters, and cities when you can."
)

_FIELD_SYSTEM = (
    "You are a field commander in a fantasy strategy game. For each listed "
    "character, draft at most 2 orders in the game's order syntax (one order "
    "per line, each ending with a period). Use the exact character names "
    "given. Do not include reasoning, headers, or a marker."
)


def intel_briefing(room: Room, player: RoomPlayer, profile: AgentProfile) -> str:
    """Enemy sightings and threats from this faction's observed world."""
    try:
        state = service.player_state(room, player.faction_id)
    except Exception:  # noqa: BLE001 - degrade, never wedge
        return "(intel unavailable)"
    snippet = _intel_snippet(state)
    return _ask(profile, _INTEL_SYSTEM, snippet)


def field_drafts(room: Room, player: RoomPlayer, profile: AgentProfile) -> str:
    """Suggested per-character orders for the faction's group leaders."""
    try:
        state = service.player_state(room, player.faction_id)
    except Exception:  # noqa: BLE001 - degrade, never wedge
        return "(field unavailable)"
    characters = _leaders(state)
    if not characters:
        return "(no group leaders to draft for)"
    snippet = json.dumps(characters, indent=1, default=str)[:6000]
    return _ask(profile, _FIELD_SYSTEM, snippet)


def leader_count(room: Room, player: RoomPlayer) -> int:
    """How many group leaders the field subagent drafted for."""
    try:
        return len(_leaders(service.player_state(room, player.faction_id)))
    except Exception:  # noqa: BLE001 - count is advisory only
        return 0


def _ask(profile: AgentProfile, system: str, user_text: str) -> str:
    return brain.chat(
        model=brain.model_name(profile.model if not SUBAGENT_MODEL else SUBAGENT_MODEL),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        temperature=min(profile.temperature, 0.5),
        max_tokens=MAX_TOKENS,
    ).strip()


def _leaders(state: dict) -> list[dict]:
    chars = state.get("characters", [])
    leaders = [c for c in chars if c.get("is_leader") and c.get("id")]
    return leaders[:MAX_FIELD_CHARACTERS]


def _intel_snippet(state: dict) -> str:
    my_id = state.get("faction_id", "")
    my_name = state.get("faction_name", "")
    enemies = state.get("enemies", []) or []
    allies = state.get("allies", []) or []
    cities = state.get("cities", []) or []
    hostile = [
        c.get("name")
        for c in cities
        if c.get("observed") and c.get("secured_by") not in (None, "", my_id)
    ]
    return (
        f"My faction: {my_name}.\n"
        f"Declared enemies: {', '.join(enemies) or 'none'}.\n"
        f"Declared allies: {', '.join(allies) or 'none'}.\n"
        f"Cities secured by others: {', '.join(hostile) or 'none'}."
    )
