"""
Bridge between the web server and the engine.

The engine stays untouched: the server replicates what ``cli.py`` does —
initialise a game from a map and players, parse orders, run a seeded turn,
save state, write reports — and adds a structured per-player view so agents
can read the world without parsing prose.
"""

from __future__ import annotations

import hashlib
import random
import threading
from datetime import datetime, timezone
from pathlib import Path

from spoils_engine import (
    config,
    engine,
    map_loader,
    models,
    parser,
    reporting,
    storage,
)

from webapp.rooms import Room, RoomPlayer, default_store

_ROOT = Path(__file__).resolve().parent.parent
_MAPS_DIR = _ROOT / "maps"

# Prefer the full gazetteer map when present; sample stays as a fallback.
_PREFERRED_DEFAULT_MAP = "soe_world.json"
_FALLBACK_DEFAULT_MAP = "sample_map.json"

# Independent characters every game gets, so OFFER has someone to hire.
# ``locations`` is tried in order so the same list works on sample_map
# (albatross_city) and soe_world (kitesta / madegi_doy).
_DEFAULT_INDEPENDENTS = [
    {
        "name": "Wizard Ojibenmi",
        "gender": "male",
        "locations": ["albatross_city", "kitesta"],
        "skills": {"magic": 60},
    },
    {
        "name": "Bishop Nancy Lopenda",
        "gender": "female",
        "title": "bishop",
        "locations": ["madegi_doy"],
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
            world_map.cities.keys())
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
        game_state.world_map.cities.keys())
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


def _resolve_city_id(
    preferred: str | list[str] | None, city_ids: list[str]
) -> str:
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
        game_state.world_map.cities.keys())

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


def load_state(room: Room) -> models.GameState:
    state = storage.load_game_state(room.game_dir())
    if state is None:
        raise RuntimeError(f"Could not load game state for {room.code}")
    return state


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
    (orders_dir / f"{faction_id}_turn{room.next_turn()}.txt").write_text(
        text, encoding="utf-8"
    )


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

        reports = reporting.generate_player_reports(
            state, turn_log, orders_by_player
        )
        _write_report_files(room, turn, reports)
        room.store_reports(turn, reports)

        return {
            "turn": turn,
            "seed": seed,
            "reports": reports,
        }


