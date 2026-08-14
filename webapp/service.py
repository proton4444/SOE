"""
Bridge between the web server and the engine.

The engine stays untouched: the server replicates what ``cli.py`` does —
initialise a game from a map and players, parse orders, run a seeded turn,
save state, write reports — and adds a structured per-player view so agents
can read the world without parsing prose.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import tempfile
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from soe import (
    config,
    engine,
    map_loader,
    models,
    parser,
    reporting,
    storage,
    territory,
)

from webapp import backups, mapview
from webapp.ai import context as agent_context
from webapp.ai.context import _observed_city_ids, _secured_by
from webapp.ai.registry import default_registry
from webapp.observability import logger
from webapp.rooms import Room, RoomPlayer, default_store

_ROOT = Path(__file__).resolve().parent.parent
_MAPS_DIR = _ROOT / "maps"

# Prefer the full gazetteer map when present; sample stays as a fallback.
_PREFERRED_DEFAULT_MAP = "world.json"
_FALLBACK_DEFAULT_MAP = "starter_map.json"

# Independent characters every game gets, so OFFER has someone to hire.
# ``locations`` is tried in order so the same list works on sample_map
# (gullhaven) and soe_world (redport / highfell).
_DEFAULT_INDEPENDENTS = [
    {
        "name": "Wizard Ojibenmi",
        "gender": "male",
        "locations": ["gullhaven", "redport"],
        "skills": {"magic": 60},
    },
    {
        "name": "Bishop Nancy Lopenda",
        "gender": "female",
        "title": "bishop",
        "locations": ["highfell"],
        "skills": {"religion": 45},
    },
]

_lock = threading.RLock()


def available_maps() -> list[str]:
    """Playable world maps only (JSON with a non-empty cities list).

    Pipeline sidecars such as ``soe_geography.json`` live in ``maps/`` but are
    not engine maps and must not appear in the room picker.
    """
    import json

    names: list[str] = []
    for path in sorted(_MAPS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cities = data.get("cities") if isinstance(data, dict) else None
        if isinstance(cities, list) and cities:
            names.append(path.name)
    return names


def default_map() -> str:
    """Map used when the client omits ``map`` / ``map_file``."""
    maps = available_maps()
    if _PREFERRED_DEFAULT_MAP in maps:
        return _PREFERRED_DEFAULT_MAP
    if maps:
        return maps[0]
    return _FALLBACK_DEFAULT_MAP


# ============================================================================
# game lifecycle
# ============================================================================


def create_game(room: Room) -> models.GameState:
    """Initialise the engine game for a room. Returns the fresh state."""
    with _lock:
        game_dir = room.game_dir()
        if storage.game_exists(game_dir):
            raise RuntimeError(f"Game already exists at {game_dir}")

        world_map = _load_map(room.map_file)
        game_state = models.GameState(turn_number=0, world_map=world_map)

        # Only cities that can all reach each other are eligible: a player
        # dropped on a sealed island or a dead-end one-way road would have no
        # game to play. Falls back to the raw city list for degenerate maps so
        # a hand-built test map still boots.
        city_ids = map_loader.mutually_reachable_cities(world_map) or list(
            world_map.cities.keys()
        )
        if not city_ids:
            raise RuntimeError(f"Map '{room.map_file}' has no cities")
        # Seeded random start cities: reproducible from the room code alone.
        start_cities = list(city_ids)
        random.Random(_room_seed(room.code)).shuffle(start_cities)

        for player in room.players:
            player.start_city = start_cities[player.slot % len(start_cities)]
            _add_faction(game_state, player)

        _add_independents(game_state)

        default_store().save()
        storage.save_game_state(game_state, game_dir)
        _snapshot_state(room, 0)
        return game_state


def _room_seed(code: str) -> int:
    digest = hashlib.sha256(code.encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _load_map(map_file: str) -> models.WorldMap:
    path = _MAPS_DIR / map_file
    if not path.exists():
        raise FileNotFoundError(f"Map not found: {map_file}")
    return map_loader.load_map_from_json(path)


def _add_faction(game_state: models.GameState, player: RoomPlayer) -> None:
    _, leader_name = _name_pair(player.slot)
    city_ids = map_loader.mutually_reachable_cities(game_state.world_map) or list(
        game_state.world_map.cities.keys()
    )
    start_city = player.start_city or city_ids[player.slot % len(city_ids)]

    faction = models.Faction(
        id=player.faction_id,
        name=player.faction_name,
        treasury=0,
        controlled_city_ids={start_city},
    )
    game_state.factions[player.faction_id] = faction

    leader = models.Character(
        id=f"char_{player.faction_id}_leader",
        name=leader_name,
        faction_id=player.faction_id,
        location_city_id=start_city,
        is_leader=True,
        gold=float(config.STARTING_TREASURY),
        combat_skill=config.STARTING_COMBAT_SKILL,
        magic_skill=config.STARTING_MAGIC_SKILL,
        magic_power_current=config.STARTING_MAGIC_SKILL,
    )
    game_state.characters[leader.id] = leader


def _name_pair(slot: int):
    from webapp.rooms import FACTION_NAMES

    return FACTION_NAMES[slot % len(FACTION_NAMES)]


def _resolve_city_id(preferred: str | list[str] | None, city_ids: list[str]) -> str:
    """Pick the first preferred city that exists on this map; else first city."""
    if not city_ids:
        raise RuntimeError("Map has no cities")
    if preferred is None:
        prefs: list[str] = []
    elif isinstance(preferred, str):
        prefs = [preferred]
    else:
        prefs = list(preferred)
    present = set(city_ids)
    for city_id in prefs:
        if city_id in present:
            return city_id
    return city_ids[0]


def _add_independents(game_state: models.GameState) -> None:
    npc_faction = models.Faction(
        id="independent",
        name="The Free Cities",
        is_npc=True,
    )
    game_state.factions["independent"] = npc_faction
    # Same pool as the players: an independent on an unreachable city is
    # content no one can ever visit. An explicit location still wins.
    city_ids = map_loader.mutually_reachable_cities(game_state.world_map) or list(
        game_state.world_map.cities.keys()
    )

    for j, npc in enumerate(_DEFAULT_INDEPENDENTS):
        npc_id = f"char_independent_{j + 1}"
        skills = npc["skills"]
        preferred = npc.get("locations") or npc.get("location")
        location = _resolve_city_id(preferred, city_ids)
        game_state.characters[npc_id] = models.Character(
            id=npc_id,
            name=npc["name"],
            faction_id="independent",
            location_city_id=location,
            is_leader=False,
            gender=npc.get("gender", "male"),
            title=npc.get("title", ""),
            magic_skill=int(skills.get("magic", 0)),
            religion_skill=int(skills.get("religion", 0)),
            magic_power_current=int(skills.get("magic", 0)),
            religious_power_current=int(skills.get("religion", 0)),
        )


def load_state(room: Room, *, turn: int | None = None) -> models.GameState:
    """Load the current state, or the per-turn snapshot for ``turn``."""
    if turn is None:
        state = storage.load_game_state(room.game_dir())
        if state is None:
            raise RuntimeError(f"Could not load game state for {room.code}")
        return state
    snapshot = room.game_dir() / f"state_turn{turn}.json"
    if not snapshot.exists():
        raise TurnNotFoundError(turn)
    with open(snapshot, encoding="utf-8") as handle:
        data = json.load(handle)
    state = storage.decode_game_state(data)
    if state is None:
        raise RuntimeError(f"Could not decode turn {turn} snapshot for {room.code}")
    return state


def _snapshot_state(room: Room, turn: int) -> None:
    """Keep a per-turn state copy so the map can be rewound (``?turn=N``)."""
    source = room.game_dir() / "state.json"
    if not source.exists():
        return
    target = room.game_dir() / f"state_turn{turn}.json"
    try:
        _atomic_write_text(target, source.read_text(encoding="utf-8"))
    except OSError:
        logger.exception("turn_snapshot_failed room=%s turn=%s", room.code, turn)


class TurnNotFoundError(LookupError):
    def __init__(self, turn: int):
        super().__init__(f"No saved state for turn {turn}.")
        self.turn = turn


# ============================================================================
# orders
# ============================================================================


def parse_feedback(room: Room, player: RoomPlayer, text: str) -> dict:
    """Parse orders without storing them; return counts and warnings."""
    state = load_state(room)
    parsed = parser.parse_orders(text, state, player.faction_id)
    warnings = [w for order in parsed for w in order.warnings]
    return {
        "parsed": len(parsed),
        "warnings": warnings,
        "ok": not warnings,
    }


def submit_orders(room: Room, player: RoomPlayer, text: str) -> dict:
    """Validate, store, and persist a player's orders for the next turn."""
    with _lock:
        feedback = parse_feedback(room, player, text)
        payload = {
            "orders": text,
            "warnings": feedback["warnings"],
            "parsed": feedback["parsed"],
            "at": datetime.now(timezone.utc).isoformat(),
        }
        room.store_submission(player.faction_id, payload)
        _write_order_file(room, player.faction_id, text)
        feedback.update({"turn": room.next_turn()})
        return feedback


