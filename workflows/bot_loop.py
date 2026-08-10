"""
Auto-play workflow: run every enabled bot in a room for N turns.

Run this on the machine that holds the game files (the server box), with
SOE_LLM_KEY set:

    set SOE_LLM_KEY=sk-or-v1-...
    python workflows/bot_loop.py --code ABC12 --turns 20

Each iteration: intel + field subagents per bot, the strategist decides,
orders are filtered by the engine's own parser, the turn resolves with the
deterministic room seed, and a summary line is printed. Per-bot failures are
reported and the loop continues; a resolution failure stops the run.
"""

from __future__ import annotations

import argparse
import sys
import time

from webapp import service
from webapp.ai import brain, orchestrator
from webapp.ai.registry import default_registry
from webapp.rooms import default_store


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="Room code, e.g. ABC12")
    parser.add_argument("--turns", type=int, default=10, help="Turns to play")
    parser.add_argument("--force", action="store_true",
                        help="Resolve even if a player has not submitted")
    parser.add_argument("--pause", type=float, default=1.0,
                        help="Seconds between bot runs and resolutions")
    args = parser.parse_args()

    if not brain.is_configured():
        print("Set SOE_LLM_KEY first.", file=sys.stderr)
        return 2

    room = default_store().get(args.code)
    if not room:
        print(f"No room with code {args.code}.", file=sys.stderr)
        return 1
    bots = [
        p for p in room.players
        if default_registry().is_bot(room.code, p.faction_id)
    ]
    if not bots:
        print("No enabled bots in this room.", file=sys.stderr)
        return 1

    print(f"Room {room.code}: {len(bots)} bot(s), "
          f"{args.turns} turn(s), force={args.force}")
    for turn_index in range(args.turns):
        turn = room.next_turn()
        print(f"\n== turn {turn} ==")
        for player in bots:
            time.sleep(args.pause)
            try:
                result = orchestrator.run_bot_turn(room, player)
                warnings = "; ".join(result["warnings"]) or "none"
                print(f"  {player.faction_name}: {result['parsed']} order(s) "
                      f"(warnings: {warnings})")
            except Exception as exc:  # noqa: BLE001 - per-bot, keep going
                print(f"  {player.faction_name}: FAILED "
                      f"{type(exc).__name__}: {exc}")
        time.sleep(args.pause)
        try:
            resolved = service.resolve_turn(room, force=args.force)
            print(f"  resolved turn {resolved['turn']} (seed {resolved['seed']})")
        except service.NotReadyError as exc:
            print(f"  NOT resolved: {exc}")
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"  resolution failed: {type(exc).__name__}: {exc}")
            return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
