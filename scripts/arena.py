#!/usr/bin/env python
"""
Headless arena: batch games between pluggable seat policies.

The benchmark thesis is that this game separates strong play from weak play.
Nothing has ever tested that. This harness is the test: it seats policies
against each other over many maps, swaps seats to cancel positional
advantage, and reports a head-to-head win-rate matrix.

Phase 0 adds the LLM seat: ``llm:<model>`` plays through the same pipeline as
the production bot (``webapp.ai.context``: fogged state, previous report,
blueprint doctrine, same system prompt, same order filter), so an LLM result
is comparable with the dashboard. Baselines remain ``scripted`` (the heuristic
bot from ``beta_100_turns``) and ``random`` (legal orders, no strategy).

Run modes:

    python scripts/arena.py --policies scripted,random --seeds 40 --turns 30
    python scripts/arena.py --config configs/phase0_smoke.json
    python scripts/arena.py --resume <run_id>

Config runs write a resumable run bundle under ``games/arena/<run_id>/``
(see ``scripts.arena_bundle``). Tests always use a fake brain and make no
network calls.

Creates games through ``webapp.service``, then runs the production parser and
engine in memory: no server, HTTP, autoplay pacing, or per-turn persistence.
Isolation is by ``SOE_DATA_DIR``/``SOE_GAMES_DIR``, which must be set before
``webapp`` is imported -- hence the deferred imports below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.arena_bundle import BundleError  # noqa: E402

if TYPE_CHECKING:
    from scripts.arena_bundle import RunBundle

DEFAULT_OUTPUT = _REPO_ROOT / "games" / "arena"
PHASE0_GATE_PATH = _REPO_ROOT / "configs" / "phase0_gate.json"
PHASE0_PROBE_PATH = _REPO_ROOT / "server_data" / "phase0_probe.json"
PHASE0_PROBE_MAX_AGE_HOURS = 24

# Rendered maps and reports are irrelevant here and cost real time per turn.
os.environ.setdefault("SOE_BOT_VISION", "")


# ===========================================================================
# policies
# ===========================================================================

# The order forms a policy may emit. Deliberately the same whitelist the
# strategist prompt gives an LLM (webapp/ai/context.py::system_prompt), so a
# random baseline and a model are drawing from one vocabulary and the
# comparison is about choosing well, not about knowing the syntax.
SKILLS = ("combat", "magic", "religion")
RESOURCES = ("wood", "stone")


def _order_line_metrics(orders) -> tuple[int, int, int]:
    """Return submitted command lines, warned lines, and warning messages.

    ``REPEAT`` is an internal queue marker emitted alongside one player
    command, not another line written by the policy, so it is excluded from
    the Phase 0 denominator.
    """
    from soe.orders import RepeatOrder

    commands = [order for order in orders if not isinstance(order, RepeatOrder)]
    return (
        len(commands),
        sum(1 for order in commands if order.warnings),
        sum(len(order.warnings) for order in commands),
    )


def _emitted_line_metrics(text: str, game_state, faction_id: str) -> tuple[int, int, int, list[str]]:
    """Score physical non-empty model lines before any safety filtering."""
    from soe import parser
    from webapp.ai.context import is_order_decoration

    total = warned = messages = 0
    warning_text: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or is_order_decoration(line):
            continue
        total += 1
        try:
            orders = parser.parse_orders(line, game_state, faction_id)
        except Exception as exc:  # noqa: BLE001 - one malformed emitted line
            warned += 1
            messages += 1
            warning_text.append(f"Parser error for emitted line {line!r}: {exc}")
            continue
        line_warnings = [
            warning for order in orders for warning in order.warnings
        ]
        if not orders and not line_warnings:
            line_warnings = [f"No order parsed from emitted line: {line!r}"]
        if line_warnings:
            warned += 1
            messages += len(line_warnings)
            warning_text.extend(line_warnings)
    return total, warned, messages, warning_text


@dataclass
class PolicyTurn:
    """One seat's decision for one turn."""

    #: The orders text as submitted to the production parser.
    text: str
    #: Decision trace for the run bundle (model, raw reply, usage, ...).
    trace: dict = field(default_factory=dict)


@dataclass
class SpendBudget:
    """Shared best-effort provider spend ceiling for every LLM seat."""

    limit_usd: float
    spent_usd: float = 0.0
    exhausted: bool = False
    cost_known: bool = True

    def __post_init__(self) -> None:
        if self.limit_usd <= 0:
            self.exhausted = True

    def charge(self, cost) -> None:
        if not isinstance(cost, (int, float)):
            # A ceiling cannot be enforced when the provider omits cost. Stop
            # before another paid call instead of silently running unbounded.
            self.cost_known = False
            self.exhausted = True
            return
        self.spent_usd += float(cost)
        if self.spent_usd >= self.limit_usd:
            self.exhausted = True


class Policy:
    """Decides one faction's orders for one turn from its DecisionContext."""

    #: identifies the policy in results and matchup keys
    name = "policy"

    def orders(self, ctx, rng: random.Random) -> PolicyTurn:
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


class ScriptedPolicy(Policy):
    """The heuristic bot from ``scripts/beta_100_turns.py``.

    Note for later phases: this bot reads the full game state, while an LLM
    seat sees only its fog of war. Scripted-vs-random is fair because both
    are omniscient; scripted-vs-model is not, and the margin must be read
    with that advantage in mind.
    """

    def __init__(self, style: str = "balanced"):
        self.style = style
        self.name = f"scripted:{style}"

    def orders(self, ctx, rng: random.Random) -> PolicyTurn:
        from scripts import beta_100_turns

        text = beta_100_turns.plan_orders(
            ctx.game_state, ctx.faction_id, self.style, rng
        )
        return PolicyTurn(text=text)


class RandomPolicy(Policy):
    """Legal orders, chosen at random. The floor.

    Every line it emits parses; none of them cohere. A policy that cannot beat
    this is not playing the game, and a game where this is competitive is not
    measuring anything.
    """

    name = "random"

    def __init__(self, min_orders: int = 4, max_orders: int = 10):
        self.min_orders = min_orders
        self.max_orders = max_orders

    def orders(self, ctx, rng: random.Random) -> PolicyTurn:
        gs, faction_id, turn = ctx.game_state, ctx.faction_id, ctx.turn
        leader = _leader(gs, faction_id)
        if leader is None:
            return PolicyTurn(text="# no living characters\n")

        city = gs.world_map.cities.get(leader.location_city_id)
        city_name = city.name if city else leader.location_city_id
        neighbours = _neighbour_names(gs, leader.location_city_id)
        targets = _enemy_character_names(gs, faction_id, leader.location_city_id)

        forms: list = [
            lambda: f"Have {leader.name} tax.",
            lambda: f"Recruit {rng.randint(1, 30)} soldiers in {city_name}.",
            lambda: f"Recruit {rng.randint(1, 20)} workers in {city_name}.",
            lambda: f"Have {leader.name} secure {city_name}.",
            lambda: f"Have {leader.name} study {rng.choice(SKILLS)}.",
            lambda: f"Work for {rng.randint(1, 3)} weeks.",
            lambda: f"Collect {rng.choice(RESOURCES)} for {rng.randint(1, 5)} days.",
            lambda: f"Invest {rng.randint(10, 200)} gold in {city_name}.",
            lambda: f"Wait for {rng.randint(1, 3)} days.",
        ]
        if neighbours:
            forms.append(
                lambda: f"Have {leader.name} go to {rng.choice(neighbours)}."
            )
        if targets:
            forms.append(
                lambda: f"Have {leader.name} attack {rng.choice(targets)}."
            )

        n = rng.randint(self.min_orders, self.max_orders)
        lines = [rng.choice(forms)() for _ in range(n)]
        return PolicyTurn(
            text=f"# random baseline, turn {turn}\n" + "\n".join(lines) + "\n"
        )