def _write_order_file(room: Room, faction_id: str, text: str) -> None:
    orders_dir = room.game_dir() / "orders"
    orders_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(orders_dir / f"{faction_id}_turn{room.next_turn()}.txt", text)


# ============================================================================
# turn resolution
# ============================================================================


def resolve_turn(room: Room, force: bool = False) -> dict:
    """Run the engine for the next turn. Returns the per-player reports."""
    with _lock:
        turn = room.next_turn()
        state = load_state(room)
        bucket = room.submissions.get(turn, {})

        if not force and not room.all_submitted(turn):
            missing = [
                p.display_name
                for p in room.joined_players()
                if p.faction_id not in bucket
            ]
            raise NotReadyError(f"Still waiting on: {', '.join(missing)}")

        try:
            backup = backups.create_pre_turn_backup(room, turn)
        except backups.BackupError as exc:
            _record_resolution_event(
                room, turn, "backup_failed", error_type=type(exc).__name__
            )
            logger.error(
                "turn_backup_failed room=%s turn=%s error_type=%s",
                room.code,
                turn,
                type(exc).__name__,
            )
            raise BackupUnavailableError from exc

        _record_resolution_event(
            room, turn, "started", backup=backup, state_version=backup.state_version
        )
        logger.info(
            "turn_resolution_started room=%s turn=%s backup=%s state_version=%s",
            room.code,
            turn,
            backup.relative_path,
            backup.state_version,
        )

        # Captured so a failed publication can put the room back exactly as it
        # was. Everything from here to store_reports is one turn or none.
        pre_turn = _PreTurnRoom(
            reports={t: dict(v) for t, v in room.reports.items()},
            submissions={t: dict(v) for t, v in room.submissions.items()},
            last_resolved_turn=room.last_resolved_turn,
        )

        try:
            orders_by_player = {}
            for faction_id in state.factions.keys():
                if faction_id == "independent":
                    continue
                text = bucket.get(faction_id, {}).get("orders", "")
                if text:
                    orders_by_player[faction_id] = parser.parse_orders(
                        text, state, faction_id
                    )
                else:
                    orders_by_player[faction_id] = []

            seed = deterministic_seed(room, turn)
            state, turn_log = engine.run_turn(state, orders_by_player, seed)

            storage.save_game_state(state, room.game_dir())
            _snapshot_state(room, turn)
            try:
                _record_turn_events(room, turn, seed, turn_log)
            except OSError:
                # Observability must not make a valid turn unresolvable. The
                # recovery log still records the completed turn below.
                logger.exception(
                    "turn_event_record_failed room=%s turn=%s", room.code, turn
                )

            reports = reporting.generate_player_reports(
                state, turn_log, orders_by_player
            )
            _write_report_files(room, turn, reports)
            room.store_reports(turn, reports)
        except Exception as exc:
            _record_resolution_event(
                room,
                turn,
                "failed",
                backup=backup,
                state_version=backup.state_version,
                error_type=type(exc).__name__,
            )
            logger.exception(
                "turn_resolution_failed room=%s turn=%s backup=%s error_type=%s",
                room.code,
                turn,
                backup.relative_path,
                type(exc).__name__,
            )
            _rollback_turn(room, turn, backup, pre_turn)
            raise

        _record_resolution_event(
            room,
            turn,
            "completed",
            backup=backup,
            state_version=backup.state_version,
            seed=seed,
            post_state_sha=_state_sha(room),
        )
        logger.info(
            "turn_resolution_completed room=%s turn=%s backup=%s seed=%s",
            room.code,
            turn,
            backup.relative_path,
            seed,
        )
        return {"turn": turn, "seed": seed, "reports": reports}


