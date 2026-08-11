#!/usr/bin/env python
"""
Headless arena: batch games between pluggable seat policies.

The benchmark thesis is that this game separates strong play from weak play.
Nothing has ever tested that. This harness is the test: it seats policies
against each other over many maps, swaps seats to cancel positional
advantage, and reports a head-to-head win-rate matrix.

Phase 0 uses only free policies -- ``scripted`` (the heuristic bot from
``beta_100_turns``) and ``random`` (legal orders, no strategy). If the
scripted bot cannot reliably beat random, the game has no skill gradient and
no model will find one. That question costs nothing to answer, so it is
answered first.

Runs against ``webapp.service`` directly: no server, no HTTP, no autoplay
pacing. Isolation is by ``SOE_DATA_DIR``/``SOE_GAMES_DIR``, which must be set
before ``webapp`` is imported -- hence the deferred imports below.

    python scripts/arena.py --seeds 8 --turns 30
    python scripts/arena.py --policies scripted:military,scripted:religious
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_OUTPUT = _REPO_ROOT / "games" / "arena"

# Rendered maps and reports are irrelevant here and cost real time per turn.
os.environ.setdefault("SOE_BOT_VISION", "")


# ===========================================================================
# policies
# ===========================================================================

# The order forms a policy may emit. Deliberately the same whitelist the
# strategist prompt gives an LLM (webapp/ai/orchestrator.py::_system_prompt),
# so a random baseline and a model are drawing from one vocabulary and the
# comparison is about choosing well, not about knowing the syntax.
SKILLS = ("combat", "magic", "religion")
RESOURCES = ("wood", "stone")


class Policy:
    """Decides one faction's orders for one turn."""

    #: identifies the policy in results and matchup keys
    name = "policy"

    def orders(self, gs, faction_id: str, turn: int, rng: random.Random) -> str:
        raise NotImplementedError

    # A policy may fail (a model can refuse, time out, or emit garbage).
    # Failures are recorded, never raised: a bot that cannot play should lose,
    # not crash the batch.
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

    def orders(self, gs, faction_id: str, turn: int, rng: random.Random) -> str:
        from scripts import beta_100_turns

        return beta_100_turns.plan_orders(gs, faction_id, self.style, rng)


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

    def orders(self, gs, faction_id: str, turn: int, rng: random.Random) -> str:
        leader = _leader(gs, faction_id)
        if leader is None:
            return "# no living characters\n"

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
        return f"# random baseline, turn {turn}\n" + "\n".join(lines) + "\n"


def build_policy(spec: str) -> Policy:
    """``scripted``, ``scripted:military``, ``random`` -> a Policy."""
    head, _, tail = spec.partition(":")
    head = head.strip().lower()
    if head == "random":
        return RandomPolicy()
    if head == "scripted":
        return ScriptedPolicy(tail.strip().lower() or "balanced")
    raise ValueError(
        f"Unknown policy '{spec}'. Phase 0 supports: random, "
        "scripted[:balanced|military|religious]"
    )


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


# ===========================================================================
# scoring
# ===========================================================================

# Win rate is the headline score: ordinal, needs no weighting argument, and
# hard to game. The tiebreak chain only decides games the primary metric ties.
TIEBREAK = ("secured", "gold", "soldiers", "characters_alive")


def decide_winner(metrics: dict[str, dict]) -> str | None:
    """Faction id of the winner, or None for a genuine draw."""
    ranked = sorted(
        metrics.items(),
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
    warnings: Counter = field(default_factory=Counter)
    parsed_orders: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)
    wall_seconds: float = 0.0

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


def play_game(
    code: str,
    map_file: str,
    policies: list[Policy],
    turns: int,
    seed: int,
) -> GameResult:
    """Create a room, run ``turns`` turns, return the result."""
    from webapp import rooms as rooms_mod
    from webapp import service
    from soe import storage

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

    seats = {p.faction_id: policies[i].name for i, p in enumerate(players)}
    warnings: Counter = Counter()
    parsed: Counter = Counter()
    errors: list[str] = []
    played = 0

    for turn in range(1, turns + 1):
        gs = service.load_state(room)
        for i, player in enumerate(players):
            policy = policies[i]
            # Seeded per seat and turn so a rerun of the same matchup is
            # byte-identical -- the engine is deterministic and the arena
            # must not be the thing that introduces noise.
            rng = random.Random(f"{seed}:{code}:{player.faction_id}:{turn}")
            try:
                text = policy.orders(gs, player.faction_id, turn, rng)
            except Exception as exc:  # noqa: BLE001 - a broken policy loses, not crashes
                errors.append(f"turn {turn} {policy.name}: {type(exc).__name__}: {exc}")
                text = f"# policy error on turn {turn}\n"
            feedback = service.submit_orders(room, player, text)
            warnings[policy.name] += len(feedback.get("warnings", []))
            parsed[policy.name] += int(feedback.get("parsed", 0))

        try:
            service.resolve_turn(room)
            played = turn
        except Exception as exc:  # noqa: BLE001 - report the stall, keep the batch alive
            errors.append(f"resolve turn {turn}: {type(exc).__name__}: {exc}")
            break

    final = storage.load_game_state(room.game_dir())
    metrics = {p.faction_id: _faction_metrics(final, p.faction_id) for p in players}

    return GameResult(
        code=code,
        map_file=map_file,
        turns_played=played,
        seats=seats,
        metrics=metrics,
        winner=decide_winner(metrics),
        warnings=warnings,
        parsed_orders=parsed,
        errors=errors,
        wall_seconds=round(time.time() - started, 2),
    )


