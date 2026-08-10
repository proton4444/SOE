"""Run a tiny, deterministic gameplay path and write a human-readable verdict.

This is intentionally not a long beta simulation. It answers one practical
question: can two players submit understandable orders, resolve three turns,
and observe a meaningful change in the world without an engine exception?
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from spoils_engine import config, engine, map_loader, models, parser, reporting, storage


DEFAULT_OUTPUT = ROOT / "games" / "gameplay_smoke"
MAP_FILE = ROOT / "maps" / "sample_map.json"
BASE_SEED = 1000

ORDERS = {
    1: {
        "player_1": (
            "Have Emperor Marcus recruit 80 soldiers in Madegi Doy. "
            "Have Emperor Marcus secure Madegi Doy. "
            "Have Emperor Marcus tax."
        ),
        "player_2": (
            "Have Khan Tengri recruit 10 soldiers in Kitesta. "
            "Have Khan Tengri secure Kitesta. "
            "Have Khan Tengri tax."
        ),
    },
    2: {
        "player_1": (
            "Have Emperor Marcus go to Kitesta. Have Emperor Marcus attack Khan Tengri."
        ),
        "player_2": "Have Khan Tengri wait for 1 week.",
    },
    3: {
        "player_1": (
            "Have Emperor Marcus attack Khan Tengri. "
            "Have Emperor Marcus secure Kitesta. "
            "Have Emperor Marcus tax."
        ),
        "player_2": "Have Khan Tengri wait for 1 week.",
    },
}


def _initial_state() -> models.GameState:
    world = map_loader.load_map_from_json(MAP_FILE)
    state = models.GameState(turn_number=0, world_map=world)
    players = [
        ("player_1", "The Golden Empire", "Emperor Marcus", "madegi_doy"),
        ("player_2", "The Silver Horde", "Khan Tengri", "kitesta"),
    ]
    for faction_id, faction_name, leader_name, city_id in players:
        state.factions[faction_id] = models.Faction(
            id=faction_id,
            name=faction_name,
            controlled_city_ids={city_id},
        )
        state.characters[f"char_{faction_id}_leader"] = models.Character(
            id=f"char_{faction_id}_leader",
            name=leader_name,
            faction_id=faction_id,
            location_city_id=city_id,
            is_leader=True,
            gold=float(config.STARTING_TREASURY),
            combat_skill=50,
            magic_skill=config.STARTING_MAGIC_SKILL,
            magic_power_current=config.STARTING_MAGIC_SKILL,
        )
    return state


def _snapshot(state: models.GameState) -> dict:
    factions = {}
    for faction_id, faction in state.factions.items():
        characters = [
            c for c in state.characters.values() if c.faction_id == faction_id
        ]
        units = Counter()
        for stack in state.unit_stacks.values():
            if stack.faction_id == faction_id:
                units[stack.unit_type.value] += stack.count
        factions[faction_id] = {
            "name": faction.name,
            "sovereign_cities": sorted(faction.controlled_city_ids),
            "occupied_cities": sorted(faction.secured_city_ids),
            "gold": round(faction.treasury + sum(c.gold for c in characters), 1),
            "soldiers": units.get("soldier", 0),
            "free_characters": sum(
                not c.is_dead and not c.is_prisoner for c in characters
            ),
            "prisoners": sum(c.is_prisoner for c in characters),
            "dead": sum(c.is_dead for c in characters),
            "leaders": [
                {
                    "name": c.name,
                    "city": c.location_city_id,
                    "dead": c.is_dead,
                    "prisoner": c.is_prisoner,
                }
                for c in characters
            ],
        }
    return {"turn": state.turn_number, "factions": factions}


def _city_names(state: models.GameState, ids: list[str] | set[str]) -> list[str]:
    return sorted(
        state.world_map.cities[city_id].name
        for city_id in ids
        if city_id in state.world_map.cities
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


def _report(summary: dict, state: models.GameState, turn_records: list[dict]) -> str:
    lines = [
        "# Spoils of Empire - Gameplay Smoke Test",
        "",
        "## Verdict",
        "",
        f"**{summary['verdict']}** - {summary['turns_completed']} turns completed "
        f"with {summary['event_count']} gameplay events and "
        f"{summary['warning_count']} parser warnings.",
        "",
        "This is a short golden-path check for human play, not a balance test. "
        "It verifies that orders can be understood, turns can resolve, and the "
        "world changes in a way a master can explain.",
        "",
        "## Scenario",
        "",
        "- Turn 1: both factions recruit, secure their home city, and collect taxes.",
        "- Turn 2: Emperor Marcus marches from Madegi Doy to Kitesta and attacks Khan Tengri.",
        "- Turn 3: Marcus attacks again, secures Kitesta, and collects taxes; Tengri waits.",
        "",
        "## Turn-by-turn",
        "",
    ]
    for record in turn_records:
        lines.append(f"### Turn {record['turn']}")
        lines.append("")
        lines.append(
            f"Orders parsed: {record['parsed_orders']} | "
            f"Warnings: {record['warning_count']} | "
            f"Seed: `{record['seed']}`"
        )
        lines.append("")
        for event in record["events"]:
            status = "OK" if event["success"] else "FAILED"
            lines.append(f"- **{status}** {event['description']}")
        lines.append("")

    lines += [
        "## Final board",
        "",
        "| Faction | Sovereign cities | Occupied cities | Gold | Soldiers | Characters |",
        "|---|---|---|---:|---:|---:|",
    ]
    for faction in summary["final"]["factions"].values():
        lines.append(
            f"| {faction['name']} | "
            f"{', '.join(_city_names(state, faction['sovereign_cities'])) or 'none'} | "
            f"{', '.join(_city_names(state, faction['occupied_cities'])) or 'none'} | "
            f"{faction['gold']:.1f} | {faction['soldiers']} | "
            f"{faction['free_characters']} free / {faction['prisoners']} prisoner / {faction['dead']} dead |"
        )

    lines += ["", "## Checks", ""]
    for check in summary["checks"]:
        lines.append(
            f"- {'PASS' if check['passed'] else 'FAIL'}: {check['name']} - {check['detail']}"
        )
    lines += [
        "",
        "## Artifacts",
        "",
        "- `state.json` - final persisted engine state",
        "- `turn_events.jsonl` - structured event feed used by the master dashboard",
        "- `orders/` - the exact human-readable orders for each turn",
        "- `reports/` - player reports generated from each resolved turn",
    ]
    return "\n".join(lines) + "\n"


def run_smoke(output_dir: Path = DEFAULT_OUTPUT) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "orders").mkdir(exist_ok=True)
    (output_dir / "reports").mkdir(exist_ok=True)
    state = _initial_state()
    storage.save_game_state(state, output_dir)
    turn_records = []
    all_events = []
    warning_count = 0
    error = ""

    for turn, order_texts in ORDERS.items():
        parsed_orders = {}
        parsed_count = 0
        turn_warning_count = 0
        try:
            for faction_id, text in order_texts.items():
                (output_dir / "orders" / f"{faction_id}_turn{turn}.txt").write_text(
                    text + "\n", encoding="utf-8"
                )
                orders = parser.parse_orders(text, state, faction_id)
                parsed_orders[faction_id] = orders
                parsed_count += len(orders)
                turn_warning_count += sum(len(order.warnings) for order in orders)

            state, turn_log = engine.run_turn(
                state, parsed_orders, seed=BASE_SEED + turn
            )
            events = [
                {
                    "phase": event.phase,
                    "player_id": event.player_id,
                    "event_type": event.event_type,
                    "description": event.description,
                    "location_city_id": event.location_city_id,
                    "success": event.success,
                }
                for event in turn_log.events
                if not event.silent
            ]
            all_events.extend(events)
            turn_records.append(
                {
                    "turn": turn,
                    "seed": BASE_SEED + turn,
                    "parsed_orders": parsed_count,
                    "warning_count": turn_warning_count,
                    "events": events,
                }
            )
            _write_jsonl(output_dir / "turn_events.jsonl", turn_records)
            reports = reporting.generate_player_reports(state, turn_log, parsed_orders)
            for faction_id, report in reports.items():
                (output_dir / "reports" / f"{faction_id}_turn{turn}.txt").write_text(
                    report, encoding="utf-8"
                )
            storage.save_game_state(state, output_dir)
        except Exception as exc:  # pragma: no cover - exercised by the verdict path
            error = f"{type(exc).__name__}: {exc}"
            break
        warning_count += turn_warning_count

    p1 = state.factions["player_1"]
    p1_leader = state.characters["char_player_1_leader"]
    p2 = state.factions["player_2"]
    checks = [
        {
            "name": "three turns resolved",
            "passed": state.turn_number == 3 and not error,
            "detail": f"engine turn is {state.turn_number}",
        },
        {
            "name": "orders were understood",
            "passed": warning_count == 0 and len(turn_records) == 3,
            "detail": f"{warning_count} parser warnings",
        },
        {
            "name": "movement and combat happened",
            "passed": any(event["event_type"] == "victory" for event in all_events),
            "detail": "Emperor Marcus won the Kitesta engagement",
        },
        {
            "name": "occupation changed the board",
            "passed": "kitesta" in p1.secured_city_ids and not p2.secured_city_ids,
            "detail": "Kitesta is secured by The Golden Empire",
        },
        {
            "name": "reports and state were written",
            "passed": (output_dir / "state.json").exists()
            and (output_dir / "reports" / "player_1_turn3.txt").exists(),
            "detail": "final state and player report are present",
        },
    ]
    passed = all(check["passed"] for check in checks) and not error
    summary = {
        "verdict": "PASS" if passed else "FAIL",
        "turns_completed": state.turn_number,
        "event_count": len(all_events),
        "warning_count": warning_count,
        "error": error,
        "checks": checks,
        "final": _snapshot(state),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output_dir / "GAMEPLAY_REPORT.md").write_text(
        _report(summary, state, turn_records), encoding="utf-8"
    )
    return summary


def main() -> int:
    summary = run_smoke()
    print(
        f"{summary['verdict']} - {summary['turns_completed']} turns, "
        f"{summary['event_count']} events, "
        f"{summary['warning_count']} parser warnings"
    )
    print(f"Human report: {DEFAULT_OUTPUT / 'GAMEPLAY_REPORT.md'}")
    for check in summary["checks"]:
        print(
            f"  {'PASS' if check['passed'] else 'FAIL'} {check['name']}: {check['detail']}"
        )
    if summary["error"]:
        print(summary["error"])
    return 0 if summary["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