def deterministic_seed(room: Room, turn: int) -> int:
    """A stable, reproducible seed per (room, turn)."""
    digest = hashlib.sha256(f"{room.code}:{turn}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _write_report_files(room: Room, turn: int, reports: dict[str, str]) -> None:
    reports_dir = room.game_dir() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for faction_id, text in reports.items():
        (reports_dir / f"{faction_id}_turn{turn}.txt").write_text(
            text, encoding="utf-8"
        )


class NotReadyError(Exception):
    pass


# ============================================================================
# structured per-player view (for agents)
# ============================================================================

def player_state(room: Room, faction_id: str) -> dict:
    """A fogged JSON view of the world from one faction's seat."""
    state = load_state(room)
    faction = state.factions[faction_id]

    characters = []
    for char in sorted(
        (c for c in state.characters.values() if c.faction_id == faction_id),
        key=lambda c: c.id,
    ):
        characters.append(_character_view(state, char))

    # The map's geography (names, ports, ruins, terrain, regions) is the
    # published board -- it is drawn for everyone on the landing page, so it is
    # not secret. Who holds a city is: that only shows where this faction has
    # eyes on the ground.
    observed = _observed_city_ids(state, faction_id)
    cities = []
    for city in sorted(state.world_map.cities.values(), key=lambda c: c.name):
        known = city.id in observed
        cities.append({
            "id": city.id,
            "name": city.name,
            "region": city.region,
            "population_band": city.population_band.value,
            "is_port": city.is_port,
            "is_ruin": city.is_ruin,
            "is_magic_free": city.is_magic_free,
            "terrain": sorted(t for t in city.terrain),
            "observed": known,
            "secured_by": _secured_by(state, city.id) if known else None,
            "controlled_by": faction_id if city.id in faction.controlled_city_ids else None,
        })

    return {
        "room": room.code,
        "turn": state.turn_number,
        "next_turn": state.turn_number + 1,
        "faction_id": faction_id,
        "faction_name": faction.name,
        "allies": sorted(faction.allies),
        "enemies": sorted(faction.enemies),
        "wage_debt": faction.wage_debt,
        "loan_balance": faction.loan_balance,
        "characters": characters,
        "cities": cities,
        "posted_messages": {
            cid: msg for cid, msg in state.posted_messages.items()
        },
    }


def _character_view(state: models.GameState, char: models.Character) -> dict:
    units = {}
    ships = []
    for stack in state.unit_stacks.values():
        if stack.faction_id == char.faction_id and stack.owner_character_id == char.id:
            units[stack.unit_type.value] = units.get(stack.unit_type.value, 0) + stack.count
    for ship in state.ships.values():
        if ship.faction_id == char.faction_id and ship.location_city_id == char.location_city_id:
            ships.append({"id": ship.id, "type": ship.ship_type.value, "location": ship.location_city_id})

    elite = [
        {"name": u.name, "size": u.size, "combat_level": u.combat_level}
        for u in state.elite_units.values()
        if u.leader_character_id == char.id
    ]
    creatures = [
        {"type": c.creature_type.value, "count": c.count}
        for c in state.summoned_creatures.values()
        if c.summoner_id == char.id
    ]
    prisoners = [
        {"id": p.id, "name": p.name}
        for p in state.characters.values()
        if p.captor_id == char.id
    ]

    city = state.world_map.cities.get(char.location_city_id)

    return {
        "id": char.id,
        "name": char.name,
        "title": char.title,
        "is_leader": char.is_leader,
        "location_city_id": char.location_city_id,
        "location_city_name": city.name if city else None,
        "location_position": char.location_position.value,
        "gold": char.gold,
        "health": char.health,
        "is_dead": char.is_dead,
        "is_prisoner": char.is_prisoner,
        "is_lurking": char.is_lurking,
        "is_noncom": char.is_noncom,
        "combat_skill": char.combat_skill,
        "magic_skill": char.magic_skill,
        "magic_power_current": char.magic_power_current,
        "religion_skill": char.religion_skill,
        "religious_power_current": char.religious_power_current,
        "trading_skill": char.trading_skill,
        "sailing_skill": char.sailing_skill,
        "resources": dict(char.resources),
        "units": units,
        "ships": ships,
        "elite_units": elite,
        "summoned_creatures": creatures,
        "prisoners": prisoners,
    }


def map_overlay(room: Room, faction_id: str | None) -> dict | None:
    """
    The live board as one seat sees it, for ``mapview.render_svg``.

    Returns None before the game exists or for a spectator with no seat, so the
    map falls back to the plain published version.
    """
    from webapp import mapview

    if faction_id is None:
        return None
    try:
        state = load_state(room)
    except (FileNotFoundError, RuntimeError):
        return None
    if faction_id not in state.factions:
        return None

    # Stable faction colours: by seat, so a player's colour never moves.
    slots = {p.faction_id: p.slot for p in room.players}
    colors = {
        fid: mapview.faction_color(slots.get(fid, i))
        for i, fid in enumerate(sorted(state.factions))
    }

    observed = _observed_city_ids(state, faction_id)
    holder_of: dict[str, str] = {}
    for fid, faction in state.factions.items():
        for city_id in faction.controlled_city_ids:
            holder_of[city_id] = fid

    cities: dict[str, dict] = {}
    for city_id in state.world_map.cities:
        mine_chars = [
            c for c in state.characters.values()
            if c.faction_id == faction_id and c.location_city_id == city_id
            and not c.is_dead and not c.is_prisoner
        ]
        mine_units = sum(
            s.count for s in state.unit_stacks.values()
            if s.faction_id == faction_id and s.location_city_id == city_id
        )
        mine_ships = sum(
            1 for s in state.ships.values()
            if s.faction_id == faction_id and s.location_city_id == city_id
        )
        is_observed = city_id in observed
        holder = holder_of.get(city_id) if is_observed else None
        secured = _secured_by(state, city_id) if is_observed else None
        entry = {
            "observed": is_observed,
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
        cities[city_id] = entry

    # The key counts only what this seat is entitled to see, so the numbers
    # match the pennants actually drawn on the map.
    factions = []
    for fid in sorted(state.factions, key=lambda f: (state.factions[f].is_npc, f)):
        known = sum(
            1 for cid, entry in cities.items() if entry.get("holder_id") == fid
        )
        if not known and fid != faction_id:
            continue
        factions.append({
            "id": fid,
            "name": state.factions[fid].name,
            "color": colors.get(fid, "#888888"),
            "cities": known,
        })

    return {
        "turn": state.turn_number,
        "faction_id": faction_id,
        "cities": cities,
        "factions": factions,
    }


def _observed_city_ids(state: models.GameState, faction_id: str) -> set[str]:
    """
    Cities this faction has eyes on: ones it holds, and ones where it has a
    living character, a unit stack, or a ship standing right now.

    Deliberately does not roll for sightings -- ``fog.collect_sightings`` is
    diced, and a status read must not consume luck or change between two GETs
    of the same turn. Detection belongs in the turn report.
    """
    faction = state.factions[faction_id]
    observed = set(faction.controlled_city_ids)
    for char in state.characters.values():
        if char.faction_id == faction_id and not char.is_dead and not char.is_prisoner:
            observed.add(char.location_city_id)
    for stack in state.unit_stacks.values():
        if stack.faction_id == faction_id:
            observed.add(stack.location_city_id)
    for ship in state.ships.values():
        if ship.faction_id == faction_id:
            observed.add(ship.location_city_id)
    observed.discard(None)
    return observed


def _secured_by(state: models.GameState, city_id: str) -> str | None:
    for faction in state.factions.values():
        if city_id in faction.secured_city_ids:
            return faction.id
    return None


# ============================================================================
# lobby helpers
# ============================================================================

def _city_names(room: Room) -> dict[str, str]:
    try:
        from webapp.mapview import load_raw_map

        return {c["id"]: c["name"] for c in load_raw_map(room.map_file).get("cities", [])}
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
            p.display_name
            for p in room.joined_players()
            if p.faction_id not in bucket
        ],
        "all_submitted": room.all_submitted(turn),
        "available_reports": sorted(room.reports.keys()),
    }
