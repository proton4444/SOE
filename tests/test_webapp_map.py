"""
AI map endpoint tests (M5): fog-of-war json/svg, png, and turn snapshots.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_map_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_map_games_{uuid.uuid4().hex[:8]}"),
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


def _create_room(slots=2):
    resp = client.post("/api/rooms", json={"name": "Map War", "slots": slots})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _join(code, pin, name):
    resp = client.post("/api/join", json={"code": code, "pin": pin, "name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_map_preview_is_confined_to_the_maps_directory():
    """C2: the preview route is unauthenticated, so ``{name}`` must not be
    able to name a file outside ``maps/``."""
    from webapp import mapview, service

    for escape in (
        "..%5Cserver_data%5Cllm_settings.json",
        "..%2Fserver_data%2Fllm_settings.json",
        "..%5C..%5Cserver_data%5Cllm_settings.json",
        "%2E%2E%5Cpyproject.toml",
    ):
        resp = client.get(f"/map/{escape}")
        assert resp.status_code == 404, f"{escape} -> {resp.status_code}"

    # Real map files that are not playable maps are not previewable either.
    assert client.get("/map/soe_geography.json").status_code == 404

    with pytest.raises(FileNotFoundError):
        mapview.load_raw_map("../pyproject.toml")
    with pytest.raises(FileNotFoundError):
        mapview.load_raw_map("..\\pyproject.toml")

    playable = service.default_map()
    ok = client.get(f"/map/{playable}")
    assert ok.status_code == 200
    assert "<svg" in ok.text


def test_map_requires_valid_key():
    room = _create_room()
    url = f"/api/rooms/{room['code']}/map"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-Agent-Key": "nope"}).status_code == 403


def test_map_json_is_fogged_and_coordinate_bearing():
    from webapp.rooms import default_store

    room = _create_room()
    me = _join(room["code"], room["pin"], "Alice")
    url = f"/api/rooms/{room['code']}/map"
    board = client.get(url, headers={"X-Agent-Key": me["agent_key"]}).json()

    assert board["faction_id"] == "player_1"
    assert board["turn"] == 0
    assert board["cities"]
    city = board["cities"][0]
    assert {"id", "name", "x", "y", "observed", "population_band"} <= set(city)
    assert city["x"] is not None and city["y"] is not None

    # The seat's own city is observed; a distant one is not.
    room_obj = default_store().get(room["code"])
    start = room_obj.players[0].start_city
    own = next(c for c in board["cities"] if c["id"] == start)
    assert own["observed"] is True
    assert own["holder"] == "player_1"
    far = next(c for c in board["cities"] if c["id"] != start)
    assert far["observed"] is False
    assert "holder" not in far


def test_map_json_rejects_foreign_faction_for_player():
    room = _create_room()
    me = _join(room["code"], room["pin"], "Alice")
    resp = client.get(
        f"/api/rooms/{room['code']}/map",
        params={"faction": "player_2"},
        headers={"X-Agent-Key": me["agent_key"]},
    )
    assert resp.status_code == 403


def test_map_svg_renders_for_seat():
    room = _create_room()
    me = _join(room["code"], room["pin"], "Alice")
    resp = client.get(
        f"/api/rooms/{room['code']}/map",
        params={"format": "svg"},
        headers={"X-Agent-Key": me["agent_key"]},
    )
    assert resp.status_code == 200
    assert "<svg" in resp.text


def test_map_png_uses_backend(monkeypatch):
    from webapp import mapimg

    room = _create_room()
    me = _join(room["code"], room["pin"], "Alice")
    monkeypatch.setattr(mapimg, "svg_to_png", lambda svg: b"FAKEPNGDATA")
    resp = client.get(
        f"/api/rooms/{room['code']}/map",
        params={"format": "png"},
        headers={"X-Agent-Key": me["agent_key"]},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == b"FAKEPNGDATA"


def test_map_png_reports_501_when_backend_missing(monkeypatch):
    from webapp import mapimg

    room = _create_room()
    me = _join(room["code"], room["pin"], "Alice")

    def broken(svg):
        raise mapimg.PngBackendUnavailable("no cairo, no playwright")

    monkeypatch.setattr(mapimg, "svg_to_png", broken)
    resp = client.get(
        f"/api/rooms/{room['code']}/map",
        params={"format": "png"},
        headers={"X-Agent-Key": me["agent_key"]},
    )
    assert resp.status_code == 501
    assert "no cairo, no playwright" in resp.json()["detail"]


def test_map_bad_format_rejected():
    room = _create_room()
    me = _join(room["code"], room["pin"], "Alice")
    resp = client.get(
        f"/api/rooms/{room['code']}/map",
        params={"format": "gif"},
        headers={"X-Agent-Key": me["agent_key"]},
    )
    assert resp.status_code == 400


def test_map_turn_snapshots_rewind_and_404():
    room = _create_room()
    me = _join(room["code"], room["pin"], "Alice")
    them = _join(room["code"], room["pin"], "Bob")
    client.post(
        f"/api/rooms/{room['code']}/orders",
        headers={"X-Agent-Key": me["agent_key"]},
        json={"orders": "Report."},
    )
    client.post(
        f"/api/rooms/{room['code']}/orders",
        headers={"X-Agent-Key": them["agent_key"]},
        json={"orders": "Report."},
    )
    client.post(
        f"/api/rooms/{room['code']}/resolve",
        headers={"X-Agent-Key": room["host_key"]},
    )

    url = f"/api/rooms/{room['code']}/map"
    h = {"X-Agent-Key": me["agent_key"]}
    assert client.get(url, headers=h).json()["turn"] == 1
    assert client.get(url, params={"turn": 1}, headers=h).json()["turn"] == 1
    assert client.get(url, params={"turn": 0}, headers=h).json()["turn"] == 0
    assert client.get(url, params={"turn": 99}, headers=h).status_code == 404
    assert client.get(url, params={"turn": -1}, headers=h).status_code == 404


def test_host_sees_all_visible_map():
    room = _create_room()
    _join(room["code"], room["pin"], "Alice")
    board = client.get(
        f"/api/rooms/{room['code']}/map",
        headers={"X-Agent-Key": room["host_key"]},
    ).json()
    assert board["all_visible"] is True
    assert all(c["observed"] for c in board["cities"])
    assert "characters" in board