# ===========================================================================
# batch
# ===========================================================================


def run_batch(
    specs: list[str],
    seeds: int,
    turns: int,
    map_file: str,
    output: Path,
) -> dict:
    """Play every seed as a *pair*: same map, seats exchanged.

    Start-city quality dominates short games, so a single game says almost
    nothing about the policies. A pair does: if one policy wins from both
    seats of the same map, the map cannot explain it.
    """
    if len(specs) != 2:
        raise ValueError("Phase 0 compares exactly two policies")
    if specs[0] == specs[1]:
        raise ValueError("The two policies must differ")

    results: list[GameResult] = []
    pairs: list[dict] = []

    for seed in range(seeds):
        code = f"AR{seed:03d}"
        pair_winners: list[str | None] = []
        for ordering in ((specs[0], specs[1]), (specs[1], specs[0])):
            policies = [build_policy(s) for s in ordering]
            result = play_game(code, map_file, policies, turns, seed)
            results.append(result)
            pair_winners.append(result.winner_policy())
            print(
                f"  {code}  {ordering[0]:<22} vs {ordering[1]:<22} "
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

    return summarise(specs, results, pairs, turns, map_file, output)


def summarise(
    specs: list[str],
    results: list[GameResult],
    pairs: list[dict],
    turns: int,
    map_file: str,
    output: Path,
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
            }
            for r in results
        ],
    }

    output.mkdir(parents=True, exist_ok=True)
    (output / "arena_results.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output / "ARENA_REPORT.md").write_text(render_report(summary), encoding="utf-8")
    return summary


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
        "| Policy | Wins | Win rate (decisive games) | Orders parsed | Warnings |",
        "|---|---:|---:|---:|---:|",
    ]
    for p in s["policies"]:
        rate = s["win_rate"][p]
        lines.append(
            f"| `{p}` | {s['wins'].get(p, 0)} | "
            f"{'—' if rate is None else f'{rate:.1%}'} | "
            f"{s['parsed_orders_total'][p]} | {s['warnings_total'][p]} |"
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


# ===========================================================================
# cli
# ===========================================================================


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--policies",
        default="scripted,random",
        help="two comma-separated policy specs (default: scripted,random)",
    )
    ap.add_argument("--seeds", type=int, default=8, help="distinct map situations")
    ap.add_argument("--turns", type=int, default=30, help="turns per game")
    ap.add_argument("--map", default="", help="map file (default: engine default)")
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"report directory (default: {DEFAULT_OUTPUT})",
    )
    ap.add_argument(
        "--keep-games",
        action="store_true",
        help="keep the per-game state dirs (default: discard, they are large)",
    )
    args = ap.parse_args()

    # Resolve to canonical names up front ("scripted" -> "scripted:balanced")
    # so matchup keys, result seats and the win tally all agree.
    specs = [
        build_policy(s.strip()).name
        for s in args.policies.split(",")
        if s.strip()
    ]

    # Isolation must be in place before webapp binds its module-level paths.
    workdir = Path(tempfile.mkdtemp(prefix="soe_arena_"))
    os.environ["SOE_DATA_DIR"] = str(workdir / "server_data")
    os.environ["SOE_GAMES_DIR"] = str(workdir / "games")

    from webapp import service

    map_file = args.map or service.default_map()

    print(f"Arena: {specs[0]} vs {specs[1]}")
    print(f"  map={map_file} seeds={args.seeds} turns={args.turns}")
    print(f"  workdir={workdir}")
    try:
        summary = run_batch(specs, args.seeds, args.turns, map_file, args.out)
    finally:
        if args.keep_games:
            print(f"Game data kept at {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    print()
    decisive = summary["games"] - summary["draws"]
    for p in specs:
        rate = summary["win_rate"][p]
        print(
            f"  {p:<22} {summary['wins'].get(p, 0):>3} wins  "
            f"{'—' if rate is None else f'{rate:.1%}'}"
        )
    print(f"  draws: {summary['draws']} / {summary['games']}")
    print(f"\nReport: {args.out / 'ARENA_REPORT.md'}")
    return 0 if decisive else 1


if __name__ == "__main__":
    raise SystemExit(main())