@dataclass(frozen=True)
class _PreTurnRoom:
    """The room bookkeeping a failed turn has to hand back."""

    reports: dict[int, dict]
    submissions: dict[int, dict]
    last_resolved_turn: int


def _rollback_turn(
    room: Room, turn: int, backup: backups.BackupRecord, pre_turn: _PreTurnRoom
) -> None:
    """Undo a turn whose publication failed after the state was saved.

    Without this the game sits at turn N while the room registry sits at N-1,
    and the retry resolves turn N onto an already-advanced state. The pre-turn
    backup is verified when it is created, so the authoritative state file is
    restored from it rather than recomputed. Derived per-turn artefacts are
    removed so nothing can read half of a turn that never happened.

    The room's own registry entry is restored in place; the backup's copy of
    rooms.json is deliberately not used, because it holds every other room too.
    """
    try:
        _atomic_write_text(
            room.game_dir() / "state.json",
            (backup.path / "game" / "state.json").read_text(encoding="utf-8"),
        )
        (room.game_dir() / f"state_turn{turn}.json").unlink(missing_ok=True)
        reports_dir = room.game_dir() / "reports"
        if reports_dir.is_dir():
            for path in reports_dir.glob(f"*_turn{turn}.txt"):
                path.unlink(missing_ok=True)

        room.reports = pre_turn.reports
        room.submissions = pre_turn.submissions
        room.last_resolved_turn = pre_turn.last_resolved_turn
        default_store().save()
    except Exception:
        _record_resolution_event(
            room,
            turn,
            "rollback_failed",
            backup=backup,
            state_version=backup.state_version,
        )
        logger.exception(
            "turn_rollback_failed room=%s turn=%s backup=%s",
            room.code,
            turn,
            backup.relative_path,
        )
        return

    _record_resolution_event(
        room,
        turn,
        "rolled_back",
        backup=backup,
        state_version=backup.state_version,
        post_state_sha=_state_sha(room),
    )
    logger.warning(
        "turn_rolled_back room=%s turn=%s backup=%s",
        room.code,
        turn,
        backup.relative_path,
    )


