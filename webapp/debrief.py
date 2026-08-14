"""
Debrief — what the coach's agent actually did, read back from the record.

This is the *understand* half of the Phase 2 loop. It computes nothing from a
live game: every field here is read out of the run bundle
(``manifest.json``, ``games.jsonl``, ``turns.jsonl``, ``decisions/``,
``arena_results.json``) or derived from those by arithmetic the coach could
repeat. If a number cannot be traced to the record, it does not belong here.

Three rules shape the module.

**One seat, not two.** The bundle is the operator's record of a match and holds
both sides. A coach's debrief is a view from their own seat: the opponent's
orders, per-turn position and faction id never enter the payload. The result is
reported as won, lost or drawn, because that much the coach played through.

**The rationale is derived, not asked.** A model asked to explain itself will
oblige, and the explanation is a second generation, not evidence. Phase 2 wants
a synthetic rationale separate from the orders; this builds one from what was
issued and what visibly moved. It is dull and it is true, and it costs no
tokens and no change to the frozen Phase 0 prompt.

**Errors are named by kind.** A line the parser threw out, a provider that
returned 429, and a turn of legal orders that changed nothing are three
different failures with three different fixes, and a coach who cannot tell them
apart will rewrite doctrine to fix a rate limit.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Faction metrics the arena records each turn, grouped the way a coach reads
#: them. The keys are exactly ``scripts.arena._faction_metrics``.
METRIC_GROUPS = {
    "territory": ("secured", "controlled"),
    "army": ("soldiers", "characters_alive"),
    "economy": ("gold",),
}
TRACKED_METRICS = tuple(key for group in METRIC_GROUPS.values() for key in group)

#: How many offending lines to carry as examples. A debrief is for reading.
MAX_EXAMPLES = 5

#: Provider failure classes the arena records, in the order a coach should read
#: them: the first two are the operator's problem, the rest are the model's.
PROVIDER_FAILURES = (
    "not_configured",
    "budget_exhausted",
    "http_429",
    "http_4xx",
    "http_5xx",
    "transport",
    "parse_error",
    "unknown",
)


class DebriefError(Exception):
    """The run bundle cannot be read back."""


# ======================================================================
# views
# ======================================================================


@dataclass(frozen=True)
class TurnView:
    turn: int
    #: Order lines the model wrote, after the orders marker.
    proposed: list[str]
    #: Proposed lines the engine could not use. These never reached the game.
    discarded: list[str]
    #: Lines that were submitted to the engine.
    accepted: list[str]
    warnings: list[str]
    #: This faction's position at the end of the turn.
    position: dict
    #: Change since the previous recorded turn. None on the first turn, where
    #: there is nothing recorded to subtract from.
    effect: dict | None
    #: One derived sentence. Not the model's words.
    rationale: str
    provider_failure: dict | None
    latency_ms: float | None
    cost_usd: float | None


@dataclass(frozen=True)
class GameView:
    game_id: str
    code: str
    #: The coach's own seat. The opponent's faction id is deliberately absent.
    seat: str
    outcome: str  # won | lost | drawn
    turns_played: int
    final_position: dict
    turns: list[TurnView] = field(default_factory=list)


@dataclass(frozen=True)
class Debrief:
    run_id: str
    blueprint_id: str
    blueprint_version: int
    content_hash: str
    scenario_id: str
    opponent: str
    model: str
    map_file: str
    headline: dict
    cost: dict
    reliability: dict
    errors: dict
    games: list[GameView] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ======================================================================
# reading the bundle
# ======================================================================


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DebriefError(f"Unreadable run record: {path}") from exc


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise DebriefError(f"Truncated run record: {path}") from exc
    return records


def order_lines(text: str) -> list[str]:
    """The order lines of a block: no blanks, no comments, no marker noise."""
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or set(line) <= set("-*_= "):
            continue
        lines.append(line)
    return lines


def _discarded(proposed: list[str], accepted: list[str]) -> list[str]:
    """Proposed lines that did not survive to the engine, order preserved.

    A multiset difference rather than a set one: a model that writes the same
    order twice and has one copy dropped has lost one order, not both.
    """
    remaining = list(accepted)
    dropped = []
    for line in proposed:
        if line in remaining:
            remaining.remove(line)
        else:
            dropped.append(line)
    return dropped


# ======================================================================
# the derived rationale
# ======================================================================


def _families(order_types: list[str]) -> str:
    counts: dict[str, int] = {}
    for name in order_types or []:
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(
        f"{name}x{n}" if n > 1 else name for name, n in sorted(counts.items())
    )


def _effect_phrase(effect: dict | None) -> str:
    if not effect:
        return ""
    moved = [
        f"{key} {value:+g}" for key, value in effect.items() if value
    ]
    return "; ".join(moved)


def derived_rationale(
    order_types: list[str],
    effect: dict | None,
    provider_failure: dict | None,
    discarded_count: int,
) -> str:
    """One sentence about a turn, built only from the record.

    Deliberately mechanical. A coach reading a hundred of these should be able
    to trust that nothing was inferred on their behalf.
    """
    if provider_failure:
        detail = provider_failure.get("failure_class", "unknown")
        return f"No orders: the provider call failed ({detail})."
    if not order_types:
        return "No orders were issued this turn."
    parts = [f"Issued {_families(order_types)}"]
    if discarded_count:
        parts.append(
            f"{discarded_count} proposed line{'s' if discarded_count > 1 else ''} "
            "did not reach the engine"
        )
    moved = _effect_phrase(effect)
    parts.append(f"position moved: {moved}" if moved else "nothing visible changed")
    return ". ".join(parts) + "."


# ======================================================================
# building the debrief
# ======================================================================


def build(run, bundle_dir: Path | None = None) -> Debrief:
    """The coach's view of one training run.

    ``run`` is a ``webapp.training.TrainingRun``; its bundle directory holds
    everything else.
    """
    root = Path(bundle_dir) if bundle_dir else run.bundle_dir()
    if not (root / "manifest.json").exists():
        raise DebriefError(
            f"Training run '{run.id}' has no record to read: {root} is missing "
            "its manifest."
        )
    manifest = _read_json(root / "manifest.json")
    summary = _read_json(root / "arena_results.json")
    games = _read_jsonl(root / "games.jsonl")
    turns = _read_jsonl(root / "turns.jsonl")

    label = f"{run.blueprint_id}_v{run.blueprint_version}"
    policy = _my_policy(summary, label)
    game_views = [
        _game_view(root, record, games, turns, policy)
        for record in _game_starts(games)
    ]
    return Debrief(
        run_id=run.run_id,
        blueprint_id=run.blueprint_id,
        blueprint_version=run.blueprint_version,
        content_hash=run.blueprint_hash,
        scenario_id=run.scenario_id,
        opponent=run.opponent,
        model=str(manifest.get("model", run.model)),
        map_file=str(manifest.get("map", "")),
        headline=_headline(summary, policy, game_views),
        cost=_cost(summary, policy),
        reliability=_reliability(summary, policy),
        errors=_errors(game_views, summary, policy),
        games=game_views,
    )


def _my_policy(summary: dict, label: str) -> str:
    policies = summary.get("policies") or []
    for name in policies:
        if name.endswith(label):
            return name
    if policies:
        return policies[0]
    raise DebriefError("The run summary names no policies.")


def _game_starts(games: list[dict]) -> list[dict]:
    return [g for g in games if g.get("event") != "result"]


def _my_seat(seats: dict, policy: str) -> str:
    for faction_id, name in (seats or {}).items():
        if name == policy:
            return faction_id
    raise DebriefError("The coach's policy does not hold a seat in this game.")


def _game_view(
    root: Path, start: dict, games: list[dict], turns: list[dict], policy: str
) -> GameView:
    game_id = start.get("game_id", "")
    seat = _my_seat(start.get("seats") or {}, policy)
    result = next(
        (
            g
            for g in games
            if g.get("game_id") == game_id and g.get("event") == "result"
        ),
        {},
    )
    winner = result.get("winner")
    outcome = "drawn" if not winner else ("won" if winner == seat else "lost")

    my_turns = sorted(
        (t for t in turns if t.get("game") == game_id), key=lambda t: t.get("turn", 0)
    )
    views: list[TurnView] = []
    previous: dict | None = None
    for record in my_turns:
        position = ((record.get("metrics") or {}).get(seat)) or {}
        effect = _delta(previous, position) if previous is not None else None
        views.append(
            _turn_view(root, game_id, record.get("turn", 0), seat, position, effect)
        )
        previous = position
    final = views[-1].position if views else {}
    return GameView(
        game_id=game_id,
        code=str(start.get("code", "")),
        seat=seat,
        outcome=outcome,
        turns_played=int(result.get("turns_played", len(views))),
        final_position=final,
        turns=views,
    )


def _delta(before: dict, after: dict) -> dict:
    return {
        key: round(float(after.get(key, 0)) - float(before.get(key, 0)), 2)
        for key in TRACKED_METRICS
    }


def _turn_view(
    root: Path, game_id: str, turn: int, seat: str, position: dict, effect: dict | None
) -> TurnView:
    path = root / "decisions" / game_id / f"turn_{turn}_{seat}.json"
    trace = _read_json(path) if path.exists() else {}
    proposed = order_lines(trace.get("orders_extracted_text", ""))
    accepted = order_lines(trace.get("orders_text", ""))
    failure = (
        {
            "failure_class": trace.get("failure_class", "unknown"),
            "detail": trace.get("failure_detail", ""),
        }
        if trace.get("failure_class")
        else None
    )
    discarded = _discarded(proposed, accepted)
    usage = trace.get("usage") or {}
    return TurnView(
        turn=turn,
        proposed=proposed,
        discarded=discarded,
        accepted=accepted,
        warnings=list(trace.get("warnings") or []),
        position=dict(position),
        effect=effect,
        rationale=derived_rationale(
            list(trace.get("order_types") or []), effect, failure, len(discarded)
        ),
        provider_failure=failure,
        latency_ms=trace.get("latency_ms"),
        cost_usd=usage.get("cost"),
    )


# ======================================================================
# aggregates, all read back from the summary
# ======================================================================


def _headline(summary: dict, policy: str, games: list[GameView]) -> dict:
    wins = summary.get("wins") or {}
    return {
        "games": summary.get("games", len(games)),
        "won": wins.get(policy, 0),
        "lost": sum(count for name, count in wins.items() if name != policy),
        "drawn": summary.get("draws", 0),
        "sweeps": (summary.get("pair_sweeps") or {}).get(policy, 0),
        "pairs": len(summary.get("pairs") or []),
        "decided_by": dict(summary.get("decided_by") or {}),
    }


def _policy_section(summary: dict, section: str, policy: str) -> dict:
    return dict((summary.get(section) or {}).get(policy) or {})


def _cost(summary: dict, policy: str) -> dict:
    reliability = _policy_section(summary, "reliability", policy)
    latency = reliability.get("latency_ms") or {}
    tokens = reliability.get("tokens") or {}
    return {
        "usd": reliability.get("cost"),
        "prompt_tokens": tokens.get("prompt_tokens"),
        "completion_tokens": tokens.get("completion_tokens"),
        "latency_ms_median": latency.get("median"),
        "latency_ms_max": latency.get("max"),
        "calls": reliability.get("calls_attempted"),
    }


def _reliability(summary: dict, policy: str) -> dict:
    reliability = _policy_section(summary, "reliability", policy)
    return {
        "calls_attempted": reliability.get("calls_attempted"),
        "calls_completed": reliability.get("calls_completed"),
        "accepted_call_rate": reliability.get("accepted_call_rate"),
        "no_op_turns": reliability.get("no_op_turns"),
        "retried_calls": reliability.get("retried_calls"),
        "call_failures": dict(reliability.get("call_failures") or {}),
    }


def _errors(games: list[GameView], summary: dict, policy: str) -> dict:
    """Three kinds, because they have three different fixes.

    *Syntax* is the coach's prompt: the agent wrote something the engine does
    not accept. *Provider* is nobody's doctrine. *Strategic* is the expensive
    one — legal orders, accepted by the engine, that moved nothing — and it is
    the only one worth rewriting a blueprint over.
    """
    discarded: list[str] = []
    warnings: list[str] = []
    provider: dict[str, int] = {}
    idle_turns = 0
    silent_turns = 0
    for game in games:
        for turn in game.turns:
            discarded.extend(turn.discarded)
            warnings.extend(turn.warnings)
            if turn.provider_failure:
                key = turn.provider_failure.get("failure_class", "unknown")
                provider[key] = provider.get(key, 0) + 1
                continue
            if not turn.accepted:
                silent_turns += 1
            elif turn.effect is not None and not any(turn.effect.values()):
                idle_turns += 1
    return {
        "syntax": {
            "discarded_lines": len(discarded),
            "warned_orders": len(warnings),
            "examples": discarded[:MAX_EXAMPLES],
            "warning_examples": warnings[:MAX_EXAMPLES],
        },
        "provider": {
            "failures": {key: provider[key] for key in PROVIDER_FAILURES if key in provider},
            "total": sum(provider.values()),
        },
        "strategic": {
            "silent_turns": silent_turns,
            "idle_turns": idle_turns,
            "note": (
                "A silent turn issued nothing the engine could run. An idle "
                "turn ran legal orders that changed no tracked metric."
            ),
        },
    }


# ======================================================================
# comparing two versions
# ======================================================================


def compare(left: Debrief, right: Debrief) -> dict:
    """Two runs of the same blueprint, side by side.

    Only meaningful across the same scenario: a version that trained against
    the aggressor and one that trained against the wild card have not been
    asked the same question, and the comparison says so rather than averaging
    over it.
    """
    return {
        "blueprint_id": left.blueprint_id,
        "same_blueprint": left.blueprint_id == right.blueprint_id,
        "same_scenario": left.scenario_id == right.scenario_id,
        "versions": [left.blueprint_version, right.blueprint_version],
        "content_hashes": [left.content_hash, right.content_hash],
        "sides": [_side(left), _side(right)],
        "deltas": {
            "won": _side(right)["won"] - _side(left)["won"],
            "sweeps": _side(right)["sweeps"] - _side(left)["sweeps"],
            "discarded_lines": (
                right.errors["syntax"]["discarded_lines"]
                - left.errors["syntax"]["discarded_lines"]
            ),
            "idle_turns": (
                right.errors["strategic"]["idle_turns"]
                - left.errors["strategic"]["idle_turns"]
            ),
        },
    }


def _side(debrief: Debrief) -> dict:
    finals = [game.final_position for game in debrief.games if game.final_position]
    return {
        "run_id": debrief.run_id,
        "version": debrief.blueprint_version,
        "scenario_id": debrief.scenario_id,
        "games": debrief.headline["games"],
        "won": debrief.headline["won"],
        "sweeps": debrief.headline["sweeps"],
        "cost_usd": debrief.cost["usd"],
        "median_final": {
            key: round(statistics.median([float(f.get(key, 0)) for f in finals]), 2)
            for key in TRACKED_METRICS
        }
        if finals
        else {},
    }
