"""Reconstruct one finished arena match and export a sanitised public replay.

`MARKETING_CLOSED_ALPHA.md` blocks the poster on this script. A replay cannot
be copied out of a bundle: `turns.jsonl` stores state hashes and seeds, not
piece positions. What the bundle does hold is every seat's order text, and the
engine is deterministic, so the match can be *replayed* -- the same room code,
the same map, the same per-turn seed -- and the positions recovered on the way
through.

Two commands:

    python -m scripts.export_public_replay audit <bundle> [--limit N]
        Score candidate games on movement, contact, territorial change, and
        warning rate against the run's published rate. This is the
        "reconstruction audit" the field plan requires before a match is
        chosen. It does not default to any run.

    python -m scripts.export_public_replay export <bundle> <game_id> -o FILE
        Reconstruct one game and write one `soe.public_replay.v1` JSON.
        Refuses to write anything that fails the leakage test.

The reconstruction is checked against the bundle's recorded `state_sha` for
every turn. A mismatch aborts: a replay that diverged from the recorded match
is not that match, and the poster would be showing a game that never happened.

An exhibition (scripted versus scripted, no bundle) is also supported, for the
case the field plan anticipates where no official-gate game meets the visual
bar:

    python -m scripts.export_public_replay exhibition --seed 7 -o FILE
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import random
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _use_scratch_state() -> None:
    """Replay into a throwaway data directory, never the live one.

    Reconstruction has to build a room and a game directory to step the engine,
    and `arena._reset_game` deletes any room that already holds the code. The
    codes are arena codes, so on an operator's machine that is someone else's
    room. Pointing `SOE_DATA_DIR` and `SOE_GAMES_DIR` at a temp directory keeps
    the exporter uncoupled from the beta store, as the hosting gate requires.
    Set either variable yourself to override.
    """
    if os.environ.get("SOE_DATA_DIR") and os.environ.get("SOE_GAMES_DIR"):
        return
    scratch = Path(tempfile.mkdtemp(prefix="soe-replay-"))
    os.environ.setdefault("SOE_DATA_DIR", str(scratch / "server_data"))
    os.environ.setdefault("SOE_GAMES_DIR", str(scratch / "games"))
    (scratch / "server_data").mkdir(parents=True, exist_ok=True)
    (scratch / "games").mkdir(parents=True, exist_ok=True)
    atexit.register(shutil.rmtree, scratch, True)


_use_scratch_state()

from soe import public_replay  # noqa: E402


# ---------------------------------------------------------------------------
# bundle reading
# ---------------------------------------------------------------------------


@dataclass
class GameRecord:
    """One game's start record, joined with its result record."""

    game_id: str
    code: str
    seed: int
    map_file: str
    seats: dict[str, str]
    turns: int
    winner: str | None = None
    turns_played: int = 0


def _read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_games(bundle: Path) -> dict[str, GameRecord]:
    """Every game in the bundle, start record joined with result record."""
    games: dict[str, GameRecord] = {}
    for row in _read_jsonl(bundle / "games.jsonl"):
        game_id = row.get("game_id") or row.get("code") or ""
        if not game_id:
            continue
        if row.get("event") == "result":
            record = games.get(game_id)
            if record is not None:
                record.winner = row.get("winner")
                record.turns_played = int(row.get("turns_played") or 0)
            continue
        games[game_id] = GameRecord(
            game_id=game_id,
            code=str(row.get("code") or game_id),
            seed=int(row.get("seed") or 0),
            map_file=str(row.get("map") or ""),
            seats=dict(row.get("seats") or {}),
            turns=int(row.get("turns") or 0),
        )
    return games


def read_orders(bundle: Path, game_id: str, turn: int, faction_id: str) -> str:
    """The recorded order text for one seat on one turn.

    Falls back to the decision trace when the plain-text mirror is absent, so
    a bundle written before `record_orders_text` still replays.
    """
    path = bundle / "orders" / game_id / f"turn_{turn}_{faction_id}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    trace = bundle / "decisions" / game_id / f"turn_{turn}_{faction_id}.json"
    if trace.exists():
        with open(trace, encoding="utf-8") as handle:
            return str(json.load(handle).get("orders_text") or "")
    return ""


def read_state_hashes(bundle: Path, game_id: str) -> dict[int, str]:
    """Recorded end-of-turn state hashes, used to prove the replay matched."""
    return {
        int(row["turn"]): str(row.get("state_sha") or "")
        for row in _read_jsonl(bundle / "turns.jsonl")
        if row.get("game") == game_id and "turn" in row
    }


