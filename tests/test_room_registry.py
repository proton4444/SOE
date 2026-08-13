"""
Room registry integrity: concurrent writes (C4) and join-PIN brute force (C5).

Sync FastAPI routes run in a threadpool, so join, submit and resolve interleave
even with ``--workers 1``. These tests drive ``RoomStore`` directly -- the race
is in the registry, not in any one route.
"""

import json
import os
import tempfile
import threading
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_registry_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_registry_games_{uuid.uuid4().hex[:8]}"),
)

from webapp import rooms  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_store():
    rooms.default_store()._rooms.clear()
    rooms.default_store()._pin_failures.clear()
    if rooms.ROOMS_FILE.exists():
        rooms.ROOMS_FILE.unlink()
    yield


def _persisted() -> dict:
    """The registry as it exists on disk, not in memory."""
    return json.loads(rooms.ROOMS_FILE.read_text(encoding="utf-8"))


def _persisted_room(code: str) -> dict:
    for raw in _persisted()["rooms"]:
        if raw["code"] == code:
            return raw
    raise AssertionError(f"room {code} is not in rooms.json")


# ===========================================================================
# C4: every mutation that saves must be serialised with its save
# ===========================================================================


def test_concurrent_submit_and_join_cannot_drop_a_write(monkeypatch):
    """A save must not publish a payload it built before another thread's
    mutation.

    The window is between building the payload and replacing the file. This
    test pins a submit inside that window and lets a join complete through it:
    unserialised, the submitter then republishes a registry with no seat.
    """
    store = rooms.default_store()
    room = store.create("Race", slots=4, map_file="world.json")

    payload_built = threading.Event()
    join_done = threading.Event()
    real_dumps = json.dumps
    armed = {"pending": True}

    def hooked_dumps(*args, **kwargs):
        # One shot, submitter only: the joiner's own save must run to the end.
        if armed["pending"] and threading.current_thread().name == "submitter":
            armed["pending"] = False
            payload_built.set()
            join_done.wait(timeout=2.0)
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(rooms.json, "dumps", hooked_dumps)
    errors: list[BaseException] = []

    def submit():
        try:
            room.store_submission("player_1", {"orders": "Tax."})
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    def join():
        try:
            payload_built.wait(timeout=2.0)
            store.join(room.code, room.pin, "Alice")
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)
        finally:
            join_done.set()

    submitter = threading.Thread(target=submit, name="submitter")
    joiner = threading.Thread(target=join, name="joiner")
    submitter.start()
    joiner.start()
    submitter.join(timeout=30)
    joiner.join(timeout=30)

    assert errors == [], errors

    saved = _persisted_room(room.code)
    assert "player_1" in saved["submissions"]["1"], "the submission was dropped"
    seated = [p["display_name"] for p in saved["players"] if p["kind"] != "empty"]
    assert seated == ["Alice"], "the seat was dropped"


def test_save_does_not_share_one_temp_file(monkeypatch):
    """Two writers sharing ``rooms.json.tmp`` let the loser publish a payload
    the winner already superseded."""
    store = rooms.default_store()
    store.create("Temp names", slots=2, map_file="world.json")

    seen: list[str] = []
    real_write_text = Path.write_text

    def recording_write_text(self, *args, **kwargs):
        seen.append(self.name)
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", recording_write_text)
    store.save()
    store.save()

    assert len(seen) == 2
    assert seen[0] != seen[1]
    assert not list(rooms.ROOMS_FILE.parent.glob("rooms.json*.tmp"))


# ===========================================================================
# C5: a 4-digit PIN must not be brute-forceable
# ===========================================================================


def test_join_locks_the_room_after_repeated_wrong_pins():
    store = rooms.default_store()
    room = store.create("Guessers", slots=4, map_file="world.json")
    wrong = "0000" if room.pin != "0000" else "1111"

    for attempt in range(rooms.MAX_PIN_ATTEMPTS):
        with pytest.raises(rooms.RoomError) as exc:
            store.join(room.code, wrong, f"Guesser {attempt}")
        assert "Wrong PIN" in str(exc.value)

    # The next guess is refused outright -- and so is the correct PIN.
    with pytest.raises(rooms.RoomError) as exc:
        store.join(room.code, wrong, "Guesser last")
    assert "Too many wrong PINs" in str(exc.value)

    with pytest.raises(rooms.RoomError) as exc:
        store.join(room.code, room.pin, "Latecomer")
    assert "Too many wrong PINs" in str(exc.value)

    assert store.pin_lock_remaining(room.code) > 0
    assert store.pin_lock_remaining(room.code) <= rooms.PIN_LOCKOUT_SECONDS


def test_a_valid_pin_still_joins_before_the_lock():
    store = rooms.default_store()
    room = store.create("Fat fingers", slots=4, map_file="world.json")
    wrong = "0000" if room.pin != "0000" else "1111"

    for attempt in range(rooms.MAX_PIN_ATTEMPTS - 1):
        with pytest.raises(rooms.RoomError):
            store.join(room.code, wrong, f"Typo {attempt}")

    _, player = store.join(room.code, room.pin, "Alice")
    assert player.display_name == "Alice"
    assert store.pin_lock_remaining(room.code) == 0

    # A success clears the streak, so the next typo does not lock immediately.
    with pytest.raises(rooms.RoomError) as exc:
        store.join(room.code, wrong, "Bob")
    assert "Wrong PIN" in str(exc.value)


def test_the_lockout_is_per_room():
    store = rooms.default_store()
    locked = store.create("Locked", slots=2, map_file="world.json")
    other = store.create("Other", slots=2, map_file="world.json")
    wrong = "0000" if locked.pin != "0000" else "1111"

    for attempt in range(rooms.MAX_PIN_ATTEMPTS):
        with pytest.raises(rooms.RoomError):
            store.join(locked.code, wrong, f"Guesser {attempt}")

    assert store.pin_lock_remaining(other.code) == 0
    _, player = store.join(other.code, other.pin, "Alice")
    assert player.display_name == "Alice"
