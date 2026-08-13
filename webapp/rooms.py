"""
Room registry for the web server.

Rooms are link-based games: a short code plus a 4-digit PIN is all it takes to
join. Each room maps to an engine game directory under ``games/room_<code>``,
so the CLI can still inspect and process the same games.

State lives in ``server_data/rooms.json`` — one file, same file-based ethos as
the engine itself.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Unambiguous alphabet: no 0/O, 1/I.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Default faction names and leader names, one pair per slot.
FACTION_NAMES = [
    ("The Golden Empire", "Emperor Marcus"),
    ("The Silver Horde", "Khan Tengri"),
    ("The Crimson League", "Queen Aldara"),
    ("The Azure Dominion", "Lord Varn"),
    ("The Emerald Circle", "High Priestess Sable"),
    ("The Obsidian Pact", "General Thorne"),
]

# Tests point SOE_DATA_DIR / SOE_GAMES_DIR at a temp directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
GAMES_ROOT = Path(os.environ.get("SOE_GAMES_DIR", str(_REPO_ROOT / "games")))
ROOMS_FILE = SERVER_DATA / "rooms.json"
MAX_PLAYERS = 6

#: A 4-digit PIN is only 10,000 guesses and the room page is reachable without
#: auth, so a script would walk the space in seconds. Lock joining after a
#: handful of misses. The cost is that someone who knows a room code can
#: briefly lock its lobby; a timed lock, not a permanent one, keeps that a
#: nuisance rather than a takeover.
MAX_PIN_ATTEMPTS = 5
PIN_LOCKOUT_SECONDS = 15 * 60


class RoomRegistryError(RuntimeError):
    """The persisted room registry cannot be trusted for startup."""


@dataclass
class RoomPlayer:
    slot: int
    faction_id: str
    faction_name: str
    display_name: str = ""
    kind: str = "empty"  # empty | human | agent
    agent_key: str = ""
    start_city: str = ""  # assigned at game creation, seeded by room code


@dataclass
class Room:
    code: str
    pin: str
    name: str
    map_file: str
    host_key: str
    created_at: str
    slots: int
    players: list[RoomPlayer] = field(default_factory=list)
    # turn -> {faction_id: {"orders": text, "warnings": [..], "parsed": int, "at": iso}}
    submissions: dict[int, dict] = field(default_factory=dict)
    # turn -> {faction_id: report text}
    reports: dict[int, dict] = field(default_factory=dict)
    last_resolved_turn: int = 0

    def game_dir(self) -> Path:
        return GAMES_ROOT / f"room_{self.code}"

    def game_id(self) -> str:
        return f"room_{self.code}"

    def next_turn(self) -> int:
        return self.last_resolved_turn + 1

    def joined_players(self) -> list[RoomPlayer]:
        return [p for p in self.players if p.kind != "empty"]

    def all_submitted(self, turn: int) -> bool:
        submitted = self.submissions.get(turn, {})
        return all(p.faction_id in submitted for p in self.joined_players())

    def player_by_key(self, key: str) -> RoomPlayer | None:
        for p in self.players:
            if p.agent_key == key:
                return p
        return None

    # ------------------------------------------------------------------
    # turn bookkeeping
    # ------------------------------------------------------------------

    def store_submission(self, faction_id: str, payload: dict) -> None:
        store = default_store()
        with store.transaction():
            turn = self.next_turn()
            bucket = self.submissions.setdefault(turn, {})
            bucket[faction_id] = payload
            store.save()

    def store_reports(self, turn: int, reports: dict[str, str]) -> None:
        store = default_store()
        with store.transaction():
            self.reports[turn] = reports
            self.submissions.pop(turn, None)
            self.last_resolved_turn = turn
            store.save()


class RoomStore:
    """Thread-safe, file-backed registry of rooms."""

    def __init__(self, path: Path = ROOMS_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._rooms: dict[str, Room] = {}
        # code -> (consecutive wrong PINs, monotonic deadline of the lockout)
        self._pin_failures: dict[str, tuple[int, float]] = {}
        self._load()

    @contextmanager
    def transaction(self):
        """Serialise a read-modify-write of the registry with its own save.

        Sync FastAPI routes run in a threadpool, so join, submit and resolve
        can interleave even with ``--workers 1``. Without this the losing
        thread's ``save()`` writes a payload built before the winner's
        mutation and silently drops a seat or a turn of orders.
        """
        with self._lock:
            yield self

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # Starting with an empty registry would hide live games and could
            # cause an operator to create conflicting replacement rooms.
            raise RoomRegistryError(
                "The persisted room registry is unreadable; restore a backup before starting."
            ) from exc
        for raw in data.get("rooms", []):
            room = _room_from_dict(raw)
            if room:
                self._rooms[room.code] = room

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "rooms": [asdict(r) for r in self._rooms.values()],
            }
            # A per-write temp name: two writers sharing one tmp file would
            # have the loser replace the registry with a half-written copy.
            tmp = self.path.with_name(
                f"{self.path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
            )
            try:
                tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            finally:
                tmp.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def all(self) -> list[Room]:
        with self._lock:
            return list(self._rooms.values())

    def get(self, code: str) -> Room | None:
        with self._lock:
            return self._rooms.get(code.upper())

    def code_taken(self, code: str) -> bool:
        with self._lock:
            return code in self._rooms

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def create(self, name: str, slots: int, map_file: str) -> Room:
        with self._lock:
            slots = max(2, min(int(slots), MAX_PLAYERS))
            code = self._fresh_code()
            room = Room(
                code=code,
                pin=f"{secrets.randbelow(10000):04d}",
                name=name.strip() or f"Game {code}",
                map_file=map_file,
                host_key="host_" + secrets.token_hex(12),
                created_at=datetime.now(timezone.utc).isoformat(),
                slots=slots,
                players=[
                    RoomPlayer(
                        slot=i,
                        faction_id=f"player_{i + 1}",
                        faction_name=FACTION_NAMES[i][0],
                    )
                    for i in range(slots)
                ],
            )
            self._rooms[code] = room
            self.save()
            return room

    def pin_lock_remaining(self, code: str) -> float:
        """Seconds left on this room's join lockout; 0 when joining is open."""
        with self._lock:
            _, deadline = self._pin_failures.get(code.upper(), (0, 0.0))
            return max(0.0, deadline - time.monotonic())

    def _record_pin_failure(self, code: str) -> None:
        failures, _ = self._pin_failures.get(code, (0, 0.0))
        failures += 1
        deadline = (
            time.monotonic() + PIN_LOCKOUT_SECONDS
            if failures >= MAX_PIN_ATTEMPTS
            else 0.0
        )
        self._pin_failures[code] = (failures, deadline)

    def join(self, code: str, pin: str, display_name: str) -> tuple[Room, RoomPlayer]:
        """Claim the first open slot. Returns (room, player)."""
        with self._lock:
            code = code.upper()
            room = self._rooms.get(code)
            if not room:
                raise RoomError("No game found with that code.")
            locked_for = self.pin_lock_remaining(code)
            if locked_for:
                raise RoomError(
                    "Too many wrong PINs for this game. Try again in "
                    f"{int(locked_for // 60) + 1} minutes, or ask the host."
                )
            if not secrets.compare_digest(room.pin, pin.strip()):
                self._record_pin_failure(code)
                raise RoomError("Wrong PIN.")
            self._pin_failures.pop(code, None)
            display_name = display_name.strip()
            if not display_name:
                raise RoomError("Give yourself a name.")
            existing = self._player_named(room, display_name)
            if existing:
                # A display name is public lobby metadata, not proof of identity.
                # Returning it here would disclose the existing player's key.
                raise RoomError("That name is already taken in this game.")
            for player in room.players:
                if player.kind == "empty":
                    player.display_name = display_name
                    player.kind = "agent"  # the key is the credential, API or UI
                    player.agent_key = "soe_" + secrets.token_hex(12)
                    self.save()
                    return room, player
            raise RoomError("This game is full.")

    def _player_named(self, room: Room, display_name: str) -> RoomPlayer | None:
        for player in room.players:
            if (
                player.kind != "empty"
                and player.display_name.lower() == display_name.lower()
            ):
                return player
        return None

    def _fresh_code(self) -> str:
        for _ in range(100):
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))
            if code not in self._rooms:
                return code
        raise RoomError("Could not allocate a room code.")


_store: RoomStore | None = None


def default_store() -> RoomStore:
    global _store
    if _store is None:
        _store = RoomStore()
    return _store


class RoomError(Exception):
    pass


def _room_from_dict(raw: dict) -> Room | None:
    try:
        raw = dict(raw)
        players = [_player_from_dict(p) for p in raw.pop("players", [])]
        for field_name in ("submissions", "reports"):
            values = raw.get(field_name) or {}
            raw[field_name] = {int(turn): payload for turn, payload in values.items()}
        room = Room(**raw)
        room.players = players
        return room
    except (AttributeError, TypeError, KeyError, ValueError):
        return None


def _player_from_dict(raw: dict) -> RoomPlayer:
    return RoomPlayer(**raw)