def deterministic_seed(room: Room, turn: int) -> int:
    """A stable, reproducible seed per (room, turn)."""
    digest = hashlib.sha256(f"{room.code}:{turn}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _write_report_files(room: Room, turn: int, reports: dict[str, str]) -> None:
    reports_dir = room.game_dir() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for faction_id, text in reports.items():
        _atomic_write_text(reports_dir / f"{faction_id}_turn{turn}.txt", text)


def _atomic_write_text(path: Path, text: str) -> None:
    """Publish an order/report file only after its complete contents are written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=".write-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(text)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _record_turn_events(
    room: Room,
    turn: int,
    seed: int,
    turn_log,
) -> None:
    """Persist the operator-visible outcome without orders or credentials."""
    payload = {
        "turn": turn,
        "seed": seed,
        "events": [asdict(event) for event in turn_log.events],
    }
    path = room.game_dir() / "turn_events.jsonl"
    _atomic_write_text(path, _append_json_line(path, payload))


def _record_resolution_event(
    room: Room,
    turn: int,
    status: str,
    *,
    backup: backups.BackupRecord | None = None,
    state_version: str = "",
    seed: int | None = None,
    error_type: str = "",
    post_state_sha: str = "",
) -> None:
    """Append safe recovery metadata without order text or credentials."""
    event = {
        "at": datetime.now(timezone.utc).isoformat(),
        "room": room.code,
        "turn": turn,
        "status": status,
        "backup": backup.relative_path if backup else "",
        "state_version": state_version,
    }
    if seed is not None:
        event["seed"] = seed
    if error_type:
        event["error_type"] = error_type
    if post_state_sha:
        event["post_state_sha"] = post_state_sha
    _atomic_write_text(
        room.game_dir() / "resolution_events.jsonl",
        _append_json_line(room.game_dir() / "resolution_events.jsonl", event),
    )


def _state_sha(room: Room) -> str:
    """SHA-256 of the current state.json — the determinism fingerprint."""
    try:
        raw = (room.game_dir() / "state.json").read_bytes()
    except OSError:
        return ""
    return hashlib.sha256(raw).hexdigest()


def _append_json_line(path: Path, event: dict) -> str:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    return existing + json.dumps(event, separators=(",", ":")) + "\n"


def _read_jsonl(path: Path, limit: int | None = 20) -> list[dict]:
    """Read valid records from a small append-only operator log.

    ``limit`` keeps the newest N records for dashboard snippets. Pass
    ``limit=None`` when the full history is required (determinism verify).
    """
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict] = []
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
        if limit is not None and len(records) >= limit:
            break
    records.reverse()
    return records


class NotReadyError(Exception):
    pass


class BackupUnavailableError(Exception):
    """Turn resolution is blocked until a valid pre-turn backup can be made."""


# ============================================================================
# structured per-player view (for agents)
# ============================================================================


def player_state(room: Room, faction_id: str) -> dict:
    """A fogged JSON view of the world from one faction's seat.

    Thin adapter: the pure extraction lives in
    ``webapp.ai.context.player_state_from_state`` so the headless arena feeds
    the model the exact same payload.
    """
    state = load_state(room)
    return agent_context.player_state_from_state(
        state, faction_id, game_id=room.code
    )


def map_overlay(
    room: Room,
    faction_id: str | None,
    *,
    all_visible: bool = False,
    state: models.GameState | None = None,
) -> dict | None:
    """
    The live board as one seat sees it, for ``mapview.render_svg``.

    Returns None before the game exists or for a spectator with no seat, so the
    map falls back to the plain published version. ``all_visible`` is reserved
    for the host dashboard and never used by player-facing pages. ``state``
    lets callers overlay a historical snapshot (``?turn=N``).
    """
    from webapp import mapview

    if faction_id is None and not all_visible:
        return None
    try:
        state = state or load_state(room)
    except (FileNotFoundError, RuntimeError, TurnNotFoundError):
        return None
    if faction_id is not None and faction_id not in state.factions:
        return None

    # Stable faction colours: by seat, so a player's colour never moves.
    slots = {p.faction_id: p.slot for p in room.players}
    colors = {
        fid: mapview.faction_color(slots.get(fid, i))
        for i, fid in enumerate(sorted(state.factions))
    }

    observed = (
        set(state.world_map.cities)
        if all_visible
        else _observed_city_ids(state, faction_id)
    )
    holder_of: dict[str, str] = {}
    for fid, faction in state.factions.items():
        for city_id in faction.controlled_city_ids:
            holder_of[city_id] = fid

    cities: dict[str, dict] = {}
    for city_id in state.world_map.cities:
        mine_chars = [
            c
            for c in state.characters.values()
            if (all_visible or c.faction_id == faction_id)
            and c.location_city_id == city_id
            and not c.is_dead
            and not c.is_prisoner
        ]
        mine_units = sum(
            s.count
            for s in state.unit_stacks.values()
            if (all_visible or s.faction_id == faction_id)
            and s.location_city_id == city_id
        )
        mine_ships = sum(
            1
            for s in state.ships.values()
            if (all_visible or s.faction_id == faction_id)
            and s.location_city_id == city_id
        )
        is_observed = city_id in observed
        holder = holder_of.get(city_id) if is_observed else None
        secured = _secured_by(state, city_id) if is_observed else None
        entry = {
            "observed": is_observed,
            "master": all_visible,
            "characters": len(mine_chars),
            "units": mine_units,
            "ships": mine_ships,
        }
        if holder:
            entry["holder_id"] = holder
            entry["holder_name"] = state.factions[holder].name
            entry["holder_color"] = colors.get(holder, "#888888")
        if secured:
            entry["secured_by_name"] = state.factions[secured].name
        if is_observed:
            # The pennant shows sovereignty; who may actually tax and recruit
            # here can be someone else entirely. Spell all three out so the
            # overlay explains itself instead of only colouring the map.
            if all_visible:
                authority = territory.authority_ids(state, city_id)

                def faction_name(fid: str | None) -> str:
                    return state.factions[fid].name if fid else "none"

                entry["sovereign_name"] = faction_name(authority["sovereign"])
                entry["occupier_name"] = faction_name(authority["occupier"])
                entry["administrator_name"] = faction_name(authority["administrator"])
            else:
                held = territory.authority_names(state, city_id, faction_id)
                if held:
                    entry["sovereign_name"] = held["sovereign"]
                    entry["occupier_name"] = held["occupier"]
                    entry["administrator_name"] = held["administrator"]
        cities[city_id] = entry

    # The key counts only what this seat is entitled to see, so the numbers
    # match the pennants actually drawn on the map.
    factions = []
    for fid in sorted(state.factions, key=lambda f: (state.factions[f].is_npc, f)):
        known = sum(1 for cid, entry in cities.items() if entry.get("holder_id") == fid)
        if not known and fid != faction_id and not all_visible:
            continue
        factions.append(
            {
                "id": fid,
                "name": state.factions[fid].name,
                "color": colors.get(fid, "#888888"),
                "cities": known,
            }
        )

    return {
        "turn": state.turn_number,
        "faction_id": faction_id or "",
        "cities": cities,
        "factions": factions,
    }


def ai_map(
    room: Room,
    faction_id: str | None,
    *,
    fmt: str = "json",
    turn: int | None = None,
    all_visible: bool = False,
) -> dict:
    """Map payloads for AI consumption (M5).

    ``fmt`` is one of ``json`` (compact board with coordinates and fog of
    war), ``svg`` (rendered board), or ``png`` (rasterised board for
    vision-capable models). ``turn`` rewinds to a per-turn snapshot. The
    returned dict has exactly one key, named after ``fmt``.
    """
    from webapp import mapimg, mapview

    state = load_state(room, turn=turn)
    overlay = map_overlay(room, faction_id, all_visible=all_visible, state=state)
    if fmt == "json":
        return {"json": _ai_board_json(room, state, faction_id, all_visible)}
    svg = mapview.render_svg(room.map_file, overlay)
    if fmt == "svg":
        return {"svg": svg}
    if fmt == "png":
        return {"png": mapimg.svg_to_png(svg)}
    raise ValueError(f"Unknown map format '{fmt}'.")


def _ai_board_json(
    room: Room,
    state: models.GameState,
    faction_id: str | None,
    all_visible: bool,
) -> dict:
    """Compact, coordinate-bearing board view for text-only models."""
    try:
        positions = mapview.positions(room.map_file)
    except Exception:  # noqa: BLE001 - coordinates are an enhancement
        positions = {}
    observed = (
        set(state.world_map.cities)
        if all_visible
        else _observed_city_ids(state, faction_id or "")
    )
    holder_of: dict[str, str] = {}
    for fid, faction in state.factions.items():
        for city_id in faction.controlled_city_ids:
            holder_of[city_id] = fid

    cities = []
    for city_id, city in sorted(
        state.world_map.cities.items(), key=lambda item: item[1].name
    ):
        x, y = positions.get(city_id, (None, None))
        known = all_visible or city_id in observed
        entry = {
            "id": city_id,
            "name": city.name,
            "x": round(x, 1) if x is not None else None,
            "y": round(y, 1) if y is not None else None,
            "region": city.region,
            "population_band": city.population_band.value,
            "is_port": city.is_port,
            "is_ruin": city.is_ruin,
            "terrain": sorted(t for t in city.terrain),
            "observed": known,
        }
        if known:
            entry["holder"] = holder_of.get(city_id)
        cities.append(entry)

    characters = []
    for char in state.characters.values():
        if char.is_dead or char.is_prisoner:
            continue
        visible = (
            all_visible
            or char.faction_id == faction_id
            or char.location_city_id in observed
        )
        if not visible:
            continue
        characters.append(
            {
                "name": char.name,
                "faction_id": char.faction_id,
                "city_id": char.location_city_id,
                "is_leader": char.is_leader,
                "combat_skill": char.combat_skill,
                "magic_skill": char.magic_skill,
                "health": char.health,
            }
        )

    return {
        "turn": state.turn_number,
        "map_file": room.map_file,
        "faction_id": faction_id or "",
        "all_visible": all_visible,
        "cities": cities,
        "characters": characters,
    }


# ============================================================================
# lobby helpers
# ============================================================================


def _faction_city_names(state: models.GameState, city_ids) -> list[str]:
    return sorted(
        state.world_map.cities[city_id].name
        for city_id in city_ids
        if city_id in state.world_map.cities
    )


def _master_city_name(state: models.GameState, city_id: str) -> str:
    city = state.world_map.cities.get(city_id)
    return city.name if city else city_id or "unknown location"


def _master_order_row(order, state: models.GameState, *, queue_entry=None) -> dict:
    """Return a safe, readable command row for the host inspector."""
    actor_id = getattr(order, "actor_id", "")
    if not actor_id:
        actor_id = getattr(order, "summoner_id", "") or getattr(order, "teacher_id", "")
    actor = state.characters.get(actor_id)
    row = {
        "type": order.order_type(),
        "text": (getattr(order, "original_text", "") or order.order_type()).strip(),
        "actor": actor.name if actor else "",
        "warnings": list(getattr(order, "warnings", []) or []),
    }
    if queue_entry is not None:
        row["release_turn"] = queue_entry.release_turn
        row["release_hour"] = queue_entry.release_hour
        row["repeat_remaining"] = queue_entry.repeat_remaining
    return row


def master_player_detail(room: Room, faction_id: str) -> dict:
    """Build the host-only inspection view for one faction."""
    state = load_state(room)
    faction = state.factions.get(faction_id)
    if faction is None:
        raise KeyError(faction_id)

    player = next((p for p in room.players if p.faction_id == faction_id), None)
    characters = sorted(
        (c for c in state.characters.values() if c.faction_id == faction_id),
        key=lambda c: (c.is_dead, c.is_prisoner, c.name.lower()),
    )
    resources = Counter()
    for character in characters:
        resources.update(character.resources)

    city_names = {
        city_id: city.name for city_id, city in state.world_map.cities.items()
    }
    character_names = {
        character.id: character.name for character in state.characters.values()
    }
    characters_view = []
    for character in characters:
        characters_view.append(
            {
                "name": character.name,
                "title": character.title,
                "is_leader": character.is_leader,
                "status": "dead"
                if character.is_dead
                else "prisoner"
                if character.is_prisoner
                else "active",
                "location": _master_city_name(state, character.location_city_id),
                "position": getattr(
                    character.location_position, "value", character.location_position
                ),
                "gold": round(character.gold, 1),
                "health": character.health,
                "movement": character.movement_points,
                "combat": character.combat_skill,
                "magic": character.magic_skill,
                "religion": character.religion_skill,
                "resources": dict(sorted(character.resources.items())),
            }
        )

    units = []
    for stack in state.unit_stacks.values():
        if stack.faction_id != faction_id:
            continue
        units.append(
            {
                "type": stack.unit_type.value,
                "count": stack.count,
                "location": _master_city_name(state, stack.location_city_id),
                "owner": character_names.get(stack.owner_character_id, "faction pool"),
            }
        )
    units.sort(key=lambda item: (item["type"], item["location"], item["owner"]))

    ships = []
    for ship in state.ships.values():
        if ship.faction_id != faction_id:
            continue
        ships.append(
            {
                "type": ship.ship_type.value,
                "capacity": ship.capacity,
                "location": _master_city_name(state, ship.location_city_id),
                "owner": character_names.get(ship.owner_character_id, "faction pool"),
            }
        )
    ships.sort(key=lambda item: (item["type"], item["location"], item["owner"]))

    items = []
    for item in state.magical_items.values():
        holder = state.characters.get(item.holder_character_id)
        if not holder or holder.faction_id != faction_id:
            continue
        items.append(
            {
                "name": item.name,
                "type": item.item_type.value,
                "holder": holder.name,
                "power": f"{item.power_current}/{item.power_max}"
                if item.power_max
                else "-",
            }
        )
    items.sort(key=lambda item: item["name"].lower())

    creatures = []
    for creature in state.summoned_creatures.values():
        summoner = state.characters.get(creature.summoner_id)
        if not summoner or summoner.faction_id != faction_id:
            continue
        creatures.append(
            {
                "type": creature.creature_type.value,
                "count": creature.count,
                "summoner": summoner.name,
                "expires": creature.expires_turn or "never",
            }
        )

    elite_units = []
    for unit in state.elite_units.values():
        if unit.faction_id != faction_id:
            continue
        elite_units.append(
            {
                "name": unit.name,
                "size": unit.size,
                "level": unit.combat_level,
                "leader": character_names.get(unit.leader_character_id, "unknown"),
                "location": _master_city_name(state, unit.location_city_id),
            }
        )

    current_submission = room.submissions.get(room.next_turn(), {}).get(faction_id, {})
    current_text = current_submission.get("orders", "")
    try:
        parsed_orders = (
            parser.parse_orders(current_text, state, faction_id) if current_text else []
        )
    except Exception:  # a malformed legacy submission should still be inspectable
        parsed_orders = []
    commands = [_master_order_row(order, state) for order in parsed_orders]

    queued_commands = []
    for actor_id, queue in state.order_queues.items():
        actor = state.characters.get(actor_id)
        if not actor or actor.faction_id != faction_id:
            continue
        for entry in queue:
            if entry.order is None:
                continue
            queued_commands.append(
                _master_order_row(entry.order, state, queue_entry=entry)
            )
    queued_commands.sort(key=lambda row: (row["actor"].lower(), row["type"]))

    latest_report = room.reports.get(room.last_resolved_turn, {}).get(faction_id, "")
    return {
        "faction": {
            "id": faction.id,
            "name": faction.name,
            "is_npc": faction.is_npc,
            "player": player.display_name if player else "unclaimed seat",
            "kind": player.kind if player else "empty",
            "start_city": city_names.get(player.start_city, player.start_city)
            if player
            else "",
            "gold": round(faction.treasury + sum(c.gold for c in characters), 1),
            "treasury": round(faction.treasury, 1),
            "wage_debt": round(faction.wage_debt, 1),
            "loan_balance": round(faction.loan_balance, 1),
            "sovereign_cities": _faction_city_names(state, faction.controlled_city_ids),
            "secured_cities": _faction_city_names(state, faction.secured_city_ids),
            "allies": sorted(
                state.factions[fid].name
                for fid in faction.allies
                if fid in state.factions
            ),
            "enemies": sorted(
                state.factions[fid].name
                for fid in faction.enemies
                if fid in state.factions
            ),
        },
        "turn": state.turn_number,
        "next_turn": room.next_turn(),
        "resources": dict(sorted(resources.items())),
        "characters": characters_view,
        "units": units,
        "ships": ships,
        "items": items,
        "creatures": creatures,
        "elite_units": elite_units,
        "submission": {
            "submitted": bool(current_submission),
            "at": current_submission.get("at", ""),
            "parsed": current_submission.get("parsed", len(commands)),
            "warnings": current_submission.get("warnings", []),
            "text": current_text,
            "commands": commands,
        },
        "queued_commands": queued_commands,
        "latest_report": latest_report,
    }


def master_dashboard(
    room: Room, *, phase_filter: str = "", faction_filter: str = ""
) -> dict:
    """Build a full-state, human-readable view for the gamemaster.

    ``phase_filter``/``faction_filter`` filter the gameplay timeline (engine
    phase name / faction id); empty means no filter. Named with _filter
    suffixes because the engine faction loop below rebinds ``faction``.
    """
    state = load_state(room)
    status = room_status(room)
    player_by_faction = {p.faction_id: p for p in room.players}
    slots = {p.faction_id: p.slot for p in room.players}

    factions = []
    for faction_id, faction in state.factions.items():
        characters = [
            c for c in state.characters.values() if c.faction_id == faction_id
        ]
        units = Counter(
            stack.unit_type.value
            for stack in state.unit_stacks.values()
            if stack.faction_id == faction_id
        )
        unit_totals = Counter()
        for stack in state.unit_stacks.values():
            if stack.faction_id == faction_id:
                unit_totals[stack.unit_type.value] += stack.count
        player = player_by_faction.get(faction_id)
        factions.append(
            {
                "id": faction_id,
                "name": faction.name,
                "is_npc": faction.is_npc,
                "color": mapview.faction_color(slots.get(faction_id, len(factions))),
                "player": player.display_name if player else "unclaimed seat",
                "kind": player.kind if player else "empty",
                "start_city": (
                    _city_names(room).get(player.start_city, player.start_city)
                    if player
                    else ""
                ),
                "submitted": bool(
                    player
                    and player.faction_id in room.submissions.get(room.next_turn(), {})
                ),
                "gold": round(
                    faction.treasury + sum(c.gold for c in characters),
                    1,
                ),
                "sovereign_count": len(faction.controlled_city_ids),
                "sovereign_cities": _faction_city_names(
                    state, faction.controlled_city_ids
                ),
                "secured_count": len(faction.secured_city_ids),
                "secured_cities": _faction_city_names(state, faction.secured_city_ids),
                "free_characters": sum(
                    not c.is_dead and not c.is_prisoner for c in characters
                ),
                "prisoners": sum(c.is_prisoner for c in characters),
                "dead": sum(c.is_dead for c in characters),
                "soldiers": unit_totals.get("soldier", 0),
                "sailors": unit_totals.get("sailor", 0),
                "workers": unit_totals.get("worker", 0),
                "slaves": unit_totals.get("slave", 0),
                "ships": sum(s.faction_id == faction_id for s in state.ships.values()),
                "stacks": sum(units.values()),
            }
        )

    faction_names = {f["id"]: f["name"] for f in factions}
    turn_records = _read_jsonl(room.game_dir() / "turn_events.jsonl", limit=6)
    recent_events = []
    seen_phases = set()
    for record in reversed(turn_records):
        turn = record.get("turn", 0)
        evs = record.get("events") or []
        for event in reversed(evs):
            event = dict(event)
            event["turn"] = turn
            event["faction_name"] = faction_names.get(
                event.get("player_id", ""), "System"
            )
            if phase_filter and event.get("phase") != phase_filter:
                continue
            if faction_filter and event.get("player_id") != faction_filter:
                continue
            if event.get("phase"):
                seen_phases.add(event["phase"])
            recent_events.append(event)
            if len(recent_events) >= 48:
                break
        if len(recent_events) >= 48:
            break
    recent_events.reverse()
    timeline: list[dict] = []
    for event in recent_events:
        if not timeline or timeline[-1]["turn"] != event["turn"]:
            timeline.append({"turn": event["turn"], "events": [event]})
        else:
            timeline[-1]["events"].append(event)

    resolution_events = _read_jsonl(
        room.game_dir() / "resolution_events.jsonl", limit=12
    )
    last_resolution = resolution_events[-1] if resolution_events else None
    joined = len(room.joined_players())
    submitted = sum(
        p.faction_id in room.submissions.get(room.next_turn(), {})
        for p in room.joined_players()
    )
    if last_resolution and last_resolution.get("status") == "failed":
        headline = "Attention needed: the last resolution failed"
        health = "error"
    elif status["all_submitted"] and joined:
        headline = f"Turn {status['next_turn']} is ready to resolve"
        health = "ready"
    elif joined:
        headline = f"Waiting for {len(status['waiting_on'])} player(s)"
        health = "waiting"
    else:
        headline = "Waiting for players to join"
        health = "waiting"

    city_rows = []
    for city in sorted(state.world_map.cities.values(), key=lambda item: item.name):
        authority = territory.authority_ids(state, city.id)
        city_rows.append(
            {
                "name": city.name,
                "region": city.region or "unmapped",
                "sovereign": faction_names.get(authority["sovereign"], "none"),
                "occupier": faction_names.get(authority["occupier"], "none"),
                "administrator": faction_names.get(authority["administrator"], "none"),
                "fortification": city.fortification_level,
            }
        )

    return {
        "status": status,
        "headline": headline,
        "health": health,
        "joined": joined,
        "submitted": submitted,
        "factions": factions,
        "city_rows": city_rows,
        "recent_events": recent_events,
        "timeline": timeline,
        "phases": sorted(seen_phases),
        "resolution_events": resolution_events,
        "last_resolution": last_resolution,
        "pending_queue_count": len(state.order_queues),
        "map_file": room.map_file,
        "last_turn": state.turn_number,
    }


def _city_names(room: Room) -> dict[str, str]:
    try:
        from webapp.mapview import load_raw_map

        return {
            c["id"]: c["name"] for c in load_raw_map(room.map_file).get("cities", [])
        }
    except FileNotFoundError:
        return {}


def room_status(room: Room) -> dict:
    """Public status: players, submissions, report availability."""
    city_names = _city_names(room)
    turn = room.next_turn()
    bucket = room.submissions.get(turn, {})
    players = []
    for p in room.players:
        entry = {
            "slot": p.slot,
            "faction_id": p.faction_id,
            "faction_name": p.faction_name,
            "display_name": p.display_name,
            "kind": p.kind,
            "bot": default_registry().is_bot(room.code, p.faction_id),
            "start_city": city_names.get(p.start_city, p.start_city),
        }
        if p.kind != "empty":
            entry["submitted"] = p.faction_id in bucket
            entry["parsed"] = bucket.get(p.faction_id, {}).get("parsed", 0)
        players.append(entry)

    return {
        "code": room.code,
        "name": room.name,
        "turn": room.last_resolved_turn,
        "next_turn": turn,
        "players": players,
        "waiting_on": [
            p.display_name for p in room.joined_players() if p.faction_id not in bucket
        ],
        "all_submitted": room.all_submitted(turn),
        "available_reports": sorted(room.reports.keys()),
    }
