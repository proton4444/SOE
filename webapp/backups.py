"""Pre-turn snapshots and restore helpers for the controlled beta.

Snapshots are intentionally file-based.  A snapshot contains the server room
registry and one complete game directory, which is enough to restore the
state that was authoritative immediately before a turn was resolved.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from soe import storage

from webapp.rooms import Room, ROOMS_FILE, SERVER_DATA


BACKUP_ROOT = Path(os.environ.get("SOE_BACKUP_DIR", str(SERVER_DATA / "backups")))


class BackupError(RuntimeError):
    """Raised when a recoverable pre-turn snapshot cannot be verified."""


@dataclass(frozen=True)
class BackupRecord:
    path: Path
    room_code: str
    turn: int
    state_version: str
    created_at: str

    @property
    def relative_path(self) -> str:
        """Return a safe operator-facing path without credentials."""
        try:
            return str(self.path.relative_to(BACKUP_ROOT))
        except ValueError:
            return self.path.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def create_pre_turn_backup(room: Room, turn: int) -> BackupRecord:
    """Create and verify a snapshot before any turn-state mutation.

    The final directory is published only after the room registry and complete
    game directory have been copied and loaded successfully from the staging
    directory.  Filenames contain only room/turn/time/hash identifiers.
    """
    state_file = room.game_dir() / "state.json"
    rooms_file = ROOMS_FILE
    if not state_file.is_file():
        raise BackupError(f"Missing game state for room {room.code}")
    if not rooms_file.is_file():
        raise BackupError("Missing server room registry")

    state_version = _sha256(state_file)
    created_at = datetime.now(timezone.utc).isoformat()
    name = f"turn_{turn}_{_timestamp()}_{state_version[:12]}"
    room_root = BACKUP_ROOT / room.game_id()
    final_path = room_root / name
    staging_path = room_root / f".{name}.tmp-{secrets.token_hex(8)}"

    try:
        staging_path.mkdir(parents=True, exist_ok=False)
        shutil.copy2(rooms_file, staging_path / "rooms.json")
        shutil.copytree(room.game_dir(), staging_path / "game")

        copied_state = staging_path / "game" / "state.json"
        copied_rooms = staging_path / "rooms.json"
        if _sha256(copied_state) != state_version:
            raise BackupError("Pre-turn state snapshot hash verification failed")
        json.loads(copied_rooms.read_text(encoding="utf-8"))
        if storage.load_game_state(staging_path / "game") is None:
            raise BackupError("Pre-turn state snapshot could not be loaded")

        manifest = {
            "schema_version": 1,
            "room_code": room.code,
            "game_id": room.game_id(),
            "turn": turn,
            "authoritative_turn": turn - 1,
            "created_at": created_at,
            "state_version": state_version,
            "server_registry": "rooms.json",
            "game_directory": "game",
        }
        (staging_path / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        staging_path.replace(final_path)
    except BackupError:
        shutil.rmtree(staging_path, ignore_errors=True)
        raise
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        shutil.rmtree(staging_path, ignore_errors=True)
        raise BackupError("Could not create or verify the pre-turn backup") from exc

    return BackupRecord(
        path=final_path,
        room_code=room.code,
        turn=turn,
        state_version=state_version,
        created_at=created_at,
    )


def validate_backup(path: Path) -> dict:
    """Validate a snapshot and return its non-sensitive manifest."""
    path = Path(path)
    manifest_path = path / "manifest.json"
    game_dir = path / "game"
    rooms_file = path / "rooms.json"
    if not manifest_path.is_file() or not game_dir.is_dir() or not rooms_file.is_file():
        raise BackupError("Backup is missing required files")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    json.loads(rooms_file.read_text(encoding="utf-8"))
    state_file = game_dir / "state.json"
    if not state_file.is_file():
        raise BackupError("Backup is missing game state")
    if _sha256(state_file) != manifest.get("state_version"):
        raise BackupError("Backup state hash does not match its manifest")
    if storage.load_game_state(game_dir) is None:
        raise BackupError("Backup game state could not be loaded")
    return manifest


def _registry_with_room_restored(
    rooms_file: Path, snapshot_registry: dict, room_code: str
) -> dict:
    """Put one room's snapshot entry back into the live registry, in place.

    Every other room keeps whatever the live registry currently says about it,
    which is the whole point: a snapshot is only authoritative for the room it
    was taken for.
    """
    restored = next(
        (
            entry
            for entry in snapshot_registry.get("rooms", [])
            if str(entry.get("code")) == room_code
        ),
        None,
    )
    if restored is None:
        raise BackupError(f"Backup registry has no entry for room {room_code}")

    if not rooms_file.exists():
        return {"rooms": [restored]}

    try:
        live = json.loads(rooms_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BackupError(
            "The live room registry is unreadable, so a single room cannot be "
            "spliced into it. Re-run with whole_registry=True to restore the "
            "snapshot's entire registry instead."
        ) from exc

    rooms = []
    replaced = False
    for entry in live.get("rooms", []):
        if str(entry.get("code")) == room_code:
            rooms.append(restored)
            replaced = True
        else:
            rooms.append(entry)
    if not replaced:
        rooms.append(restored)
    return {"rooms": rooms}


def restore_backup(
    path: Path,
    *,
    rooms_file: Path = ROOMS_FILE,
    games_root: Path | None = None,
    whole_registry: bool = False,
) -> dict:
    """Restore a validated snapshot, preserving current targets beside them.

    This helper is intended for a stopped application.  The previous registry
    and game directory are kept beside the restored ones so an operator can
    inspect or undo the restore attempt.

    A snapshot carries the entire room registry, but it is only authoritative
    for the one room it was taken for.  By default just that room's entry is
    spliced back in, so recovering one game cannot rewind every other game on
    the server.  ``whole_registry=True`` restores the snapshot's full registry,
    which is correct only when the live registry is unusable or every room is
    being rolled back together.
    """
    path = Path(path)
    manifest = validate_backup(path)
    games_root = games_root or rooms_file.parent.parent / "games"
    rooms_file = Path(rooms_file)
    games_root = Path(games_root)
    room_code = str(manifest["room_code"])
    target_game = games_root / f"room_{room_code}"
    stamp = _timestamp()

    rooms_file.parent.mkdir(parents=True, exist_ok=True)
    games_root.mkdir(parents=True, exist_ok=True)

    snapshot_registry = json.loads((path / "rooms.json").read_text(encoding="utf-8"))
    if whole_registry:
        payload = snapshot_registry
    else:
        payload = _registry_with_room_restored(rooms_file, snapshot_registry, room_code)

    if rooms_file.exists():
        shutil.copy2(
            rooms_file, rooms_file.with_name(f"rooms.pre-restore-{stamp}.json")
        )
    rooms_file_tmp = rooms_file.with_suffix(".restore.tmp")
    rooms_file_tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    rooms_file_tmp.replace(rooms_file)

    if target_game.exists():
        target_game.replace(games_root / f"room_{room_code}.pre-restore-{stamp}")
    shutil.copytree(path / "game", target_game)
    return manifest
