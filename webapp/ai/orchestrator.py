"""
Turn-level AI play: one bot decides and submits orders for its faction.

The pipeline for a bot seat is: gather fog-of-war context (structured state,
latest report) -> strategist call -> extract the orders block -> submit through
the normal order pipeline. Everything is deterministic on the engine side; the
only non-determinism is the model's ``temperature`` from the profile.

Message construction and reply filtering are pure and shared with the headless
arena (``webapp.ai.context``), so both seats feed the model the same
information through the same prompt.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from webapp import blueprints, service
from webapp.ai import brain, subagents
from webapp.ai import context
from webapp.ai.context import ORDERS_MARKER, extract_orders
from webapp.ai.registry import (
    STATE_ERROR,
    STATE_SUBMITTED,
    STATE_THINKING,
    AgentProfile,
    default_registry,
)
from webapp.rooms import Room, RoomPlayer

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
    strategy = _enrolled_strategy(profile)
    ctx = _decision_context(room, player, strategy)
    messages = context.build_messages(ctx, intel=intel, field=field)
    return brain.chat(
        model=brain.model_name(strategy.model),
        messages=messages,
        temperature=strategy.temperature,
        images=_vision_images(room, player),
    )


def _decision_context(
    room: Room, player: RoomPlayer, strategy: SeatStrategy
) -> context.DecisionContext:
    """Adapter: a Room + a resolved seat strategy -> the pure DecisionContext."""
    return context.DecisionContext(
        game_state=service.load_state(room),
        faction_id=player.faction_id,
        turn=room.next_turn(),
        game_name=room.name,
        map_file=room.map_file,
        previous_report=_latest_report(room, player.faction_id),
        game_id=room.code,
        blueprint=strategy.blueprint,
        persona=strategy.persona,
    )


@dataclass(frozen=True)
class SeatStrategy:
    """What one seat plays this turn: prompt text and runtime configuration."""

    blueprint: dict | None
    persona: str
    model: str
    temperature: float


def _enrolled_strategy(profile: AgentProfile) -> SeatStrategy:
    """The strategy this seat entered the match with.

    A seat with no blueprint plays its profile's own persona and model, as
    before Phase 1. A seat with one plays the frozen version whose hash it
    enrolled, read back through the store: if that version no longer hashes to
    what was inscribed, the turn stops here rather than quietly playing
    different text. The blueprint's runtime section wins over the profile's
    model and temperature, because a match pinned to a hash that does not also
    pin the model is not pinned to anything.
    """
    ref = profile.blueprint_ref()
    if ref is None:
        return SeatStrategy(None, profile.persona, profile.model, profile.temperature)
    try:
        version = blueprints.default_store().resolve(ref)
    except blueprints.BlueprintError as exc:
        raise BotError(str(exc)) from exc
    runtime = version.runtime or {}
    return SeatStrategy(
        blueprint=blueprints.runtime_blueprint(ref.blueprint_id, version),
        persona=version.persona,
        model=str(runtime.get("model") or profile.model),
        temperature=float(runtime.get("temperature", profile.temperature)),
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


def _latest_report(room: Room, faction_id: str) -> str:
    reports = room.reports.get(room.last_resolved_turn, {})
    return reports.get(faction_id, "(no report yet)")


def extract_orders(reply: str) -> str:
    """Pull the orders block out of a strategist reply (shared, pure)."""
    return context.extract_orders(reply)


def _filter_clean_orders(room: Room, player: RoomPlayer, text: str) -> str:
    """Drop lines the engine's own parser could not recognise.

    The strategist occasionally writes narrative orders ("monitor the
    movements of the Shadow Syndicate") that parse with warnings. The engine
    is the authority: any line it flags as unparseable is removed, and only
    the remaining block is submitted. If nothing survives (or the game state
    is unreadable), the raw block is submitted unchanged so the host still
    sees what the bot wrote. Pure logic lives in ``webapp.ai.context``.
    """
    try:
        state = service.load_state(room)
    except Exception:  # noqa: BLE001 - never wedge on a broken save
        return text
    return context.filter_orders(state, player.faction_id, text)
