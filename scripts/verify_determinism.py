"""
Determinism guard: replay a resolved turn and compare the resulting state.

Usage:
    python scripts/verify_determinism.py --code ROOM --turn N

Replays turn N from the pre-turn snapshot (state_turn{N-1}.json) with the
recorded orders and the deterministic (room, turn) seed, then compares the
SHA-256 of the replayed state against the hash the live resolution recorded
in resolution_events.jsonl. A mismatch means the engine produced different
outputs for identical inputs — an immediate alarm.

Exit code 0 = match, 1 = mismatch, 2 = cannot verify (missing inputs).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

from spoils_engine import engine, parser, storage

from webapp import service
from webapp.rooms import default_store


def main() -> int:
    parser_arg = argparse.ArgumentParser(description=__doc__)
    parser_arg.add_argument("--code", required=True, help="Room code, e.g. ABC12")
    parser_arg.add_argument("--turn", required=True, type=int)
    args = parser_arg.parse_args()

    room = default_store().get(args.code)
    if not room:
        print(f"No room with code {args.code}.", file=sys.stderr)
        return 2

    events = service._read_jsonl(room.game_dir() / "resolution_events.jsonl", limit=100)
    completed = [
        e
        for e in events
        if e.get("turn") == args.turn and e.get("status") == "completed"
    ]
    if not completed or not completed[-1].get("post_state_sha"):
        print(
            f"No determinism record for turn {args.turn} "
            f"(resolve it with the current build first).",
            file=sys.stderr,
        )
        return 2
    expected = completed[-1]["post_state_sha"]

    try:
        pre = service.load_state(room, turn=args.turn - 1)
    except service.TurnNotFoundError:
        print(f"Pre-turn snapshot for turn {args.turn} is missing.", file=sys.stderr)
        return 2

    orders_dir = room.game_dir() / "orders"
    orders_by_player: dict[str, list] = {}
    for faction_id in pre.factions:
        if faction_id == "independent":
            continue
        order_file = orders_dir / f"{faction_id}_turn{args.turn}.txt"
        if order_file.exists():
            text = order_file.read_text(encoding="utf-8")
            orders_by_player[faction_id] = parser.parse_orders(text, pre, faction_id)
        else:
            orders_by_player[faction_id] = []

    seed = service.deterministic_seed(room, args.turn)
    try:
        replayed, _ = engine.run_turn(pre, orders_by_player, seed)
    except Exception as exc:  # noqa: BLE001 - report and let the caller decide
        print(f"Replay crashed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(replayed, Path(tmp))
        actual = hashlib.sha256((Path(tmp) / "state.json").read_bytes()).hexdigest()

    if actual == expected:
        print(f"turn {args.turn}: DETERMINISTIC ({actual[:16]}...)")
        return 0
    print(
        f"turn {args.turn}: MISMATCH!\n  recorded: {expected}\n  replayed: {actual}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