def _trace_counts(trace: dict) -> tuple[int, int]:
    """(order lines, warned order lines) from one decision trace.

    The trace is written to disk before the engine resolves the turn, so the
    `resolved_*` counters `play_game` computes never reach the file. What is
    persisted is the submitted pair, with the emitted pair as the fallback for
    a seat whose text failed extraction.
    """
    lines = trace.get("orders_submitted")
    warned = trace.get("submitted_warning_order_lines")
    if not isinstance(lines, (int, float)):
        lines = trace.get("orders_emitted")
        warned = trace.get("emitted_warning_order_lines")
    return int(lines or 0), int(warned or 0)


def _bundle_warning_rate(bundle: Path, game_id: str | None) -> float | None:
    """Warned order lines / order lines, over one game or the whole run.

    Computed from the traces rather than read from `arena_results.json` so the
    per-game rate and the rate it is compared against are the same measurement.
    A published number built from a different counter would make every game
    look anomalous, or none of them.
    """
    root = bundle / "decisions"
    directories = [root / game_id] if game_id else sorted(
        p for p in root.glob("*") if p.is_dir()
    )
    lines = 0
    warned = 0
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            with open(path, encoding="utf-8") as handle:
                trace = json.load(handle)
            game_lines, game_warned = _trace_counts(trace)
            lines += game_lines
            warned += game_warned
    return (warned / lines) if lines else None


def bundle_commit(bundle: Path) -> str | None:
    """The commit the run was recorded at, from its manifest."""
    path = bundle / "manifest.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle).get("git_commit") or None


def head_commit() -> str | None:
    import subprocess

    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:  # noqa: BLE001 - no git is not a reason to crash the export
        return None
    return done.stdout.strip() or None


# ---------------------------------------------------------------------------
# reconstruction
# ---------------------------------------------------------------------------


