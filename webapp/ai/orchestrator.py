"""
Turn-level AI play: one bot decides and submits orders for its faction.

The pipeline for a bot seat is: gather fog-of-war context (structured state,
latest report) -> strategist call -> extract the orders block -> submit through
the normal order pipeline. Everything is deterministic on the engine side; the
only non-determinism is the model's ``temperature`` from the profile.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone

from soe import parser

from webapp import service
from webapp.ai import brain, subagents
from webapp.ai.registry import (
    STATE_ERROR,
    STATE_SUBMITTED,
    STATE_THINKING,
    AgentProfile,
    default_registry,
)
from webapp.rooms import Room, RoomPlayer

# The strategist's reply must end with this marker and one order per line after
# it; anything before the marker is treated as reasoning and ignored.
ORDERS_MARKER = "--- ORDERS ---"
MAX_STATE_CHARS = 15000
MAX_REPORT_CHARS = 8000
MAX_ORDERS = 15

# When enabled, the strategist also receives a PNG of its fog-of-war map
# (M5). Requires a vision-capable model; off by default because text-only
# models reject image parts.
VISION_ENABLED = os.environ.get("SOE_BOT_VISION", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class BotError(RuntimeError):
    """A bot seat cannot run: not enabled, unconfigured, or failed to play."""


def run_bot_turn(room: Room, player: RoomPlayer) -> dict:
    """Have the bot for ``player``'s faction decide and submit a turn."""
    registry = default_registry()
    profile = registry.get(room.code, player.faction_id)
    if not profile or not profile.enabled:
        raise BotError("No enabled bot profile for this faction.")
    if not brain.is_configured():
        raise BotError("LLM not configured: set SOE_LLM_KEY.")

    _set_state(room, player.faction_id, profile, STATE_THINKING, "")
    try:
        intel, field, field_count = _run_subagents(room, player, profile)
        orders = _filter_clean_orders(
            room,
            player,
            extract_orders(_ask_strategist(room, player, profile, intel, field)),
        )
        feedback = service.submit_orders(room, player, orders)
        _set_state(room, player.faction_id, profile, STATE_SUBMITTED, "")
        return {
            "faction_id": player.faction_id,
            "orders": orders,
            "parsed": feedback["parsed"],
            "warnings": feedback["warnings"],
            "state": STATE_SUBMITTED,
            "subagents": {
                "intel": intel is not None,
                "field_characters": field_count,
            },
        }
    except BotError:
        _set_state(room, player.faction_id, profile, STATE_ERROR, "bot run failed")
        raise
    except Exception as exc:  # noqa: BLE001 - the seat must not wedge
        _set_state(
            room,
            player.faction_id,
            profile,
            STATE_ERROR,
            f"{type(exc).__name__}: {exc}",
        )
        raise


def _set_state(
    room: Room, faction_id: str, profile: AgentProfile, state: str, note: str
) -> None:
    profile.state = state
    profile.last_error = note[:500]
    profile.last_run_at = datetime.now(timezone.utc).isoformat()
    default_registry().set(room.code, faction_id, profile)


def _run_subagents(
    room: Room, player: RoomPlayer, profile: AgentProfile
) -> tuple[str | None, str | None, int]:
    """Intel + field drafts for the strategist. Never throws: a subagent
    failure degrades to a note instead of wedging the turn."""
    intel = None
    try:
        intel = subagents.intel_briefing(room, player, profile)
    except Exception:  # noqa: BLE001 - degrade, never wedge
        intel = None
    field = None
    field_count = 0
    try:
        field = subagents.field_drafts(room, player, profile)
        field_count = subagents.leader_count(room, player)
    except Exception:  # noqa: BLE001 - degrade, never wedge
        field = None
    return intel, field, field_count


def _ask_strategist(
    room: Room,
    player: RoomPlayer,
    profile: AgentProfile,
    intel: str | None,
    field: str | None,
) -> str:
    context = _user_context(room, player)
    if intel:
        context += "\n\n=== INTEL BRIEFING ===\n" + intel
    if field:
        context += "\n\n=== FIELD DRAFTS ===\n" + field
    messages = [
        {"role": "system", "content": _system_prompt(room, player, profile)},
        {"role": "user", "content": context},
    ]
    return brain.chat(
        model=brain.model_name(profile.model),
        messages=messages,
        temperature=profile.temperature,
        images=_vision_images(room, player),
    )


def _vision_images(room: Room, player: RoomPlayer) -> tuple[str, ...]:
    """The faction's fog-of-war map as a PNG data URI, when vision is on."""
    if not VISION_ENABLED:
        return ()
    try:
        png = service.ai_map(room, player.faction_id, fmt="png", all_visible=False)[
            "png"
        ]
    except Exception:  # noqa: BLE001 - vision is an enhancement, never a wedge
        return ()
    return ("data:image/png;base64," + base64.b64encode(png).decode("ascii"),)