class LLMPolicy(Policy):
    """A model seat: same context, prompt and filter as the production bot.

    A provider failure becomes a *recorded no-op*, never a crashed batch: the
    seat submits a comment line (zero orders) and the failure is classified
    for the reliability report. The raw reply is kept in the trace for the
    internal run; credentials never leave ``brain``.
    """

    def __init__(
        self,
        *,
        model: str,
        blueprint: dict | None = None,
        blueprint_id: str = "",
        temperature: float = 0.0,
        max_tokens: int | None = None,
        budget: SpendBudget | None = None,
        record_reasoning: bool = True,
    ):
        self.model = model
        self.blueprint = blueprint
        self.blueprint_id = blueprint_id
        self.temperature = temperature
        self.budget = budget
        #: Whether the model's free text before the orders marker is persisted.
        #: An internal run keeps it for debugging. A coach-facing training run
        #: must not: that text is private chain-of-thought, and a debrief built
        #: on it would be showing a coach the model's inner monologue rather
        #: than what it did. What survives redaction is the record of play.
        self.record_reasoning = record_reasoning
        from webapp.ai import brain

        self.max_tokens = max_tokens or brain.MAX_OUTPUT_TOKENS
        base = f"llm:{model}"
        self.name = f"{base}:{blueprint_id}" if blueprint_id else base

    def orders(self, ctx, rng: random.Random) -> PolicyTurn:
        from webapp.ai import brain, context
        from soe import parser

        trace: dict = {
            "policy": self.name,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "retry_policy": {
                "max_retries": brain.MAX_RETRIES,
                "timeout_seconds": brain.TIMEOUT_SECONDS,
            },
            "blueprint_id": self.blueprint_id or None,
            "seed": ctx.seed,
            "seat": ctx.seat,
        }
        if not ctx.doctrine_text and self.blueprint:
            ctx = replace(ctx, doctrine_text=context.doctrine_section(self.blueprint))
        messages = context.build_messages(ctx)
        trace["input_hashes"] = {
            "messages": context.messages_hash(messages),
            "prompt_signature": context.prompt_signature(ctx.doctrine_text),
        }

        if not brain.is_configured():
            trace["failure_class"] = "not_configured"
            trace["failure_detail"] = "SOE_LLM_KEY not set"
            trace["no_op"] = True
            return PolicyTurn(
                text=f"# no-op: LLM not configured (turn {ctx.turn})\n", trace=trace
            )
        if self.budget is not None and self.budget.exhausted:
            trace["failure_class"] = "budget_exhausted"
            trace["failure_detail"] = (
                f"Provider spend ceiling reached: ${self.budget.limit_usd:.2f}"
            )
            trace["budget_spent_usd"] = round(self.budget.spent_usd, 6)
            trace["no_op"] = True
            return PolicyTurn(
                text=f"# no-op: provider budget exhausted (turn {ctx.turn})\n",
                trace=trace,
            )

        try:
            result = brain.chat_result(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except brain.LLMError as exc:
            trace["failure_class"] = _failure_class(exc)
            trace["failure_detail"] = str(exc)[:300]
            trace["no_op"] = True
            return PolicyTurn(
                text=f"# no-op: provider failure (turn {ctx.turn})\n", trace=trace
            )

        trace["attempts"] = result.attempts
        trace["latency_ms"] = result.latency_ms
        trace["usage"] = result.usage
        if self.budget is not None:
            self.budget.charge((result.usage or {}).get("cost"))
            trace["budget_spent_usd"] = round(self.budget.spent_usd, 6)
            trace["budget_limit_usd"] = self.budget.limit_usd
            trace["budget_cost_known"] = self.budget.cost_known
        trace["provider_request_id"] = result.provider_request_id
        if self.record_reasoning:
            trace["raw_reply"] = result.text
            trace["rationale"] = context.rationale(result.text)
        else:
            trace["reasoning_redacted"] = True
        extracted = context.extract_orders(result.text)
        trace["orders_extracted_text"] = extracted
        (
            emitted_count,
            emitted_warned,
            emitted_messages,
            emitted_warnings,
        ) = _emitted_line_metrics(extracted, ctx.game_state, ctx.faction_id)
        trace["orders_emitted"] = emitted_count
        trace["emitted_warning_order_lines"] = emitted_warned
        trace["emitted_warning_messages"] = emitted_messages
        trace["emitted_warnings"] = emitted_warnings
        filtered = context.filter_orders(ctx.game_state, ctx.faction_id, extracted)
        trace["orders_text"] = filtered
        try:
            parsed = parser.parse_orders(filtered, ctx.game_state, ctx.faction_id)
        except Exception as exc:  # noqa: BLE001 - degrade to a recorded no-op
            trace["failure_class"] = "parse_error"
            trace["failure_detail"] = f"{type(exc).__name__}: {exc}"[:300]
            trace["no_op"] = True
            return PolicyTurn(
                text=f"# no-op: orders unparseable (turn {ctx.turn})\n", trace=trace
            )
        submitted_count, submitted_warned, submitted_messages = _order_line_metrics(
            parsed
        )
        trace["orders_submitted"] = submitted_count
        trace["orders_accepted"] = submitted_count - submitted_warned
        trace["submitted_warning_order_lines"] = submitted_warned
        trace["submitted_warning_messages"] = submitted_messages
        trace["warnings"] = [w for order in parsed for w in order.warnings]
        trace["order_types"] = [order.order_type() for order in parsed]
        trace["no_op"] = not filtered.strip()
        return PolicyTurn(text=filtered, trace=trace)


def _failure_class(exc: Exception) -> str:
    """Classify a provider failure for the reliability report."""
    message = str(exc)
    match = re.search(r"HTTP (\d{3})", message)
    if match:
        code = int(match.group(1))
        if code == 429:
            return "http_429"
        if 400 <= code < 500:
            return "http_4xx"
        return "http_5xx"
    if any(token in message for token in ("ConnectError", "Timeout", "ReadError")):
        return "transport"
    return "other"


def build_policy(spec: str) -> Policy:
    """``random``, ``scripted[:style]``, ``llm:model[:blueprint-id]`` -> Policy."""
    head, _, tail = spec.partition(":")
    head = head.strip().lower()
    if head == "random":
        return RandomPolicy()
    if head == "scripted":
        return ScriptedPolicy(tail.strip().lower() or "balanced")
    if head == "llm":
        model, _, blueprint_id = tail.partition(":")
        return LLMPolicy(
            model=model.strip(),
            blueprint=_load_blueprint(blueprint_id.strip()),
            blueprint_id=blueprint_id.strip(),
        )
    raise ValueError(
        f"Unknown policy '{spec}'. Phase 0 supports: random, "
        "scripted[:balanced|military|religious], llm:model[:blueprint-id]"
    )


BLUEPRINTS_DIR = _REPO_ROOT / "configs" / "blueprints"

#: A blueprint id names a file. It arrives from a CLI policy spec and from run
#: config JSON, so an id such as ``../../server_data/llm_settings`` would
#: otherwise read the API key file into the doctrine section and copy it into
#: the run bundle.
_BLUEPRINT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

#: A blueprint held by value still becomes a filename inside the bundle, so it
#: is confined the same way. Underscores are allowed here and not in a file id,
#: which is what keeps a store label from ever resolving to a file.
_BLUEPRINT_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def blueprint_path(blueprint_id: str) -> Path:
    """The frozen blueprint file for ``blueprint_id``, confined to
    ``configs/blueprints``."""
    if not _BLUEPRINT_ID_RE.fullmatch(str(blueprint_id or "")):
        raise ValueError(
            f"Invalid blueprint id {blueprint_id!r}: expected lowercase "
            "letters, digits and hyphens, e.g. 'expansionist-v1'"
        )
    root = BLUEPRINTS_DIR.resolve()
    path = (root / f"{blueprint_id}.json").resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Invalid blueprint id {blueprint_id!r}: escapes {root}")
    return path


def _load_blueprint(blueprint_id: str) -> dict | None:
    if not blueprint_id:
        return None
    path = blueprint_path(blueprint_id)
    if not path.exists():
        raise ValueError(f"Unknown blueprint '{blueprint_id}': {path} missing")
    return json.loads(path.read_text(encoding="utf-8"))


# ===========================================================================
# state helpers
# ===========================================================================


def _leader(gs, faction_id: str):
    """The faction's acting character: its leader, else any living character."""
    alive = [
        c
        for c in gs.characters.values()
        if c.faction_id == faction_id and not c.is_dead and not c.is_prisoner
    ]
    if not alive:
        return None
    for c in alive:
        if c.is_leader:
            return c
    return alive[0]


def _neighbour_names(gs, city_id: str) -> list[str]:
    return sorted({city.name for city, _road in gs.world_map.neighbors(city_id)})


def _enemy_character_names(gs, faction_id: str, city_id: str) -> list[str]:
    return sorted(
        c.name
        for c in gs.characters.values()
        if c.location_city_id == city_id
        and c.faction_id != faction_id
        and not c.is_dead
        and not c.is_prisoner
    )


def _soldiers_total(gs, faction_id: str) -> int:
    from scripts import beta_100_turns

    return beta_100_turns._soldiers_total(gs, faction_id)


def _faction_metrics(gs, faction_id: str) -> dict:
    fac = gs.factions[faction_id]
    chars = [c for c in gs.characters.values() if c.faction_id == faction_id]
    alive = [c for c in chars if not c.is_dead and not c.is_prisoner]
    return {
        "secured": len(getattr(fac, "secured_city_ids", set()) or []),
        "controlled": len(fac.controlled_city_ids),
        "gold": round(sum(c.gold for c in chars) + fac.treasury, 1),
        "soldiers": _soldiers_total(gs, faction_id),
        "characters_alive": len(alive),
    }


def _faction_alive(gs, faction_id: str) -> bool:
    return any(
        c.faction_id == faction_id and not c.is_dead and not c.is_prisoner
        for c in gs.characters.values()
    )


def _hostile_contact(gs, faction_id: str) -> bool:
    """An enemy living character is co-located with one of ours."""
    mine = {
        c.location_city_id
        for c in gs.characters.values()
        if c.faction_id == faction_id and not c.is_dead and not c.is_prisoner
    }
    return any(
        c.faction_id != faction_id
        and c.faction_id != "independent"
        and not c.is_dead
        and not c.is_prisoner
        and c.location_city_id in mine
        for c in gs.characters.values()
    )


# ===========================================================================
# scoring
# ===========================================================================

# Win rate is the headline score: ordinal, needs no weighting argument, and
# hard to game. The tiebreak chain only decides games the primary metric ties.
TIEBREAK = ("secured", "controlled", "soldiers", "characters_alive", "gold")


def decide_winner(metrics: dict[str, dict]) -> str | None:
    """Faction id of the winner, or None for a genuine draw."""
    contenders = [
        item for item in metrics.items() if item[1]["characters_alive"] > 0
    ]
    ranked = sorted(
        contenders,
        key=lambda kv: tuple(kv[1][k] for k in TIEBREAK),
        reverse=True,
    )
    if len(ranked) < 2:
        return ranked[0][0] if ranked else None
    best, second = ranked[0], ranked[1]
    if tuple(best[1][k] for k in TIEBREAK) == tuple(second[1][k] for k in TIEBREAK):
        return None
    return best[0]


# ===========================================================================
# one game
# ===========================================================================


@dataclass
class GameResult:
    code: str
    map_file: str
    turns_played: int
    seats: dict[str, str]  # faction_id -> policy name
    metrics: dict[str, dict]
    winner: str | None
    #: Warning messages attached after the engine has processed submitted orders.
    warnings: Counter = field(default_factory=Counter)
    #: Number of submitted player command lines carrying one or more warnings.
    warning_order_lines: Counter = field(default_factory=Counter)
    #: Number of submitted player command lines (internal REPEAT markers excluded).
    order_lines: Counter = field(default_factory=Counter)
    parsed_orders: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    wall_seconds: float = 0.0
    #: Decision traces for every seat and turn (recorded into the bundle).
    traces: list[dict] = field(default_factory=list)
    #: faction_id -> first turn it had hostile contact (0 = never)
    contact_turn: dict[str, int] = field(default_factory=dict)
    #: faction_id -> turn it was eliminated (0 = survived)
    eliminated_at: dict[str, int] = field(default_factory=dict)
    #: per-turn faction metrics, for territory/soldier curves
    per_turn: list[dict] = field(default_factory=list)
    final_state_sha: str = ""

    def winner_policy(self) -> str | None:
        return self.seats.get(self.winner) if self.winner else None


def _reset_game(code: str) -> None:
    """Drop a room and its game directory so the code can be replayed.

    Start cities are derived from the room code, so the two seat orderings of
    a matchup must share a code to share a map. They therefore cannot coexist
    on disk, and the first is cleared before the second runs.
    """
    from webapp import rooms as rooms_mod

    store = rooms_mod.default_store()
    room = store._rooms.pop(code, None)
    if room is not None:
        shutil.rmtree(room.game_dir(), ignore_errors=True)
        store.save()


def _decision_context(
    gs, faction_id, turn, room, map_file, seed, seat, prev_reports
):
    """Adapter: engine state + seat metadata -> the shared DecisionContext."""
    from webapp.ai.context import DecisionContext

    return DecisionContext(
        game_state=gs,
        faction_id=faction_id,
        turn=turn,
        game_name=room.name,
        map_file=map_file,
        previous_report=prev_reports.get(faction_id, "(no report yet)"),
        game_id=room.code,
        seed=seed,
        seat=seat,
    )


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def play_game(
    code: str,
    map_file: str,
    policies: list[Policy],
    turns: int,
    seed: int,
    *,
    game_id: str = "",
    bundle=None,
) -> GameResult:
    """Create a room, run ``turns`` turns, return the result.

    ``bundle`` (``scripts.arena_bundle.RunBundle``) is optional; when given,
    every decision is recorded under its idempotent key and, on resume,
    already-recorded decisions are replayed from the bundle instead of asking
    the policy again. A provider failure in any policy yields a recorded
    no-op: the batch never crashes on a model that cannot play.
    """
    from webapp import rooms as rooms_mod
    from webapp import service
    from soe import engine, parser, reporting

    started = time.time()
    _reset_game(code)
    players = [
        rooms_mod.RoomPlayer(
            slot=i,
            faction_id=f"player_{i + 1}",
            faction_name=rooms_mod.FACTION_NAMES[i % len(rooms_mod.FACTION_NAMES)][0],
            display_name=policy.name,
            kind="agent",
            agent_key=f"arena-{code}-{i}",
        )
        for i, policy in enumerate(policies)
    ]
    room = rooms_mod.Room(
        code=code,
        pin="0000",
        name=f"arena {code}",
        map_file=map_file,
        host_key=f"host-{code}",
        created_at=datetime.now(timezone.utc).isoformat(),
        slots=len(players),
        players=players,
    )

    store = rooms_mod.default_store()
    store._rooms[code] = room
    store.save()

    service.create_game(room)
    gs = service.load_state(room)

    game_id = game_id or code
    seats = {p.faction_id: policies[i].name for i, p in enumerate(players)}
    warnings: Counter = Counter()
    warning_order_lines: Counter = Counter()
    order_lines: Counter = Counter()
    parsed: Counter = Counter()
    errors: list[str] = []
    played = 0
    traces: list[dict] = []
    prev_reports: dict[str, str] = {
        p.faction_id: "(no report yet)" for p in players
    }
    contact_turn: dict[str, int] = {p.faction_id: 0 for p in players}
    eliminated_at: dict[str, int] = {p.faction_id: 0 for p in players}
    per_turn: list[dict] = []

    if bundle is not None:
        bundle.record_game(
            game_id,
            {
                "code": code,
                "seed": seed,
                "map": map_file,
                "seats": seats,
                "turns": turns,
                "started_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    for turn in range(1, turns + 1):
        orders_by_player = {}
        turn_traces: dict[str, dict] = {}
        for i, player in enumerate(players):
            policy = policies[i]
            # Seeded per seat and turn so a rerun of the same matchup is
            # byte-identical -- the engine is deterministic and the arena
            # must not be the thing that introduces noise.
            rng = random.Random(f"{seed}:{code}:{player.faction_id}:{turn}")
            ctx = _decision_context(
                gs, player.faction_id, turn, room, map_file, seed, i, prev_reports
            )
            recorded = (
                bundle.get_decision(game_id, turn, player.faction_id)
                if bundle is not None
                else None
            )
            if recorded is not None:
                turn_outcome = PolicyTurn(
                    text=recorded.get("orders_text", ""),
                    trace=dict(recorded),
                )
            else:
                try:
                    turn_outcome = policy.orders(ctx, rng)
                except Exception as exc:  # noqa: BLE001 - a broken policy loses, not crashes
                    error = f"turn {turn} {policy.name}: {type(exc).__name__}: {exc}"
                    errors.append(error)
                    turn_outcome = PolicyTurn(
                        text=f"# policy error on turn {turn}\n",
                        trace={
                            "failure_class": "policy_error",
                            "failure_detail": error,
                        },
                    )

            text = turn_outcome.text
            player_orders = parser.parse_orders(text, gs, player.faction_id)
            orders_by_player[player.faction_id] = player_orders
            parsed[policy.name] += len(player_orders)

            trace = dict(turn_outcome.trace)
            trace.update(
                {
                    "game": game_id,
                    "turn": turn,
                    "faction_id": player.faction_id,
                    "policy": policy.name,
                    "orders_text": text,
                    "orders_accepted": len(player_orders),
                    "order_types": [o.order_type() for o in player_orders],
                    "warnings": [w for order in player_orders for w in order.warnings],
                }
            )
            if recorded is None and bundle is not None:
                bundle.record_decision(game_id, turn, player.faction_id, trace)
                bundle.record_orders_text(game_id, turn, player.faction_id, text)
            traces.append(trace)
            turn_traces[player.faction_id] = trace

        engine_failed = False
        try:
            gs, turn_log = engine.run_turn(
                gs, orders_by_player, service.deterministic_seed(room, turn)
            )
            played = turn
        except Exception as exc:  # noqa: BLE001 - report the stall, keep the batch alive
            errors.append(f"resolve turn {turn}: {type(exc).__name__}: {exc}")
            engine_failed = True

        # Count the exact gate metric only after validation and execution have
        # had a chance to attach warnings. One bad command counts once even if
        # the engine explains it with multiple messages.
        for player in players:
            policy_name = seats[player.faction_id]
            line_count, warned_count, message_count = _order_line_metrics(
                orders_by_player.get(player.faction_id, [])
            )
            order_lines[policy_name] += line_count
            warning_order_lines[policy_name] += warned_count
            warnings[policy_name] += message_count
            trace = turn_traces[player.faction_id]
            trace["resolved_order_lines"] = line_count
            trace["resolved_warning_order_lines"] = warned_count
            trace["resolved_warning_messages"] = message_count
            trace["resolved_warnings"] = [
                warning
                for order in orders_by_player.get(player.faction_id, [])
                for warning in order.warnings
            ]
            trace["orders_accepted_after_resolution"] = line_count - warned_count

        if engine_failed:
            break

        reports = reporting.generate_player_reports(gs, turn_log, orders_by_player)
        prev_reports = {
            p.faction_id: reports.get(p.faction_id, "(no report yet)")
            for p in players
        }
        for player in players:
            if not eliminated_at[player.faction_id] and not _faction_alive(
                gs, player.faction_id
            ):
                eliminated_at[player.faction_id] = turn
            if not contact_turn[player.faction_id] and _hostile_contact(
                gs, player.faction_id
            ):
                contact_turn[player.faction_id] = turn
        per_turn.append(
            {
                "turn": turn,
                "metrics": {
                    p.faction_id: _faction_metrics(gs, p.faction_id)
                    for p in players
                },
            }
        )
        if bundle is not None:
            from scripts.arena_bundle import BundleError, state_sha

            recorded_turn = bundle.get_turn(game_id, turn)
            state_digest = state_sha(gs)
            if recorded_turn is not None:
                if recorded_turn.get("state_sha") != state_digest:
                    raise BundleError(
                        f"State hash mismatch on resume: game={game_id} turn={turn} "
                        f"bundle={recorded_turn.get('state_sha')} replay={state_digest}"
                    )
            else:
                bundle.record_turn(
                    {
                        "game": game_id,
                        "turn": turn,
                        "seed": service.deterministic_seed(room, turn),
                        "state_sha": state_digest,
                        "reports": {
                            fid: _text_sha(prev_reports[fid]) for fid in prev_reports
                        },
                        # Per-faction position at the end of this turn. Already
                        # computed for the batch summary; persisting it is what
                        # lets a debrief show a turn's observable effect without
                        # replaying the engine, and therefore without any number
                        # the record cannot account for.
                        "metrics": per_turn[-1]["metrics"],
                    }
                )

    metrics = {p.faction_id: _faction_metrics(gs, p.faction_id) for p in players}
    result = GameResult(
        code=code,
        map_file=map_file,
        turns_played=played,
        seats=seats,
        metrics=metrics,
        winner=decide_winner(metrics),
        warnings=warnings,
        warning_order_lines=warning_order_lines,
        order_lines=order_lines,
        parsed_orders=parsed,
        errors=errors,
        wall_seconds=round(time.time() - started, 2),
        traces=traces,
        contact_turn=contact_turn,
        eliminated_at=eliminated_at,
        per_turn=per_turn,
    )
    if bundle is not None:
        from scripts.arena_bundle import state_sha

        result.final_state_sha = state_sha(gs)
        bundle.record_game(
            game_id,
            {
                "code": code,
                "event": "result",
                "turns_played": played,
                "winner": result.winner,
                "final_state_sha": result.final_state_sha,
                "wall_seconds": result.wall_seconds,
            },
        )
    return result


# ===========================================================================
# batch
# ===========================================================================


def entrant_blueprint(entrant: dict) -> tuple[str, dict | None]:
    """One entrant's blueprint, by file id or held by value.

    Phase 0 named a file in ``configs/blueprints``. Phase 1 blueprints are rows
    in a coach's store with no file to name, so a training entrant carries the
    prompt-facing payload itself under ``blueprint_inline`` and a label under
    ``blueprint_label``. The two forms never collide: a file id is lowercase
    and hyphenated, and a store label carries the version suffix.
    """
    inline = entrant.get("blueprint_inline")
    if isinstance(inline, dict):
        label = str(entrant.get("blueprint_label") or inline.get("id") or "inline")
        if not _BLUEPRINT_LABEL_RE.fullmatch(label):
            raise ValueError(
                f"Invalid blueprint label {label!r}: expected letters, digits, "
                "hyphen or underscore"
            )
        return label, inline
    blueprint_id = entrant.get("blueprint", "")
    return blueprint_id, (_load_blueprint(blueprint_id) if blueprint_id else None)


def build_policies_from_config(config: dict) -> list[Policy]:
    """Entrants list -> policies (blueprints resolved from configs/blueprints)."""
    policies: list[Policy] = []
    ceiling = config.get("max_spend_usd")
    budget = (
        SpendBudget(float(ceiling))
        if isinstance(ceiling, (int, float)) and float(ceiling) >= 0
        else None
    )
    for entrant in config.get("entrants", []):
        kind = entrant.get("type", "")
        if kind == "random":
            policies.append(RandomPolicy())
        elif kind == "scripted":
            policies.append(ScriptedPolicy(entrant.get("style", "balanced")))
        elif kind == "llm":
            label, blueprint = entrant_blueprint(entrant)
            policies.append(
                LLMPolicy(
                    model=entrant.get("model", ""),
                    blueprint=blueprint,
                    blueprint_id=label,
                    temperature=config.get("temperature", 0.0),
                    max_tokens=config.get("max_tokens"),
                    budget=budget,
                    record_reasoning=not bool(config.get("redact_reasoning")),
                )
            )
        else:
            raise ValueError(f"Unknown entrant type '{kind}' in config")
    return policies


def run_batch(
    config: dict,
    output: Path,
    *,
    bundle=None,
) -> dict:
    """Play every seed as a *pair*: same map, seats exchanged.

    Start-city quality dominates short games, so a single game says almost
    nothing about the policies. A pair does: if one policy wins from both
    seats of the same map, the map cannot explain it.
    """
    policies = build_policies_from_config(config)
    if len(policies) != 2:
        raise ValueError("Phase 0 compares exactly two policies")
    if policies[0].name == policies[1].name:
        raise ValueError("The two policies must differ")

    seeds = int(config.get("seed_pairs", 4))
    turns = int(config.get("turns", 30))
    map_file = config.get("map", "")
    specs = [p.name for p in policies]

    print(f"Arena: {specs[0]} vs {specs[1]}")
    print(f"  map={map_file} seeds={seeds} turns={turns}")
    if bundle is not None:
        print(f"  bundle={bundle.run_dir}")

    results: list[GameResult] = []
    pairs: list[dict] = []
    try:
        for seed in range(seeds):
            code = f"AR{seed:03d}"
            pair_winners: list[str | None] = []
            for ordering in ((0, 1), (1, 0)):
                seat_policies = [policies[ordering[0]], policies[ordering[1]]]
                game_id = f"{code}_{'ab' if ordering == (0, 1) else 'ba'}"
                result = play_game(
                    code,
                    map_file,
                    seat_policies,
                    turns,
                    seed,
                    game_id=game_id,
                    bundle=bundle,
                )
                results.append(result)
                pair_winners.append(result.winner_policy())
                print(
                    f"  {code}  {seat_policies[0].name:<28} vs "
                    f"{seat_policies[1].name:<28} "
                    f"turns={result.turns_played:<3} "
                    f"winner={result.winner_policy() or 'draw'}",
                    flush=True,
                )

            if pair_winners[0] is not None and pair_winners[0] == pair_winners[1]:
                verdict, swept_by = "swept", pair_winners[0]
            elif pair_winners[0] is None and pair_winners[1] is None:
                verdict, swept_by = "draw", None
            else:
                verdict, swept_by = "split", None
            pairs.append(
                {
                    "seed": seed,
                    "code": code,
                    "winners": pair_winners,
                    "verdict": verdict,
                    "swept_by": swept_by,
                }
            )
            print(f"    -> pair {verdict}" + (f" by {swept_by}" if swept_by else ""))
    except KeyboardInterrupt:
        if bundle is not None:
            bundle.finish("interrupted")
        raise
    except Exception:
        if bundle is not None:
            bundle.finish("failed")
        raise

    summary = summarise(specs, results, pairs, turns, map_file, output, config=config)
    if bundle is not None:
        report_path = output / "ARENA_REPORT.md"
        report_text = (
            report_path.read_text(encoding="utf-8")
            if report_path.exists()
            else render_report(summary)
        )
        bundle.finish("complete", report_markdown=report_text)
    return summary


def summarise(
    specs: list[str],
    results: list[GameResult],
    pairs: list[dict],
    turns: int,
    map_file: str,
    output: Path,
    *,
    config: dict | None = None,
) -> dict:
    wins: Counter = Counter()
    draws = 0
    for r in results:
        w = r.winner_policy()
        if w is None:
            draws += 1
        else:
            wins[w] += 1

    played = len(results)
    decisive = played - draws
    sweeps: Counter = Counter(
        p["swept_by"] for p in pairs if p["verdict"] == "swept"
    )
    splits = sum(1 for p in pairs if p["verdict"] == "split")

    # How often a metric actually separated the two factions. If `secured`
    # never breaks a tie, the headline result is being decided by whatever
    # comes next in TIEBREAK, and that is worth knowing loudly.
    decided_by: Counter = Counter()
    for r in results:
        vals = list(r.metrics.values())
        if len(vals) == 2:
            alive = [value["characters_alive"] > 0 for value in vals]
            if alive.count(True) == 1:
                decided_by["elimination"] += 1
                continue
            for key in TIEBREAK:
                if vals[0][key] != vals[1][key]:
                    decided_by[key] += 1
                    break
            else:
                decided_by["tied"] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "policies": specs,
        "map": map_file,
        "turns_per_game": turns,
        "games": played,
        "draws": draws,
        "wins": dict(wins),
        "win_rate": {
            s: (round(wins[s] / decisive, 3) if decisive else None) for s in specs
        },
        "pairs": pairs,
        "pair_sweeps": {s: sweeps.get(s, 0) for s in specs},
        "pair_splits": splits,
        "decided_by": dict(decided_by),
        "warnings_total": {
            s: sum(r.warnings.get(s, 0) for r in results) for s in specs
        },
        "warning_order_lines_total": {
            s: sum(r.warning_order_lines.get(s, 0) for r in results) for s in specs
        },
        "order_lines_total": {
            s: sum(r.order_lines.get(s, 0) for r in results) for s in specs
        },
        "parsed_orders_total": {
            s: sum(r.parsed_orders.get(s, 0) for r in results) for s in specs
        },
        "errors": [e for r in results for e in r.errors],
        "results": [
            {
                "code": r.code,
                "seats": r.seats,
                "turns_played": r.turns_played,
                "winner": r.winner,
                "winner_policy": r.winner_policy(),
                "metrics": r.metrics,
                "wall_seconds": r.wall_seconds,
                "contact_turn": r.contact_turn,
                "eliminated_at": r.eliminated_at,
                "final_state_sha": r.final_state_sha,
            }
            for r in results
        ],
        "reliability": _reliability_summary(specs, results),
        "emitted_order_quality": _emitted_order_quality(specs, results),
        "resolved_warning_categories": _resolved_warning_categories(specs, results),
        "strategy": _strategy_summary(specs, results),
        "blueprint_diff": _blueprint_diff_summary(specs, results),
    }

    summary["warning_order_rate"] = {
        s: round(
            summary["warning_order_lines_total"][s]
            / summary["order_lines_total"][s],
            6,
        )
        if summary["order_lines_total"][s]
        else None
        for s in specs
    }

    if config is not None:
        summary["config"] = config
        summary["phase0_run_gate"] = _phase0_run_gate(summary, config, output)

    output.mkdir(parents=True, exist_ok=True)
    (output / "arena_results.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output / "ARENA_REPORT.md").write_text(render_report(summary), encoding="utf-8")
    return summary


# ===========================================================================
# Phase 0 metrics (WP5): reliability + strategy + blueprint differentiation
# ===========================================================================


def _traces_for(results: list[GameResult], policy: str) -> list[dict]:
    return [t for r in results for t in r.traces if t.get("policy") == policy]


def _reliability_summary(specs: list[str], results: list[GameResult]) -> dict:
    per: dict[str, dict] = {}
    for policy in specs:
        traces = _traces_for(results, policy)
        # Scripted and random seats also have per-turn traces for strategy
        # metrics, but they are not model calls and must never appear as 100%
        # reliable LLM seats.
        if not traces or not any(trace.get("model") for trace in traces):
            per[policy] = {"calls_attempted": 0, "n_a": True}
            continue
        failures: Counter = Counter()
        latencies: list[float] = []
        tokens = Counter()
        cost_total = 0.0
        cost_known = False
        parseable = 0
        completed = 0
        no_op = 0
        retried = 0
        for trace in traces:
            if trace.get("failure_class"):
                failures[trace["failure_class"]] += 1
            if "raw_reply" in trace:
                completed += 1
            accepted = trace.get(
                "orders_accepted_after_resolution",
                trace.get("orders_accepted", 0),
            )
            if int(accepted or 0) > 0:
                parseable += 1
            if trace.get("no_op"):
                no_op += 1
            latency = trace.get("latency_ms")
            if isinstance(latency, (int, float)):
                latencies.append(latency)
            if int(trace.get("attempts", 1) or 1) > 1:
                retried += 1
            usage = trace.get("usage") or {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    tokens[key] += value
            cost = usage.get("cost") if isinstance(usage, dict) else None
            if isinstance(cost, (int, float)):
                cost_total += cost
                cost_known = True
        attempted = len(traces)
        accepted_call_rate = round(parseable / attempted, 4) if attempted else None
        per[policy] = {
            "calls_attempted": attempted,
            "calls_completed": completed,
            "call_failures": dict(failures),
            # Kept for bundle compatibility; acceptance is measured after
            # engine resolution, so accepted_call_rate is the precise name.
            "parseable_call_rate": accepted_call_rate,
            "accepted_call_rate": accepted_call_rate,
            "no_op_turns": no_op,
            "retried_calls": retried,
            "latency_ms": _distribution(latencies),
            "tokens": dict(tokens),
            "cost": round(cost_total, 6) if cost_known else None,
        }
    return per


def _emitted_order_quality(specs: list[str], results: list[GameResult]) -> dict:
    """Model-output quality before the safety filter removes invalid lines.

    This is the competence-gate numerator: a line the model emitted remains a
    model mistake even when the shared filter correctly prevents submission.
    """
    quality: dict[str, dict] = {}
    for policy in specs:
        traces = [
            trace
            for trace in _traces_for(results, policy)
            if "orders_emitted" in trace
        ]
        if not traces:
            quality[policy] = {"n_a": True}
            continue
        emitted = sum(int(trace.get("orders_emitted", 0) or 0) for trace in traces)
        warned = sum(
            int(trace.get("emitted_warning_order_lines", 0) or 0)
            for trace in traces
        )
        messages = sum(
            int(trace.get("emitted_warning_messages", 0) or 0)
            for trace in traces
        )
        quality[policy] = {
            "order_lines": emitted,
            "warning_order_lines": warned,
            "warning_messages": messages,
            "warning_order_rate": round(warned / emitted, 6) if emitted else None,
        }
    return quality


def _resolved_warning_categories(specs: list[str], results: list[GameResult]) -> dict:
    """Count post-engine warning messages for prompt and policy diagnosis."""
    return {
        policy: dict(
            Counter(
                warning
                for trace in _traces_for(results, policy)
                for warning in trace.get("resolved_warnings", [])
            ).most_common()
        )
        for policy in specs
    }


def _one_sided_sweep_p(winner_sweeps: int, loser_sweeps: int) -> float:
    """Exact one-sided binomial tail for decisive seed-pair sweeps."""
    decisive = winner_sweeps + loser_sweeps
    if decisive <= 0:
        return 1.0
    return sum(
        math.comb(decisive, successes)
        for successes in range(winner_sweeps, decisive + 1)
    ) / (2**decisive)


def _blueprint_behavior_gap(summary: dict) -> dict:
    """Largest normalized gap in the order families named by the gate."""
    diff = summary.get("blueprint_diff", {})
    a_orders = (diff.get("a") or {}).get("orders", {})
    b_orders = (diff.get("b") or {}).get("orders", {})
    families = ("recruit", "attack", "movement", "secure", "tax")
    a_total = sum(int(a_orders.get(family, 0) or 0) for family in families)
    b_total = sum(int(b_orders.get(family, 0) or 0) for family in families)
    if not a_total or not b_total:
        return {"maximum_order_share_gap": 0.0, "family": None, "shares": {}}
    gaps = {}
    shares = {}
    for family in families:
        a_share = int(a_orders.get(family, 0) or 0) / a_total
        b_share = int(b_orders.get(family, 0) or 0) / b_total
        shares[family] = {"a": round(a_share, 6), "b": round(b_share, 6)}
        gaps[family] = abs(a_share - b_share)
    family = max(gaps, key=gaps.get)
    return {
        "maximum_order_share_gap": round(gaps[family], 6),
        "family": family,
        "shares": shares,
    }


def _phase0_run_gate(summary: dict, config: dict, output: Path) -> dict:
    """Machine-readable verdict for one official Phase 0 candidate run."""
    mode = str(config.get("mode", ""))
    if not mode.startswith("official_"):
        return {"status": "not_applicable"}

    gate = load_phase0_gate()
    specs = summary["policies"]
    role = str(config.get("gate_role", ""))
    llm_specs = [spec for spec in specs if spec.startswith("llm:")]
    reliability = summary.get("reliability", {})
    quality = summary.get("emitted_order_quality", {})

    manifest = {}
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}

    completed_rates = {}
    for spec in llm_specs:
        value = reliability.get(spec, {})
        attempted = int(value.get("calls_attempted", 0) or 0)
        completed_rates[spec] = (
            int(value.get("calls_completed", 0) or 0) / attempted
            if attempted
            else 0.0
        )
    accepted_rates = {
        spec: reliability.get(spec, {}).get(
            "accepted_call_rate",
            reliability.get(spec, {}).get("parseable_call_rate"),
        )
        for spec in llm_specs
    }
    emitted_warning_rates = {
        spec: quality.get(spec, {}).get("warning_order_rate") for spec in llm_specs
    }
    submitted_warning_rates = {
        spec: summary.get("warning_order_rate", {}).get(spec) for spec in llm_specs
    }
    warning_rates = {
        spec: max(
            rate
            for rate in (
                emitted_warning_rates.get(spec),
                submitted_warning_rates.get(spec),
            )
            if isinstance(rate, (int, float))
        )
        if any(
            isinstance(rate, (int, float))
            for rate in (
                emitted_warning_rates.get(spec),
                submitted_warning_rates.get(spec),
            )
        )
        else None
        for spec in llm_specs
    }

    sweeps = summary["pair_sweeps"]
    if role == "competence":
        winner = specs[0]
        loser = specs[1]
    else:
        winner, loser = sorted(specs, key=lambda spec: sweeps.get(spec, 0), reverse=True)
    winner_sweeps = int(sweeps.get(winner, 0))
    loser_sweeps = int(sweeps.get(loser, 0))
    sweep_p = _one_sided_sweep_p(winner_sweeps, loser_sweeps)
    behavior_gap = _blueprint_behavior_gap(summary)

    criteria = {
        "sample_size": len(summary.get("pairs", []))
        >= int(gate["minimum_seed_pairs"]),
        "engine_errors": not summary.get("errors"),
        "all_games_complete": summary.get("games")
        == 2 * int(config.get("seed_pairs", 0))
        and all(
            result.get("turns_played") == int(config.get("turns", 0))
            for result in summary.get("results", [])
        ),
        "model_seats_completed": bool(llm_specs)
        and all(
            rate >= float(gate["minimum_completed_call_rate"])
            for rate in completed_rates.values()
        ),
        "model_seats_failure_free": bool(llm_specs)
        and all(not reliability.get(spec, {}).get("call_failures") for spec in llm_specs),
        "accepted_call_rate": bool(llm_specs)
        and all(
            isinstance(rate, (int, float))
            and rate >= float(gate["minimum_accepted_call_rate"])
            for rate in accepted_rates.values()
        ),
        "warning_order_rate": bool(llm_specs)
        and all(
            isinstance(rate, (int, float))
            and rate <= float(gate["maximum_warning_order_rate"])
            for rate in warning_rates.values()
        ),
        "sweep_significance": winner_sweeps > loser_sweeps
        and sweep_p < float(gate["maximum_one_sided_p"]),
        "blueprint_behavior_diff": role != "blueprint_differentiation"
        or behavior_gap["maximum_order_share_gap"]
        >= float(gate["minimum_blueprint_order_share_gap"]),
        "state_hashes": bool(summary.get("results"))
        and all(len(str(result.get("final_state_sha", ""))) == 64 for result in summary["results"]),
        "clean_worktree": manifest.get("git_dirty") is False,
        "cost_and_duration": bool(llm_specs)
        and all(reliability.get(spec, {}).get("cost") is not None for spec in llm_specs)
        and all(float(result.get("wall_seconds", 0) or 0) > 0 for result in summary["results"]),
    }
    return {
        "status": "pass" if all(criteria.values()) else "fail",
        "role": role,
        "criteria": criteria,
        "completed_call_rate": completed_rates,
        "accepted_call_rate": accepted_rates,
        "warning_order_rate": warning_rates,
        "emitted_warning_order_rate": emitted_warning_rates,
        "submitted_warning_order_rate": submitted_warning_rates,
        "sweep_test": {
            "winner": winner,
            "winner_sweeps": winner_sweeps,
            "loser": loser,
            "loser_sweeps": loser_sweeps,
            "one_sided_p": sweep_p,
        },
        "blueprint_behavior": behavior_gap,
    }


def _strategy_summary(specs: list[str], results: list[GameResult]) -> dict:
    per: dict[str, dict] = {}
    for policy in specs:
        games = [r for r in results if any(f == policy for f in r.seats.values())]
        if not games:
            per[policy] = {}
            continue
        order_families: Counter = Counter()
        contact_turns: list[int] = []
        eliminated = 0
        territory_won = 0
        territory_lost = 0
        soldiers_curves: list[float] = []
        for game in games:
            for faction_id, seat in game.seats.items():
                if seat != policy:
                    continue
                for trace in game.traces:
                    if trace.get("faction_id") != faction_id:
                        continue
                    for order_type in trace.get("order_types", []):
                        order_families[order_type] += 1
                if game.contact_turn.get(faction_id, 0):
                    contact_turns.append(game.contact_turn[faction_id])
                if game.eliminated_at.get(faction_id, 0):
                    eliminated += 1
                if game.per_turn:
                    first_metrics = game.per_turn[0]["metrics"][faction_id]
                    last_metrics = game.metrics[faction_id]
                    territory_won += max(
                        0, last_metrics["controlled"] - first_metrics["controlled"]
                    )
                    territory_lost += max(
                        0, first_metrics["controlled"] - last_metrics["controlled"]
                    )
                mid = [
                    pt["metrics"][faction_id]["soldiers"]
                    for pt in game.per_turn
                    if pt["turn"] > game.turns_played // 2
                ]
                if mid:
                    soldiers_curves.append(sum(mid) / len(mid))
        per[policy] = {
            "order_families": dict(order_families),
            "first_contact_turn": _distribution(contact_turns),
            "eliminations": eliminated,
            "territory_won_total": territory_won,
            "territory_lost_total": territory_lost,
            "avg_midgame_soldiers": round(sum(soldiers_curves) / len(soldiers_curves), 1)
            if soldiers_curves
            else None,
        }
    return per


def _blueprint_diff_summary(specs: list[str], results: list[GameResult]) -> dict:
    """Compare the two seats directly on the behaviours the gate cares about:
    order families, time to first recruit/attack, soldiers and territory over
    time, contact, survival and result. A difference that only lives in the
    rationale text does not count -- it must show in orders or game state."""
    if len(specs) != 2:
        return {}
    diff: dict[str, dict] = {}
    for seat_label, policy in (("a", specs[0]), ("b", specs[1])):
        games = [r for r in results if any(f == policy for f in r.seats.values())]
        first_recruit: list[int] = []
        first_attack: list[int] = []
        recruit_total = attack_total = movement_total = secure_total = tax_total = 0
        contact_games = wins = survivals = 0
        for game in games:
            faction_id = next(f for f, s in game.seats.items() if s == policy)
            if game.winner == faction_id:
                wins += 1
            if not game.eliminated_at.get(faction_id, 0):
                survivals += 1
            if game.contact_turn.get(faction_id, 0):
                contact_games += 1
            for trace in game.traces:
                if trace.get("faction_id") != faction_id:
                    continue
                for order_type in trace.get("order_types", []):
                    if order_type == "RECRUIT":
                        recruit_total += 1
                        first_recruit.append(trace["turn"])
                    elif order_type == "ATTACK":
                        attack_total += 1
                        first_attack.append(trace["turn"])
                    elif order_type == "MOVE":
                        movement_total += 1
                    elif order_type == "SECURE":
                        secure_total += 1
                    elif order_type == "TAX":
                        tax_total += 1
        diff[seat_label] = {
            "policy": policy,
            "games": len(games),
            "wins": wins,
            "survival_rate": round(survivals / len(games), 3) if games else None,
            "contact_rate": round(contact_games / len(games), 3) if games else None,
            "orders": {
                "recruit": recruit_total,
                "attack": attack_total,
                "movement": movement_total,
                "secure": secure_total,
                "tax": tax_total,
            },
            "first_recruit_turn": _distribution(first_recruit),
            "first_attack_turn": _distribution(first_attack),
        }
    return diff


def _distribution(values: list[float | int]) -> dict | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    median = (
        ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    )
    return {
        "min": round(ordered[0], 1),
        "median": round(median, 1),
        "mean": round(sum(ordered) / n, 1),
        "max": round(ordered[-1], 1),
        "n": n,
    }


# ===========================================================================
# report
# ===========================================================================


def render_report(s: dict) -> str:
    a, b = s["policies"]
    decisive = s["games"] - s["draws"]
    lines = [
        "# Arena — head-to-head",
        "",
        f"- **Policies:** `{a}` vs `{b}`",
        f"- **Map:** {s['map']}",
        f"- **Games:** {s['games']} ({s['turns_per_game']} turns each, "
        "both seat orderings per seed)",
        f"- **Decisive:** {decisive}  ·  **Draws:** {s['draws']}",
        "",
        "## Win rate",
        "",
        "| Policy | Wins | Win rate | Submitted lines | Warned lines | Warning rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in s["policies"]:
        rate = s["win_rate"][p]
        warning_rate = s["warning_order_rate"][p]
        lines.append(
            f"| `{p}` | {s['wins'].get(p, 0)} | "
            f"{'—' if rate is None else f'{rate:.1%}'} | "
            f"{s['order_lines_total'][p]} | {s['warning_order_lines_total'][p]} | "
            f"{'—' if warning_rate is None else f'{warning_rate:.1%}'} |"
        )

    total_pairs = len(s["pairs"])
    lines += [
        "",
        "## Paired result (the signal)",
        "",
        "Each seed is played twice on the *same* map with the seats exchanged.",
        "A **sweep** — one policy winning from both seats — cannot be explained",
        "by start-city luck. A **split** is the map talking, not the policy.",
        "",
        "- **Sweeps:** "
        + ", ".join(f"`{p}` {s['pair_sweeps'][p]}" for p in s["policies"]),
        f"- **Splits:** {s['pair_splits']} / {total_pairs}",
        "",
        "## What decided each game",
        "",
        "| Metric | Games |",
        "|---|---:|",
    ]
    for key, n in sorted(s["decided_by"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {key} | {n} |")

    lines += [
        "",
        "| Seed | Seat-1-first winner | Seat-2-first winner | Verdict |",
        "|---|---|---|---|",
    ]
    for p in s["pairs"]:
        w = [x or "draw" for x in p["winners"]]
        verdict = p["verdict"] + (f" by {p['swept_by']}" if p["swept_by"] else "")
        lines.append(f"| `{p['code']}` | {w[0]} | {w[1]} | {verdict} |")

    lines += _render_reliability(s)
    lines += _render_order_quality(s)
    lines += _render_strategy(s)
    lines += _render_blueprint_diff(s)

    if s["errors"]:
        lines += ["", "## Errors", ""]
        lines += [f"- {e}" for e in s["errors"][:40]]

    lines += [
        "",
        "## Reading this",
        "",
        "The headline number is sweeps, not raw win rate. Raw win rate mixes",
        "skill with start-city luck; a sweep controls for the map.",
        "",
        "If `scripted` does not sweep clearly more often than `random`, the",
        "game has no skill gradient at this length, and that is a finding about",
        "the game rather than the policies: deliberate play and arbitrary legal",
        "play reach the same place, and no model could separate either. Any",
        "benchmark claim rests on this first.",
        "",
        "Watch `decided_by` too. If games are decided by `gold` rather than",
        "`secured`, the contest is an economic tiebreak, not a struggle for",
        "territory, and the scoring metric may be measuring the wrong thing.",
        "",
    ]
    return "\n".join(lines)


def _render_reliability(s: dict) -> list[str]:
    lines = ["", "## Reliability (LLM seats)", ""]
    reliability = s.get("reliability", {})
    has_llm = any(
        value and not value.get("n_a") for value in reliability.values()
    )
    if not has_llm:
        return lines + ["No model calls in this run; see strategy section."]
    lines.append("| Policy | Calls | Completed | Failures | Accepted | No-op turns | Retried |")
    lines.append("|---|---:|---:|---|---:|---:|---:|")
    for policy, value in reliability.items():
        if value.get("n_a"):
            continue
        failures = ", ".join(
            f"{cls}={n}" for cls, n in sorted(value["call_failures"].items())
        ) or "—"
        lines.append(
            f"| `{policy}` | {value['calls_attempted']} | {value['calls_completed']} "
            f"| {failures} | "
            f"{value.get('accepted_call_rate', value['parseable_call_rate']):.1%} | "
            f"{value['no_op_turns']} | {value['retried_calls']} |"
        )
    lines += [
        "",
        "| Policy | Latency ms (median) | Tokens in | Tokens out | Cost |",
        "|---|---:|---:|---:|---:|",
    ]
    for policy, value in reliability.items():
        if value.get("n_a"):
            continue
        latency = value["latency_ms"]
        tokens = value["tokens"]
        cost = value["cost"]
        lines.append(
            f"| `{policy}` | {latency['median'] if latency else '—'} | "
            f"{tokens.get('prompt_tokens', '—')} | "
            f"{tokens.get('completion_tokens', '—')} | "
            f"{cost if cost is not None else 'unknown'} |"
        )
    return lines


def _render_order_quality(s: dict) -> list[str]:
    lines = ["", "## Emitted order quality (before safety filtering)", ""]
    quality = s.get("emitted_order_quality", {})
    model_rows = [
        (policy, value)
        for policy, value in quality.items()
        if value and not value.get("n_a")
    ]
    if not model_rows:
        return lines + ["No model-emitted orders in this run."]
    lines += [
        "| Policy | Emitted lines | Warned lines | Warning messages | Warned-line rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for policy, value in model_rows:
        rate = value.get("warning_order_rate")
        lines.append(
            f"| `{policy}` | {value['order_lines']} | "
            f"{value['warning_order_lines']} | {value['warning_messages']} | "
            f"{'—' if rate is None else f'{rate:.1%}'} |"
        )
    lines += [
        "",
        "The Phase 0 threshold is at most 5% of emitted order lines carrying "
        "one or more warnings. Multiple messages on one line count once.",
    ]
    return lines


def _render_strategy(s: dict) -> list[str]:
    lines = ["", "## Strategy (per policy)", ""]
    strategy = s.get("strategy", {})
    lines.append(
        "| Policy | Order families | First contact (median) | Eliminations | "
        "Territory +/− | Midgame soldiers |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for policy in s["policies"]:
        value = strategy.get(policy, {})
        families = ", ".join(
            f"{key}={n}" for key, n in sorted(value.get("order_families", {}).items())
        )
        contact = value.get("first_contact_turn")
        lines.append(
            f"| `{policy}` | {families or '—'} | "
            f"{contact['median'] if contact else '—'} | "
            f"{value.get('eliminations', 0)} | "
            f"+{value.get('territory_won_total', 0)}/"
            f"−{value.get('territory_lost_total', 0)} | "
            f"{value.get('avg_midgame_soldiers', '—')} |"
        )
    return lines


def _render_blueprint_diff(s: dict) -> list[str]:
    diff = s.get("blueprint_diff", {})
    if not diff:
        return []
    lines = ["", "## Blueprint differentiation", ""]
    lines.append(
        "The gate requires the difference to show in orders or game state, "
        "not only in the rationale text."
    )
    lines.append("")
    lines.append(
        "| Blueprint | Wins | Survival | Contact | Recruit | Attack | "
        "Movement | Secure | Tax |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for seat_label in ("a", "b"):
        value = diff.get(seat_label) or {}
        orders = value.get("orders", {})
        lines.append(
            f"| `{value.get('policy', seat_label)}` | {value.get('wins', 0)} | "
            f"{value.get('survival_rate', '—')} | {value.get('contact_rate', '—')} | "
            f"{orders.get('recruit', '—')} | {orders.get('attack', '—')} | "
            f"{orders.get('movement', '—')} | {orders.get('secure', '—')} | "
            f"{orders.get('tax', '—')} |"
        )
    lines.append("")
    lines.append("| Blueprint | First recruit (median) | First attack (median) |")
    lines.append("|---|---:|---:|")
    for seat_label in ("a", "b"):
        value = diff.get(seat_label) or {}
        first_recruit = value.get("first_recruit_turn")
        first_attack = value.get("first_attack_turn")
        lines.append(
            f"| `{value.get('policy', seat_label)}` | "
            f"{first_recruit['median'] if first_recruit else '—'} | "
            f"{first_attack['median'] if first_attack else '—'} |"
        )
    return lines


# ===========================================================================
# config + bundle glue
# ===========================================================================


def load_phase0_gate(path: Path = PHASE0_GATE_PATH) -> dict:
    """Load the frozen Phase 0 scenario and official-run contract."""
    gate = load_config(path)
    if gate.get("status") != "frozen":
        raise BundleError(f"Phase 0 gate is not frozen: {path}")
    return gate


def validate_official_preflight(config: dict) -> None:
    """Refuse an official candidate that cannot satisfy the gate by design."""
    mode = str(config.get("mode", ""))
    if not mode.startswith("official_"):
        return

    from scripts.arena_bundle import file_sha256, git_provenance
    from webapp.ai import brain

    gate = load_phase0_gate()
    role = str(config.get("gate_role", ""))
    contract = (gate.get("official_runs") or {}).get(role)
    if not isinstance(contract, dict):
        raise BundleError(f"Unknown Phase 0 official gate role: {role!r}")

    map_name = str(config.get("map", ""))
    if map_name != gate.get("map"):
        raise BundleError(
            f"Official Phase 0 map must be {gate.get('map')!r}, got {map_name!r}"
        )
    map_path = _REPO_ROOT / "maps" / map_name
    actual_hash = file_sha256(map_path)
    if actual_hash != str(gate.get("map_sha256", "")):
        raise BundleError(
            "Official Phase 0 map hash changed "
            f"(frozen={gate.get('map_sha256')}, current={actual_hash})"
        )
    if int(config.get("turns", 0)) != int(gate.get("turns", 0)):
        raise BundleError(f"Official Phase 0 runs require {gate.get('turns')} turns")
    if int(config.get("seed_pairs", 0)) < int(gate.get("minimum_seed_pairs", 40)):
        raise BundleError(
            "Official Phase 0 runs require at least "
            f"{gate.get('minimum_seed_pairs', 40)} seed pairs"
        )

    entrants = config.get("entrants", [])
    if not isinstance(entrants, list) or len(entrants) != 2:
        raise BundleError("Official Phase 0 runs require exactly two entrants")
    expected_opponent = contract.get("opponent")
    if expected_opponent:
        actual_opponent = _entrant_from_spec(expected_opponent)
        if entrants[1] != actual_opponent:
            raise BundleError(
                f"Official competence opponent must be {expected_opponent}"
            )
    expected_blueprints = contract.get("blueprints")
    if expected_blueprints:
        actual_blueprints = [entrant.get("blueprint") for entrant in entrants]
        if actual_blueprints != expected_blueprints or any(
            entrant.get("type") != "llm" for entrant in entrants
        ):
            raise BundleError(
                "Official blueprint run must use the frozen blueprint pair "
                f"{expected_blueprints}"
            )
    frozen_blueprints = gate.get("blueprint_sha256", {})
    for entrant in entrants:
        blueprint_id = entrant.get("blueprint")
        if not blueprint_id:
            continue
        expected_hash = frozen_blueprints.get(blueprint_id)
        actual_blueprint_hash = file_sha256(blueprint_path(blueprint_id))
        if not expected_hash or actual_blueprint_hash != expected_hash:
            raise BundleError(
                f"Official blueprint {blueprint_id!r} changed "
                f"(frozen={expected_hash}, current={actual_blueprint_hash})"
            )

    provenance = git_provenance(_REPO_ROOT)
    if provenance.get("git_dirty"):
        raise BundleError(
            "Official Phase 0 runs require a clean worktree; commit or remove "
            "all changes before starting"
        )

    llm_entrants = [entrant for entrant in entrants if entrant.get("type") == "llm"]
    if not llm_entrants or not brain.is_configured():
        raise BundleError("SOE_LLM_KEY must be configured before an official run")
    try:
        receipt = json.loads(PHASE0_PROBE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(
            "Official Phase 0 runs require a successful recent model probe: "
            "python scripts/probe_model.py <model>"
        ) from exc
    probes = receipt.get("probes", {}) if isinstance(receipt, dict) else {}
    now = datetime.now(timezone.utc)
    for model_name in {str(entrant.get("model", "")) for entrant in llm_entrants}:
        probe = probes.get(model_name) if isinstance(probes, dict) else None
        try:
            checked_at = datetime.fromisoformat(
                str((probe or {}).get("checked_at", "")).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise BundleError(f"No valid probe receipt for official model {model_name}") from exc
        age_hours = (now - checked_at.astimezone(timezone.utc)).total_seconds() / 3600
        if not (probe or {}).get("success") or not 0 <= age_hours <= PHASE0_PROBE_MAX_AGE_HOURS:
            raise BundleError(
                f"Probe for {model_name} is missing, failed, or older than "
                f"{PHASE0_PROBE_MAX_AGE_HOURS} hours"
            )
    if config.get("max_spend_usd") is None:
        raise BundleError("Official Phase 0 runs require a max_spend_usd ceiling")

def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime(
        "run-%Y%m%d-%H%M%S"
    ) + "-" + uuid.uuid4().hex[:6]


def _blueprint_prompt_hashes(config: dict) -> tuple[dict, dict[str, str]]:
    """Hash of every referenced blueprint file and its prompt contribution."""
    from webapp.ai import context

    blueprint_hashes: dict[str, str] = {}
    prompt_hashes: dict[str, str] = {}
    for entrant in config.get("entrants", []):
        label, blueprint = entrant_blueprint(entrant)
        if not label or blueprint is None:
            continue
        if isinstance(entrant.get("blueprint_inline"), dict):
            blueprint_hashes[label] = _inline_blueprint_hash(blueprint)
        else:
            path = blueprint_path(label)
            if not path.exists():
                raise ValueError(f"Blueprint file not found: {path}")
            blueprint_hashes[label] = hashlib.sha256(path.read_bytes()).hexdigest()
        prompt_hashes[label] = context.prompt_signature(
            context.doctrine_section(blueprint)
        )
    return blueprint_hashes, prompt_hashes


def _inline_blueprint_hash(payload: dict) -> str:
    """Hash of a blueprint held by value, over the bytes the bundle stores."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def manifest_fields(config: dict) -> dict:
    from webapp.ai import brain

    from scripts.arena_bundle import file_sha256

    map_path = _REPO_ROOT / "maps" / config.get("map", "")
    if not map_path.exists():
        raise ValueError(f"Map file not found: {map_path}")
    blueprint_hashes, prompt_hashes = _blueprint_prompt_hashes(config)
    llm_models = [
        entrant.get("model", "")
        for entrant in config.get("entrants", [])
        if entrant.get("type") == "llm"
    ]
    return {
        "mode": config.get("mode", "smoke"),
        "map": config.get("map", ""),
        "map_hash": file_sha256(map_path),
        "prompt_hashes": prompt_hashes or {"none": "no-llm-entrant"},
        "blueprints": [
            {"id": blueprint_id, "hash": digest, "file": f"{blueprint_id}.json"}
            for blueprint_id, digest in blueprint_hashes.items()
        ],
        "model": llm_models[0] if llm_models else config.get("model", ""),
        "temperature": config.get("temperature", 0.0),
        "max_tokens": config.get("max_tokens", brain.MAX_OUTPUT_TOKENS),
        "retry_policy": {
            "max_retries": brain.MAX_RETRIES,
            "timeout_seconds": brain.TIMEOUT_SECONDS,
        },
        "seed_pairs": int(config.get("seed_pairs", 4)),
        "turns": int(config.get("turns", 30)),
        "entrants": config.get("entrants", []),
        "max_spend_usd": config.get("max_spend_usd"),
        "seats": [
            entrant.get("type", "") for entrant in config.get("entrants", [])
        ],
    }


def prepare_bundle(config: dict, output: Path, run_id: str | None = None) -> "RunBundle":
    """Create the run bundle with its frozen manifest (WP4)."""
    from scripts.arena_bundle import RunBundle, git_provenance

    validate_official_preflight(config)
    # Capture provenance before creating files under the repository. Otherwise
    # an unignored output directory can make a clean run describe itself as
    # dirty merely because it started writing its own evidence bundle.
    provenance = git_provenance(_REPO_ROOT)
    run_id = run_id or new_run_id()
    run_dir = output / run_id
    bundle = RunBundle(run_dir)

    blueprint_paths: dict[str, Path] = {}
    inline_blueprints: dict[str, dict] = {}
    for entrant in config.get("entrants", []):
        label, blueprint = entrant_blueprint(entrant)
        if not label or blueprint is None:
            continue
        if isinstance(entrant.get("blueprint_inline"), dict):
            inline_blueprints[label] = blueprint
        else:
            blueprint_paths[label] = blueprint_path(label)
    for blueprint_id, path in blueprint_paths.items():
        if not path.exists():
            raise ValueError(f"Blueprint file not found: {path}")

    fields = manifest_fields(config)
    fields["blueprints"] = bundle.copy_blueprints(
        blueprint_paths
    ) + bundle.write_blueprints(inline_blueprints)
    fields.update(provenance)
    return RunBundle.start(run_dir, fields)


def resume_bundle(output: Path, run_id: str, config: dict) -> "RunBundle":
    """Open an existing bundle, verifying provenance before replay (WP4)."""
    from scripts.arena_bundle import RunBundle, validate_resume_bundle

    bundle = RunBundle(output / run_id)
    expected = manifest_fields(config)
    expected["schema_version"] = "1"
    validate_resume_bundle(bundle, expected, _REPO_ROOT)
    return bundle


def load_config(path: Path) -> dict:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unreadable run config: {path}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"Run config must be a JSON object: {path}")
    return config


def _confirm_run(config: dict, model: str, bundle) -> bool:
    """Model and spend ceiling are visible before a real run starts."""
    print()
    print("Run summary:")
    print(f"  mode        {config.get('mode', 'smoke')}")
    print(f"  map         {config.get('map')}  turns {config.get('turns')}")
    print(f"  seed pairs  {config.get('seed_pairs')}")
    print(f"  model       {model or '(no LLM entrant)'}")
    ceiling = config.get("max_spend_usd")
    print(f"  max spend   {ceiling if ceiling is not None else 'unlimited'}")
    print(f"  bundle      {bundle.run_dir if bundle else 'none'}")
    from webapp.ai import brain

    if model and not brain.is_configured():
        print("  WARNING: SOE_LLM_KEY is not set; the LLM seat will no-op.")
    try:
        answer = input("  Confirm real run (y/N)? ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  Run not confirmed; aborting.")
        return False
    return answer in ("y", "yes")


# ===========================================================================
# cli
# ===========================================================================


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--policies",
        default="",
        help="two comma-separated policy specs (legacy: scripted,random)",
    )
    ap.add_argument("--seeds", type=int, default=40, help="distinct map situations")
    ap.add_argument("--turns", type=int, default=30, help="turns per game")
    ap.add_argument("--map", default="", help="map file (default: engine default)")
    ap.add_argument(
        "--config",
        type=Path,
        default=None,
        help="JSON run config (mode, map, turns, seed_pairs, entrants)",
    )
    ap.add_argument(
        "--resume",
        type=str,
        default="",
        help="resume an existing run by its run id",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive confirmation of a real LLM run",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"bundle/report directory (default: {DEFAULT_OUTPUT})",
    )
    ap.add_argument(
        "--keep-games",
        action="store_true",
        help="keep the per-game state dirs (default: discard, they are large)",
    )
    args = ap.parse_args()

    # Isolation must be in place before webapp binds its module-level paths.
    workdir = Path(tempfile.mkdtemp(prefix="soe_arena_"))
    os.environ["SOE_DATA_DIR"] = str(workdir / "server_data")
    os.environ["SOE_GAMES_DIR"] = str(workdir / "games")
    # The dashboard's LLM setup (server_data/llm_settings.json) applies to
    # headless runs too; only the key from that file is bridged, nothing else.
    os.environ.setdefault(
        "SOE_LLM_SETTINGS_FILE",
        str(_REPO_ROOT / "server_data" / "llm_settings.json"),
    )

    from webapp import service

    try:
        return _run(args, service)
    finally:
        if args.keep_games:
            print(f"Game data kept at {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def _run(args, service) -> int:
    if args.resume and args.config is None:
        raise SystemExit(
            "--resume needs the original run config: "
            "python scripts/arena.py --resume <run_id> --config <config>"
        )
    if args.config is not None:
        config = load_config(args.config)
        config.setdefault("map", service.default_map())
        return _run_config(args, config)
    return _run_legacy(args, service)


def _run_legacy(args, service) -> int:
    specs = [
        build_policy(s.strip()).name
        for s in args.policies.split(",")
        if s.strip()
    ]
    if len(specs) != 2:
        specs = ["scripted", "random"]
    if any(s.startswith("llm:") for s in specs):
        raise SystemExit(
            "LLM seats need a run config (--config); legacy flags do not "
            "carry budgets, blueprints or bundle guarantees."
        )
    config = {
        "mode": "legacy",
        "map": args.map or service.default_map(),
        "turns": args.turns,
        "seed_pairs": args.seeds,
        "entrants": [_entrant_from_spec(s) for s in specs],
    }
    summary = run_batch(config, args.out)
    decisive = summary["games"] - summary["draws"]
    print(f"\nReport: {args.out / 'ARENA_REPORT.md'}")
    return 0 if decisive else 1


def _entrant_from_spec(spec: str) -> dict:
    head, _, tail = spec.partition(":")
    if head == "random":
        return {"type": "random"}
    if head == "scripted":
        return {"type": "scripted", "style": tail.strip().lower() or "balanced"}
    model, _, blueprint_id = tail.partition(":")
    return {"type": "llm", "model": model.strip(), "blueprint": blueprint_id.strip()}


def _run_config(args, config: dict) -> int:
    policies = build_policies_from_config(config)
    if len(policies) != 2:
        raise ValueError("Phase 0 compares exactly two policies")
    has_llm = any(isinstance(p, LLMPolicy) for p in policies)
    model = next((p.model for p in policies if isinstance(p, LLMPolicy)), "")

    try:
        if args.resume:
            bundle = resume_bundle(args.out, args.resume, config)
        else:
            bundle = prepare_bundle(config, args.out)
    except BundleError as exc:
        raise SystemExit(f"Arena preflight failed: {exc}") from None
    if not args.resume:
        if has_llm and not args.yes:
            if not _confirm_run(config, model, bundle):
                bundle.finish("cancelled")
                print("Run cancelled by operator.")
                return 0

    summary = run_batch(config, bundle.run_dir, bundle=bundle)
    decisive = summary["games"] - summary["draws"]
    print(f"\nReport: {bundle.run_dir / 'ARENA_REPORT.md'}")
    return 0 if decisive else 1


if __name__ == "__main__":
    raise SystemExit(main())
