"""
Blast radius of a pre-turn snapshot restore.

A snapshot contains the whole room registry but is only authoritative for the
one room it was taken for.  Restoring it must not rewind the other games on the
server, so by default only the backed-up room's entry is spliced back in.  The
full-registry swap is still available, but has to be asked for.

These run against a temporary data dir (SOE_DATA_DIR / SOE_GAMES_DIR) so the
repo's real games and rooms are never touched.
"""

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_test_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_store():
    from webapp import rooms
    from webapp.ai import registry as ai_registry
    from webapp.rooms import ROOMS_FILE

    rooms.default_store()._rooms.clear()
    ai_registry.default_registry()._profiles.clear()
    if ROOMS_FILE.exists():
        ROOMS_FILE.unlink()
    if ai_registry.AGENTS_FILE.exists():
        ai_registry.AGENTS_FILE.unlink()
    yield


def _room_with_a_resolved_turn():
    """Create a room, join it, and resolve turn 1. Returns the room payload."""
    created = client.post("/api/rooms", json={"name": "Test War", "slots": 2}).json()
    player = client.post(
        "/api/join",
        json={"code": created["code"], "pin": created["pin"], "name": "Alice"},
    ).json()
    client.post(
        f"/api/rooms/{created['code']}/orders?key={player['agent_key']}",
        json={"orders": "Recruit 20 soldiers."},
    )
    response = client.post(
        f"/api/rooms/{created['code']}/resolve",
        json={"force": True},
        headers={"X-Agent-Key": created["host_key"]},
    )
    assert response.status_code == 200, response.text
    return created


def _backup_of(code):
    from webapp import backups

    return next(
        path
        for path in (backups.BACKUP_ROOT / f"room_{code}").iterdir()
        if path.is_dir()
    )


def _reloaded(code):
    from webapp.rooms import ROOMS_FILE, RoomStore

    return RoomStore(ROOMS_FILE).get(code)


def _two_rooms_resolved_in_order():
    """Room A resolves first, then room B, so A's snapshot predates B's turn."""
    room_a = _room_with_a_resolved_turn()
    room_b = _room_with_a_resolved_turn()
    return room_a, room_b


def test_restoring_one_room_rewinds_only_that_room(tmp_path):
    from webapp import backups
    from webapp.rooms import GAMES_ROOT, ROOMS_FILE

    room_a, room_b = _two_rooms_resolved_in_order()
    assert _reloaded(room_a["code"]).last_resolved_turn == 1
    assert _reloaded(room_b["code"]).last_resolved_turn == 1

    backups.restore_backup(
        _backup_of(room_a["code"]), rooms_file=ROOMS_FILE, games_root=GAMES_ROOT
    )

    assert _reloaded(room_a["code"]).last_resolved_turn == 0, (
        "room A should be back at its pre-turn state"
    )
    assert _reloaded(room_b["code"]).last_resolved_turn == 1, (
        "restoring room A rewound room B; a snapshot is only authoritative for "
        "the room it was taken for"
    )


def test_whole_registry_restore_is_available_but_opt_in():
    from webapp import backups
    from webapp.rooms import GAMES_ROOT, ROOMS_FILE

    room_a, room_b = _two_rooms_resolved_in_order()

    backups.restore_backup(
        _backup_of(room_a["code"]),
        rooms_file=ROOMS_FILE,
        games_root=GAMES_ROOT,
        whole_registry=True,
    )

    # A's snapshot was taken before room B existed, so the full swap does not
    # merely rewind B -- it drops it out of the registry altogether. That is the
    # cost of this mode, and the reason it is not the default.
    assert _reloaded(room_a["code"]).last_resolved_turn == 0
    assert _reloaded(room_b["code"]) is None


def test_restore_preserves_the_replaced_registry_for_inspection():
    from webapp import backups
    from webapp.rooms import GAMES_ROOT, ROOMS_FILE

    room_a, _ = _two_rooms_resolved_in_order()
    backups.restore_backup(
        _backup_of(room_a["code"]), rooms_file=ROOMS_FILE, games_root=GAMES_ROOT
    )

    preserved = list(ROOMS_FILE.parent.glob("rooms.pre-restore-*.json"))
    assert preserved, "the replaced registry should be kept beside the restored one"
    assert json.loads(preserved[0].read_text(encoding="utf-8"))["rooms"]


def test_splicing_refuses_an_unreadable_live_registry_and_says_what_to_do():
    from webapp import backups
    from webapp.rooms import GAMES_ROOT, ROOMS_FILE

    room_a = _room_with_a_resolved_turn()
    backup_path = _backup_of(room_a["code"])
    ROOMS_FILE.write_text("not-json", encoding="utf-8")

    with pytest.raises(backups.BackupError) as caught:
        backups.restore_backup(
            backup_path, rooms_file=ROOMS_FILE, games_root=GAMES_ROOT
        )
    assert "whole_registry=True" in str(caught.value)

    # The escape hatch it points at actually works.
    backups.restore_backup(
        backup_path,
        rooms_file=ROOMS_FILE,
        games_root=GAMES_ROOT,
        whole_registry=True,
    )
    assert _reloaded(room_a["code"]).last_resolved_turn == 0


def test_restore_into_an_empty_registry_creates_just_that_room(tmp_path):
    from webapp import backups
    from webapp.rooms import RoomStore

    room_a = _room_with_a_resolved_turn()
    fresh_rooms = tmp_path / "server_data" / "rooms.json"
    fresh_games = tmp_path / "games"

    backups.restore_backup(
        _backup_of(room_a["code"]), rooms_file=fresh_rooms, games_root=fresh_games
    )

    restored = RoomStore(fresh_rooms)
    assert [r.code for r in restored.all()] == [room_a["code"]]
    assert restored.get(room_a["code"]).last_resolved_turn == 0