def _build_room(code: str, map_file: str, faction_ids: list[str], labels: list[str]):
    """The same room `arena.play_game` builds, so the replay is the same game.

    Start cities are derived from the room code and every turn's seed is
    `sha256(code:turn)`, so code, map, and seat order are the whole of what
    the engine needs to reproduce the match.
    """
    from webapp import rooms as rooms_mod
    from scripts.arena import _reset_game

    _reset_game(code)
    players = [
        rooms_mod.RoomPlayer(
            slot=index,
            faction_id=faction_id,
            faction_name=rooms_mod.FACTION_NAMES[index % len(rooms_mod.FACTION_NAMES)][0],
            display_name=labels[index],
            kind="agent",
            agent_key=f"arena-{code}-{index}",
        )
        for index, faction_id in enumerate(faction_ids)
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
    return room, players


def reconstruct(
    bundle: Path,
    record: GameRecord,
    *,
    verify: bool = True,
) -> tuple[list[dict], str | None, str]:
    """Replay one recorded match. Returns (frames, winner_seat, decided_by).

    Frame 0 is the opening position; frame N is the end of turn N.
    """
    from webapp import service
    from soe import engine, parser
    from scripts.arena import (
        _faction_metrics,
        decide_winner,
        TIEBREAK,
    )
    from scripts.arena_bundle import state_sha

    faction_ids = sorted(record.seats)
    room, players = _build_room(
        record.code, record.map_file, faction_ids, [record.seats[f] for f in faction_ids]
    )
    service.create_game(room)
    state = service.load_state(room)

    recorded_hashes = read_state_hashes(bundle, record.game_id) if verify else {}
    registry = public_replay._PieceRegistry()
    frames = [public_replay.frame_from_state(state, 0, registry)]

    total_turns = record.turns_played or record.turns
    for turn in range(1, total_turns + 1):
        orders_by_player = {}
        for player in players:
            text = read_orders(bundle, record.game_id, turn, player.faction_id)
            orders_by_player[player.faction_id] = parser.parse_orders(
                text, state, player.faction_id
            )
        state, _log = engine.run_turn(
            state, orders_by_player, service.deterministic_seed(room, turn)
        )
        expected = recorded_hashes.get(turn)
        if expected:
            actual = state_sha(state)
            if actual != expected:
                raise RuntimeError(
                    f"replay diverged from the recorded match at turn {turn} "
                    f"({record.game_id}): the bundle and the engine disagree, so "
                    "this reconstruction is not that game"
                )
        frames.append(public_replay.frame_from_state(state, turn, registry))

    metrics = {fid: _faction_metrics(state, fid) for fid in faction_ids}
    winner = decide_winner(metrics)
    return frames, winner, _decided_by(metrics, winner, TIEBREAK)


def _decided_by(metrics: dict[str, dict], winner: str | None, tiebreak: tuple) -> str:
    """Which criterion separated the seats -- the honest version of the result.

    The field plan is explicit that an 80-0 sweep is not a ranking: it happened
    because the tie-break rewards territory and soldiers and the two seats never
    fought. Naming the deciding criterion is what keeps the poster from
    implying otherwise.
    """
    if winner is None:
        return "draw"
    alive = [fid for fid, m in metrics.items() if m["characters_alive"] > 0]
    if len(alive) == 1:
        return "elimination"
    others = [m for fid, m in metrics.items() if fid != winner]
    for key in tiebreak:
        best = metrics[winner][key]
        if all(best != other[key] for other in others):
            return key
    return "tiebreak"


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


def audit(bundle: Path, limit: int | None, label: str) -> list[dict]:
    """Score candidate games. Never picks; ranks and reports."""
    games = read_games(bundle)
    run_rate = _bundle_warning_rate(bundle, None)
    rows: list[dict] = []
    for index, (game_id, record) in enumerate(sorted(games.items())):
        if limit is not None and index >= limit:
            break
        try:
            frames, winner, decided_by = reconstruct(bundle, record)
        except Exception as exc:  # noqa: BLE001 - a bad candidate is skipped, not fatal
            rows.append({"game_id": game_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        replay = public_replay.build(
            map_file=record.map_file,
            match_id=game_id,
            label=label,
            seats=record.seats,
            frames=frames,
            winner_seat=winner,
            decided_by=decided_by,
        )
        bar = public_replay.visual_bar(replay)
        rate = _bundle_warning_rate(bundle, game_id)
        anomalous = (
            rate is not None
            and run_rate is not None
            and run_rate > 0
            and rate > run_rate * 2
        )
        rows.append(
            {
                "game_id": game_id,
                "winner": winner,
                "decided_by": decided_by,
                "warning_rate": rate,
                "warning_anomalous": anomalous,
                **bar,
            }
        )
    rows.sort(
        key=lambda r: (
            r.get("passes", False),
            r.get("territory_changes", -1),
            r.get("contacts", -1),
            r.get("moves", -1),
        ),
        reverse=True,
    )
    return rows


# ---------------------------------------------------------------------------
# exhibition
# ---------------------------------------------------------------------------


def exhibition(map_file: str, seed: int, turns: int, styles: tuple[str, str]) -> tuple:
    """A local scripted-versus-scripted match, for when no gate game is watchable.

    The field plan allows this on the poster, labelled `exhibition`. It is not
    evidence of the 7,200-turn gate and this function never says it is.
    """
    from webapp import service
    from soe import engine, parser
    from scripts.arena import ScriptedPolicy, _faction_metrics, decide_winner, TIEBREAK

    code = f"EX{seed:03d}"
    faction_ids = ["player_1", "player_2"]
    labels = [f"scripted:{styles[0]}", f"scripted:{styles[1]}"]
    room, players = _build_room(code, map_file, faction_ids, labels)
    service.create_game(room)
    state = service.load_state(room)

    policies = [ScriptedPolicy(styles[0]), ScriptedPolicy(styles[1])]
    registry = public_replay._PieceRegistry()
    frames = [public_replay.frame_from_state(state, 0, registry)]
    prev_reports = {p.faction_id: "(no report yet)" for p in players}

    from scripts.arena import _decision_context

    for turn in range(1, turns + 1):
        orders_by_player = {}
        for index, player in enumerate(players):
            rng = random.Random(f"{seed}:{code}:{player.faction_id}:{turn}")
            ctx = _decision_context(
                state, player.faction_id, turn, room, map_file, seed, index, prev_reports
            )
            text = policies[index].orders(ctx, rng).text
            orders_by_player[player.faction_id] = parser.parse_orders(
                text, state, player.faction_id
            )
        state, turn_log = engine.run_turn(
            state, orders_by_player, service.deterministic_seed(room, turn)
        )
        from soe import reporting

        reports = reporting.generate_player_reports(state, turn_log, orders_by_player)
        prev_reports = {
            p.faction_id: reports.get(p.faction_id, "(no report yet)") for p in players
        }
        frames.append(public_replay.frame_from_state(state, turn, registry))

    metrics = {fid: _faction_metrics(state, fid) for fid in faction_ids}
    winner = decide_winner(metrics)
    seats = {fid: labels[i] for i, fid in enumerate(faction_ids)}
    return frames, winner, _decided_by(metrics, winner, TIEBREAK), seats, code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write(replay: dict, out: Path) -> None:
    public_replay.validate(replay)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(replay, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser_ = argparse.ArgumentParser(description=__doc__)
    sub = parser_.add_subparsers(dest="command", required=True)

    p_audit = sub.add_parser("audit", help="score candidate games in a bundle")
    p_audit.add_argument("bundle", type=Path)
    p_audit.add_argument("--limit", type=int, default=None)
    p_audit.add_argument("--json", action="store_true")

    p_export = sub.add_parser("export", help="export one game as a public replay")
    p_export.add_argument("bundle", type=Path)
    p_export.add_argument("game_id")
    p_export.add_argument("-o", "--out", type=Path, required=True)
    p_export.add_argument(
        "--label", choices=list(public_replay.LABELS), default="official-gate"
    )

    p_ex = sub.add_parser("exhibition", help="export a local scripted match")
    p_ex.add_argument("-o", "--out", type=Path, required=True)
    p_ex.add_argument("--map", dest="map_file", default="calib_12.json")
    p_ex.add_argument("--seed", type=int, default=0)
    p_ex.add_argument("--turns", type=int, default=30)
    p_ex.add_argument("--styles", nargs=2, default=["military", "expansionist"])

    args = parser_.parse_args(argv)

    if args.command == "audit":
        rows = audit(args.bundle, args.limit, "exhibition")
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            header = f"{'game':<12}{'moves':>7}{'contact':>9}{'terr':>6}{'warn':>8}  bar"
            print(header)
            print("-" * len(header))
            for row in rows:
                if "error" in row:
                    print(f"{row['game_id']:<12}  {row['error']}")
                    continue
                rate = row["warning_rate"]
                rate_text = "n/a" if rate is None else f"{rate:.3f}"
                flag = "!" if row["warning_anomalous"] else " "
                bar = "PASS" if row["passes"] else "fail"
                print(
                    f"{row['game_id']:<12}{row['moves']:>7}{row['contacts']:>9}"
                    f"{row['territory_changes']:>6}{rate_text:>8}{flag} {bar}"
                )
            print(
                "\nNothing here picks a match. A PASS row is a candidate; the "
                "operator chooses.\n"
            )
        return 0

    if args.command == "export":
        games = read_games(args.bundle)
        record = games.get(args.game_id)
        if record is None:
            print(f"no game {args.game_id!r} in {args.bundle}", file=sys.stderr)
            return 2
        # An `official-gate` label says "this is a match from the 7,200-turn
        # gate". A replay on an engine that has moved since the run is a new
        # simulation of the same orders, not that match -- the order-bug fixes
        # after the gate change how turns resolve. Reconstruct at the recorded
        # commit or do not make the claim.
        recorded = bundle_commit(args.bundle)
        current = head_commit()
        drifted = bool(recorded and current and recorded != current)
        if drifted and args.label == "official-gate":
            print(
                f"engine drift: bundle recorded at {recorded[:12]}, working tree at "
                f"{current[:12]}.\nAn 'official-gate' replay must be reconstructed on "
                "the engine that produced it:\n\n"
                f"  git worktree add ../soe-replay {recorded[:12]}\n"
                "  cp soe/public_replay.py ../soe-replay/soe/\n"
                "  cp scripts/export_public_replay.py ../soe-replay/scripts/\n"
                f"  cd ../soe-replay && python -m scripts.export_public_replay export "
                f"{args.bundle} {args.game_id} -o {args.out}\n\n"
                "Or export it here as --label exhibition, which claims nothing "
                "about the gate.",
                file=sys.stderr,
            )
            return 3
        frames, winner, decided_by = reconstruct(args.bundle, record)
        replay = public_replay.build(
            map_file=record.map_file,
            match_id=args.game_id,
            label=args.label,
            seats=record.seats,
            frames=frames,
            winner_seat=winner,
            decided_by=decided_by,
        )
        _write(replay, args.out)
        bar = public_replay.visual_bar(replay)
        print(f"wrote {args.out} ({replay['turns']} turns, {len(replay['frames'])} frames)")
        print(f"visual bar: {bar}")
        return 0

    if args.command == "exhibition":
        frames, winner, decided_by, seats, code = exhibition(
            args.map_file, args.seed, args.turns, tuple(args.styles)
        )
        replay = public_replay.build(
            map_file=args.map_file,
            match_id=f"exh-{code.lower()}",
            label="exhibition",
            seats=seats,
            frames=frames,
            winner_seat=winner,
            decided_by=decided_by,
        )
        _write(replay, args.out)
        print(f"wrote {args.out} ({replay['turns']} turns)")
        print(f"visual bar: {public_replay.visual_bar(replay)}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
