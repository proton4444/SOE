"""
Fault injection across the turn publication boundary.

``resolve_turn`` writes the advanced state, then derives snapshots, events,
report files, and finally the room registry.  Every write between the state
save and ``Room.store_reports`` is a window where ``state.json`` says turn N
while ``rooms.json`` still says turn N-1.  These tests fail the resolution at
each of those points and assert the game is still recoverable afterwards.

They run against a temporary data dir (SOE_DATA_DIR / SOE_GAMES_DIR) so the
repo's real games and rooms are never touched.
"""

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


class InjectedFailure(RuntimeError):
    """A fault raised on purpose at one persistence boundary."""


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


def _room_ready_to_resolve():
    """Create a room with one joined player holding submitted orders."""
    from webapp import rooms

    created = client.post("/api/rooms", json={"name": "Test War", "slots": 2}).json()
    player = client.post(
        "/api/join",
        json={"code": created["code"], "pin": created["pin"], "name": "Alice"},
    ).json()
    client.post(
        f"/api/rooms/{created['code']}/orders?key={player['agent_key']}",
        json={"orders": "Recruit 20 soldiers."},
    )
    return created["code"], rooms.default_store().get(created["code"])


def _reload_from_disk(code):
    """Read state and room metadata the way a restarted server would."""
    from soe import storage
    from webapp.rooms import GAMES_ROOT, ROOMS_FILE, RoomStore

    state = storage.load_game_state(GAMES_ROOT / f"room_{code}")
    room = RoomStore(ROOMS_FILE).get(code)
    return state, room


# The persistence boundaries after the advanced state is written to disk.
FAULT_POINTS = ["snapshot", "generate_reports", "report_files", "store_reports"]


def _inject(monkeypatch, where):
    from webapp import service as svc
    from webapp.rooms import Room

    def boom(*args, **kwargs):
        raise InjectedFailure(f"injected failure at {where}")

    if where == "snapshot":
        monkeypatch.setattr(svc, "_snapshot_state", boom)
    elif where == "generate_reports":
        monkeypatch.setattr(svc.reporting, "generate_player_reports", boom)
    elif where == "report_files":
        monkeypatch.setattr(svc, "_write_report_files", boom)
    elif where == "store_reports":
        monkeypatch.setattr(Room, "store_reports", boom)
    else:  # pragma: no cover - guards the parametrisation itself
        raise AssertionError(f"unknown fault point {where}")


@pytest.mark.parametrize("where", FAULT_POINTS)
def test_failure_after_state_save_leaves_state_and_room_agreeing(monkeypatch, where):
    """A failed turn must not leave the state ahead of the room registry."""
    from webapp import service

    code, room = _room_ready_to_resolve()
    _inject(monkeypatch, where)

    with pytest.raises(InjectedFailure):
        service.resolve_turn(room, force=True)

    state, reloaded = _reload_from_disk(code)
    assert state is not None and reloaded is not None
    assert state.turn_number == reloaded.last_resolved_turn, (
        f"split state after failure at {where}: "
        f"state.json is at turn {state.turn_number} but the room registry "
        f"is at turn {reloaded.last_resolved_turn}"
    )


@pytest.mark.parametrize("where", FAULT_POINTS)
def test_failed_turn_keeps_orders_available_for_a_retry(monkeypatch, where):
    """Submitted orders survive a failed resolution so the turn can be retried."""
    from webapp import service

    code, room = _room_ready_to_resolve()
    _inject(monkeypatch, where)

    with pytest.raises(InjectedFailure):
        service.resolve_turn(room, force=True)

    _, reloaded = _reload_from_disk(code)
    assert reloaded.submissions.get(1), (
        f"orders for turn 1 were dropped by the failure at {where}; "
        "the turn can no longer be retried from the submitted intent"
    )


def test_retry_after_a_failed_turn_does_not_apply_the_turn_twice(monkeypatch):
    """The classic split-state consequence: turn N resolved onto turn N."""
    from webapp import service

    code, room = _room_ready_to_resolve()
    _inject(monkeypatch, "report_files")
    with pytest.raises(InjectedFailure):
        service.resolve_turn(room, force=True)

    monkeypatch.undo()
    result = service.resolve_turn(room, force=True)

    state, reloaded = _reload_from_disk(code)
    assert result["turn"] == 1
    assert state.turn_number == 1, (
        f"the retry advanced the game to turn {state.turn_number}; "
        "turn 1 was applied on top of an already-advanced state"
    )
    assert reloaded.last_resolved_turn == 1


def test_failed_turn_records_a_host_visible_recovery_event(monkeypatch):
    """An operator can see that the turn was rolled back, not silently lost."""
    from webapp import service

    code, room = _room_ready_to_resolve()
    _inject(monkeypatch, "report_files")
    with pytest.raises(InjectedFailure):
        service.resolve_turn(room, force=True)

    events = (
        Path(os.environ["SOE_GAMES_DIR"]) / f"room_{code}" / "resolution_events.jsonl"
    ).read_text(encoding="utf-8")
    assert '"status":"failed"' in events
    assert '"status":"rolled_back"' in events