def _system_prompt(room: Room, player: RoomPlayer, profile: AgentProfile) -> str:
    persona = profile.persona.strip()
    persona_lines = f"\nPersona: {persona}" if persona else ""
    return (
        "You are the strategist for a faction in SOE, a "
        "deterministic PBEM fantasy strategy game.\n"
        f"Game: {room.name} (map {room.map_file}). "
        f"You play {player.faction_name}. Next turn: {room.next_turn()}."
        f"{persona_lines}\n\n"
        "Write orders for the next turn in the game's English-like order "
        "syntax (see the examples in the user message). Rules:\n"
        "- Use only character names that appear in the turn report or state.\n"
        "- One order per line, each ending with a period.\n"
        f"- At most {MAX_ORDERS} orders.\n"
        "- End your reply with the marker line "
        f"`{ORDERS_MARKER}` followed by the orders.\n"
        "- Anything before the marker is your reasoning and will be ignored.\n"
        "- Attack orders target enemy CHARACTERS (names from the report), "
        "never cities.\n"
        "- Invest needs an amount and a city: `Invest 50 gold in <city>`.\n"
        "- Do not tour the map: at most 2 movement orders, and only toward "
        "cities that matter to your strategy. The rest of your orders should "
        "be economy, recruiting, or diplomacy.\n"
        "- ONLY these order forms are allowed. If an action cannot be "
        "expressed in one of these forms, do not write it:\n"
        "  Have <Character> go to <City>.\n"
        "  Have <Character> sail to <City>.\n"
        "  Have <Character> fly to <City>.\n"
        "  Recruit <n> soldiers|sailors|workers in <City>.\n"
        "  Buy <n> galleys in <City>.\n"
        "  Tax.\n"
        "  Work for <n> weeks.\n"
        "  Collect <resource> for <n> days.\n"
        "  Mine <resource> for <n> days.\n"
        "  Invest <amount> gold in <City>.\n"
        "  Have <Character> attack <Character>.\n"
        "  Have <Character> secure <City>.\n"
        "  Have <Character> study <skill>.\n"
        "  Have <Character> summon <n> <creature>.\n"
        "  Ally <Faction>. | Enemy <Faction>. | Neutral <Faction>.\n"
        "  Wait for <n> days.\n"
        "- Never write narrative sentences, statements, or observations as "
        "orders."
    )


def _user_context(room: Room, player: RoomPlayer) -> str:
    try:
        state = json.dumps(
            service.player_state(room, player.faction_id),
            indent=2,
            default=str,
        )
    except Exception:  # noqa: BLE001 - a broken save must not wedge the bot
        state = "(game state unavailable)"
    if len(state) > MAX_STATE_CHARS:
        state = state[:MAX_STATE_CHARS] + "\n... (truncated)"

    report = _latest_report(room, player.faction_id)
    if len(report) > MAX_REPORT_CHARS:
        report = report[:MAX_REPORT_CHARS] + "\n... (truncated)"

    return (
        "Here is your faction's view of the world and your latest turn "
        "report.\n\n"
        "=== STRUCTURED STATE ===\n"
        f"{state}\n\n"
        "=== YOUR LAST TURN REPORT ===\n"
        f"{report}\n\n"
        "=== ORDER SYNTAX EXAMPLES ===\n"
        "Have Emperor Marcus go to Redport.\n"
        "Recruit 20 soldiers in Highfell.\n"
        "Tax.\n"
        "Have Emperor Marcus attack Khan Tengri.\n"
        "Work for 1 week.\n"
        "Wait for 1 day.\n"
    )


def _latest_report(room: Room, faction_id: str) -> str:
    reports = room.reports.get(room.last_resolved_turn, {})
    return reports.get(faction_id, "(no report yet)")


def extract_orders(reply: str) -> str:
    """Pull the orders block out of a strategist reply.

    Some models write a markdown ``---`` separator (or a trailing empty
    marker) next to the real one, so the text after the first marker
    occurrence is not always the orders. Pick the marker segment that
    actually contains order-like lines.
    """
    segments = reply.split(ORDERS_MARKER)
    if len(segments) < 2:
        return reply.strip()
    best = max(segments[1:], key=_order_line_count, default="")
    if _order_line_count(best):
        return best.strip()
    return reply.strip()


def _order_line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip().endswith("."))


_UNPARSEABLE_RE = re.compile(r"Could not parse order: '(.*)'")
# Markdown separators some models leave around the marker block. The engine
# parser merges such a line into the next sentence, which defeats warning
# matching, so strip them before parsing.
_DECORATIVE_LINE_RE = re.compile(r"^[\s\-*_=|]+$")


def _filter_clean_orders(room: Room, player: RoomPlayer, text: str) -> str:
    """Drop lines the engine's own parser could not recognise.

    The strategist occasionally writes narrative orders ("monitor the
    movements of the Shadow Syndicate") that parse with warnings. The engine
    is the authority: any line it flags as unparseable is removed, and only
    the remaining block is submitted. If nothing survives (or the game state
    is unreadable), the raw block is submitted unchanged so the host still
    sees what the bot wrote.
    """
    if not text.strip():
        return text
    raw_lines = text.splitlines()
    stripped = [
        line for line in raw_lines if not _DECORATIVE_LINE_RE.match(line.strip())
    ]
    if len(stripped) != len(raw_lines):
        text = "\n".join(stripped).strip() or text
    try:
        state = service.load_state(room)
        orders = parser.parse_orders(text, state, player.faction_id)
    except Exception:  # noqa: BLE001 - never wedge on a parser quirk
        return text
    bad = set()
    for order in orders:
        for warning in order.warnings:
            match = _UNPARSEABLE_RE.search(warning)
            if match:
                bad.add(_normalise(match.group(1)))
    if not bad:
        return text
    kept = [line for line in text.splitlines() if _normalise(line) not in bad]
    filtered = "\n".join(kept).strip()
    if not filtered:
        return text
    return filtered


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower())
