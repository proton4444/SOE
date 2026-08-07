"""
End-to-end tests for the web server: humans over HTMX pages, agents over JSON.

These run against a temporary data dir (SOE_DATA_DIR / SOE_GAMES_DIR) so the
repo's real games and rooms are never touched.
"""

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault("SOE_DATA_DIR", str(Path(tempfile.gettempdir()) / f"soe_test_{uuid.uuid4().hex[:8]}"))
os.environ.setdefault("SOE_GAMES_DIR", str(Path(tempfile.gettempdir()) / f"soe_games_{uuid.uuid4().hex[:8]}"))

from fastapi.testclient import TestClient  # noqa: E402

from webapp.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_store():
    from webapp import rooms
    from webapp.rooms import ROOMS_FILE

    rooms.default_store()._rooms.clear()
    if ROOMS_FILE.exists():
        ROOMS_FILE.unlink()
    yield


def _create_room(slots=2):
    resp = client.post("/api/rooms", json={"name": "Test War", "slots": slots})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _join(code, pin, name):
    resp = client.post("/api/join", json={"code": code, "pin": pin, "name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_create_room_initialises_an_engine_game():
    room = _create_room()
    game_dir = Path(os.environ["SOE_GAMES_DIR"]) / f"room_{room['code']}"
    assert game_dir.exists()
    state_file = game_dir / "state.json"
    assert state_file.exists()
    state = state_file.read_text(encoding="utf-8")
    assert '"turn_number": 0' in state
    assert 'player_1' in state and 'player_2' in state
    # Default map is the full world when present.
    assert room["map_file"] == "soe_world.json" or room["map_file"].endswith(".json")
    if (Path(__file__).resolve().parent.parent / "maps" / "soe_world.json").exists():
        assert room["map_file"] == "soe_world.json"
        assert "madegi_doy" in state


def test_available_maps_excludes_geography_sidecar():
    from webapp import service

    maps = service.available_maps()
    assert "sample_map.json" in maps or "soe_world.json" in maps
    assert "soe_geography.json" not in maps
    assert service.default_map() in maps


def test_create_room_rejects_unknown_map():
    resp = client.post("/api/rooms", json={"map": "nope.json"})
    assert resp.status_code == 400


def test_create_room_rejects_geography_sidecar():
    resp = client.post("/api/rooms", json={"map": "soe_geography.json"})
    assert resp.status_code == 400


def test_join_claims_slots_and_returns_key():
    room = _create_room(slots=3)
    p1 = _join(room["code"], room["pin"], "Alice")
    p2 = _join(room["code"], room["pin"], "bob-bot")
    assert p1["faction_id"] == "player_1"
    assert p2["faction_id"] == "player_2"
    assert p1["agent_key"].startswith("soe_")
    assert p1["agent_key"] != p2["agent_key"]

    # Re-joining with the same name returns the same player.
    again = _join(room["code"], room["pin"], "Alice")
    assert again["faction_id"] == p1["faction_id"]
    assert again["agent_key"] == p1["agent_key"]


def test_join_rejects_wrong_pin_and_full_room():
    room = _create_room(slots=2)
    resp = client.post("/api/join", json={"code": room["code"], "pin": "0000", "name": "X"})
    assert resp.status_code == 400
    _join(room["code"], room["pin"], "A")
    _join(room["code"], room["pin"], "B")
    resp = client.post("/api/join", json={"code": room["code"], "pin": room["pin"], "name": "C"})
    assert resp.status_code == 400


def test_orders_parse_feedback_and_are_stored():
    room = _create_room()
    p1 = _join(room["code"], room["pin"], "Alice")
    resp = client.post(
        f"/api/rooms/{room['code']}/orders?key={p1['agent_key']}",
        json={"orders": "Recruit 20 soldiers in Madegi Doy.\nHave Emperor Marcus go to Kitesta."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parsed"] == 2
    assert body["warnings"] == []
    assert body["turn"] == 1

    # Bad orders warn but do not fail.
    resp = client.post(
        f"/api/rooms/{room['code']}/orders?key={p1['agent_key']}",
        json={"orders": "Go to Nowheresville."},
    )
    body = resp.json()
    assert body["parsed"] >= 1
    assert any("nowheresville" in w.lower() for w in body["warnings"])


def test_orders_require_a_valid_key():
    room = _create_room()
    resp = client.post(
        f"/api/rooms/{room['code']}/orders?key=soe_bogus",
        json={"orders": "Recruit 5 soldiers."},
    )
    assert resp.status_code == 403
    resp = client.post(f"/api/rooms/{room['code']}/orders", json={"orders": "x"})
    assert resp.status_code == 401


def test_turn_resolves_when_all_submitted():
    room = _create_room()
    p1 = _join(room["code"], room["pin"], "Alice")
    p2 = _join(room["code"], room["pin"], "Bob")

    client.post(
        f"/api/rooms/{room['code']}/orders?key={p1['agent_key']}",
        json={"orders": "Recruit 20 soldiers in Madegi Doy."},
    )

    # Not ready while someone is missing.
    resp = client.post(f"/api/rooms/{room['code']}/resolve", json={}, headers={"X-Agent-Key": room["host_key"]})
    assert resp.status_code == 409
    assert "Bob" in resp.json()["detail"]

    # Ready after both submit.
    client.post(
        f"/api/rooms/{room['code']}/orders?key={p2['agent_key']}",
        json={"orders": "Recruit 30 soldiers in Albatross City.\nHave Khan Tengri go to Madegi Doy."},
    )
    resp = client.post(f"/api/rooms/{room['code']}/resolve", json={}, headers={"X-Agent-Key": room["host_key"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["turn"] == 1

    # State advanced, reports exist for both players.
    status = client.get(f"/api/rooms/{room['code']}/status", headers={"X-Agent-Key": p1["agent_key"]})
    assert status.json()["turn"] == 1
    assert status.json()["available_reports"] == [1]

    for player in (p1, p2):
        report = client.get(
            f"/api/rooms/{room['code']}/report?key={player['agent_key']}&turn=1"
        )
        assert report.status_code == 200
        assert report.json()["report"].strip()
        assert player["faction_name"] in report.json()["report"]


def test_agent_state_view_is_structured_and_fogged():
    room = _create_room()
    p1 = _join(room["code"], room["pin"], "Alice")
    state = client.get(f"/api/rooms/{room['code']}/state", headers={"X-Agent-Key": p1["agent_key"]}).json()

    assert state["faction_id"] == "player_1"
    assert state["faction_name"] == "The Golden Empire"
    assert state["turn"] == 0
    assert len(state["characters"]) == 1
    leader = state["characters"][0]
    assert leader["is_leader"] is True
    # Start cities are seeded-random: the leader must begin in some city.
    assert leader["location_city_name"] in {c["name"] for c in state["cities"]}
    assert leader["gold"] > 0
    assert {"id", "name", "population_band", "is_port"} <= set(state["cities"][0])
    assert all("controlled_by" in c for c in state["cities"])

    # No enemy characters leak into the view.
    assert all(c["is_prisoner"] is False for c in state["characters"])


def test_host_force_resolve_runs_with_empty_orders():
    room = _create_room()
    p1 = _join(room["code"], room["pin"], "Alice")
    client.post(
        f"/api/rooms/{room['code']}/orders?key={p1['agent_key']}",
        json={"orders": "Recruit 20 soldiers in Madegi Doy."},
    )
    resp = client.post(f"/api/rooms/{room['code']}/resolve", json={"force": True}, headers={"X-Agent-Key": room["host_key"]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["turn"] == 1


def test_resolve_is_deterministic_per_room_and_turn():
    room = _create_room()
    p1 = _join(room["code"], room["pin"], "Alice")
    p2 = _join(room["code"], room["pin"], "Bob")
    for p in (p1, p2):
        client.post(
            f"/api/rooms/{room['code']}/orders?key={p['agent_key']}",
            json={"orders": "Recruit 20 soldiers."},
        )
    first = client.post(f"/api/rooms/{room['code']}/resolve", json={}, headers={"X-Agent-Key": room["host_key"]})
    seed_a = first.json()["seed"]

    room2 = _create_room()
    p1b = _join(room2["code"], room2["pin"], "Alice")
    p2b = _join(room2["code"], room2["pin"], "Bob")
    for p in (p1b, p2b):
        client.post(
            f"/api/rooms/{room2['code']}/orders?key={p['agent_key']}",
            json={"orders": "Recruit 20 soldiers."},
        )
    second = client.post(f"/api/rooms/{room2['code']}/resolve", json={}, headers={"X-Agent-Key": room2["host_key"]})
    seed_b = second.json()["seed"]

    assert seed_a != seed_b  # different rooms, different seeds


def test_start_cities_are_seeded_random_but_reproducible():
    import random
    from pathlib import Path

    from spoils_engine import map_loader
    from webapp import service
    from webapp.mapview import load_raw_map
    from webapp.rooms import default_store

    room = _create_room(slots=3)
    room_obj = default_store().get(room["code"])
    starts = [p.start_city for p in room_obj.players]
    assert len(set(starts)) == len(starts)  # seeded shuffle assigns distinct cities

    # Same pool create_game uses: mutually reachable cities only.
    maps_dir = Path(__file__).resolve().parent.parent / "maps"
    world = map_loader.load_map_from_json(maps_dir / room["map_file"])
    city_ids = map_loader.mutually_reachable_cities(world) or list(world.cities)
    expected = list(city_ids)
    random.Random(service._room_seed(room["code"])).shuffle(expected)
    assert starts == [expected[p.slot] for p in room_obj.players]

    # The same room code always yields the same starts.
    assert service._room_seed(room["code"]) == service._room_seed(room["code"])

    # Start cities are visible in the lobby status, by display name.
    status = client.get(f"/api/rooms/{room['code']}/status",
                        headers={"X-Agent-Key": room["host_key"]}).json()
    names = {c["id"]: c["name"] for c in load_raw_map(room["map_file"])["cities"]}
    assert [p["start_city"] for p in status["players"]] == [
        names[s] for s in starts
    ]


def test_map_is_the_first_impact_of_the_landing_page():
    page = client.get("/")
    assert page.status_code == 200
    # The hero SVG map renders with cities and road/sea links.
    assert '<svg' in page.text
    assert "Madegi Doy" in page.text
    # Default is the full world map when present.
    assert "soe_world.json" in page.text or "sample_map.json" in page.text
    assert "sea lane" in page.text or "≈" in page.text or "Soe World" in page.text
    # The map picker wires the chosen map into the create form.
    assert 'name="map_file"' in page.text
    assert 'value="soe_world.json"' in page.text or 'value="sample_map.json"' in page.text
    # Full world uses traced geography (15 landmasses), not road-hull merge.
    if "soe_world.json" in page.text and "value=\"soe_world.json\"" in page.text:
        assert "15 landmasses" in page.text or "Slamoniya" in page.text
        assert "soe-map-geo" in page.text


def test_map_preview_endpoint_serves_svg():
    resp = client.get("/map/sample_map.json")
    assert resp.status_code == 200
    assert "<svg" in resp.text
    assert "Peshandi" in resp.text
    # Landmass index: sample map has continent + island.
    assert "landmass" in resp.text.lower() or "Landmasses" in resp.text
    assert "Northern Island" in resp.text or "island" in resp.text.lower()

    resp = client.get("/map/nope.json")
    assert resp.status_code == 404


def test_map_positions_use_explicit_coords_and_fall_back_to_layout(tmp_path, monkeypatch):
    from webapp import mapview

    monkeypatch.setattr(mapview, "_map_path", lambda name: tmp_path / name)

    custom = tmp_path / "custom.json"
    custom.write_text(json.dumps({
        "cities": [
            {"id": "a", "name": "A", "population_band": "< 10k", "x": 0.0, "y": 0.0},
            {"id": "b", "name": "B", "population_band": "< 10k", "x": 1.0, "y": 1.0},
        ],
        "roads": [],
    }), encoding="utf-8")

    # Hand-placed coordinates are used when present for every city.
    pos = mapview.positions("custom.json")
    assert pos["a"][0] < pos["b"][0]
    assert pos["a"][1] < pos["b"][1]

    # No coordinates -> deterministic force layout still works.
    no_coords = tmp_path / "auto.json"
    no_coords.write_text(json.dumps({
        "cities": [
            {"id": "a", "name": "A", "population_band": "< 10k"},
            {"id": "b", "name": "B", "population_band": "< 10k"},
            {"id": "c", "name": "C", "population_band": "< 10k"},
        ],
        "roads": [],
    }), encoding="utf-8")
    pos_a = mapview.positions("auto.json")
    pos_b = mapview.positions("auto.json")
    assert pos_a == pos_b  # deterministic
    assert len(pos_a) == 3


def test_human_room_page_and_join_flow():
    room = _create_room()
    page = client.get(f"/room/{room['code']}")
    assert page.status_code == 200

    # The join panel carries the game code and an invite hint.
    panel = client.get(f"/room/{room['code']}/panel")
    assert panel.status_code == 200
    assert "Join this game" in panel.text
    assert room["code"] in panel.text

    # Join through the web form.
    resp = client.post(
        "/join",
        data={"code": room["code"], "pin": room["pin"], "display_name": "Webbie"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert f"/room/{room['code']}" in resp.headers["location"]
    cookie = resp.cookies.get(f"soe_player_{room['code']}")
    assert cookie

    client.cookies.set(f"soe_player_{room['code']}", cookie)
    panel = client.get(f"/room/{room['code']}/panel")
    assert "Your reports" in panel.text

    # Submit via the HTMX endpoint.
    resp = client.post(
        f"/room/{room['code']}/orders",
        data={"orders": "Recruit 10 soldiers."},
    )
    assert resp.status_code == 200
    assert "Stored 1 order(s)" in resp.text


def test_player_state_does_not_leak_rival_garrisons():
    """
    The map itself is public (it is drawn on the landing page), but who is
    holding which city is not: a faction only learns that where it has eyes.
    """
    from spoils_engine import storage
    from webapp import service
    from webapp.rooms import default_store

    room = _create_room(slots=2)
    room_obj = default_store().get(room["code"])
    p1, p2 = room_obj.players[0], room_obj.players[1]

    state = service.load_state(room_obj)
    far_city = next(
        cid for cid in state.world_map.cities
        if cid not in {p1.start_city, p2.start_city}
    )
    # Rival secures its own home and a city nobody is watching.
    state.factions[p2.faction_id].secured_city_ids = {p2.start_city, far_city}
    storage.save_game_state(state, room_obj.game_dir())

    view = service.player_state(room_obj, p1.faction_id)
    by_id = {c["id"]: c for c in view["cities"]}

    # Geography is still fully listed -- it is the published board.
    assert set(by_id) == set(state.world_map.cities)
    assert by_id[far_city]["name"]

    # But the rival's garrisons are invisible from where player 1 stands.
    assert by_id[far_city]["observed"] is False
    assert by_id[far_city]["secured_by"] is None
    assert by_id[p2.start_city]["secured_by"] is None

    # Player 1's own seat is observed, and reports its own hold.
    assert by_id[p1.start_city]["observed"] is True
    assert by_id[p1.start_city]["controlled_by"] == p1.faction_id


def test_player_state_reveals_a_garrison_once_a_scout_stands_there():
    from spoils_engine import storage
    from webapp import service
    from webapp.rooms import default_store

    room = _create_room(slots=2)
    room_obj = default_store().get(room["code"])
    p1, p2 = room_obj.players[0], room_obj.players[1]

    state = service.load_state(room_obj)
    state.factions[p2.faction_id].secured_city_ids = {p2.start_city}
    # Move player 1's leader onto the rival's seat.
    leader = next(
        c for c in state.characters.values() if c.faction_id == p1.faction_id
    )
    leader.location_city_id = p2.start_city
    storage.save_game_state(state, room_obj.game_dir())

    view = service.player_state(room_obj, p1.faction_id)
    seen = next(c for c in view["cities"] if c["id"] == p2.start_city)

    assert seen["observed"] is True
    assert seen["secured_by"] == p2.faction_id


def _join_as_player(room, display_name="Cartographer"):
    """Join over the web form and keep the session cookie on the client."""
    resp = client.post(
        "/join",
        data={"code": room["code"], "pin": room["pin"], "display_name": display_name},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    cookie = resp.cookies.get(f"soe_player_{room['code']}")
    assert cookie
    client.cookies.set(f"soe_player_{room['code']}", cookie)
    return cookie


def test_room_map_is_the_live_board_not_the_published_map():
    room = _create_room(slots=2)
    _join_as_player(room)

    page = client.get(f"/room/{room['code']}")
    assert page.status_code == 200

    # The overlay key rides on the map, naming the turn and the holders.
    assert "WHO HOLDS WHAT" in page.text
    assert "TURN 0" in page.text

    # The player's own seat is flagged, and their leader is counted there.
    assert "(you)" in page.text
    assert "1&#8224;" in page.text or "1†" in page.text


def test_landing_page_map_carries_no_game_state():
    """The published map is the same for everyone: no holders, no forces."""
    page = client.get("/")
    assert page.status_code == 200
    assert "WHO HOLDS WHAT" not in page.text
    assert "(you)" not in page.text


def test_map_overlay_hides_what_a_seat_cannot_see():
    from spoils_engine import storage
    from webapp import service
    from webapp.rooms import default_store

    room = _create_room(slots=2)
    room_obj = default_store().get(room["code"])
    p1, p2 = room_obj.players[0], room_obj.players[1]

    state = service.load_state(room_obj)
    far_city = next(
        cid for cid in state.world_map.cities
        if cid not in {p1.start_city, p2.start_city}
    )
    state.factions[p2.faction_id].controlled_city_ids.add(far_city)
    storage.save_game_state(state, room_obj.game_dir())

    overlay = service.map_overlay(room_obj, p1.faction_id)

    # Player 1 sees their own holding...
    assert overlay["cities"][p1.start_city]["holder_id"] == p1.faction_id
    assert overlay["cities"][p1.start_city]["characters"] == 1
    # ...and nothing about the rival's, at home or abroad.
    assert "holder_id" not in overlay["cities"][p2.start_city]
    assert "holder_id" not in overlay["cities"][far_city]
    assert overlay["cities"][far_city]["observed"] is False

    # The key counts only the pennants actually drawn.
    key = {f["id"]: f["cities"] for f in overlay["factions"]}
    assert key[p1.faction_id] == 1
    assert p2.faction_id not in key

    # Seat colours are stable and distinct between players.
    o2 = service.map_overlay(room_obj, p2.faction_id)
    c1 = overlay["cities"][p1.start_city]["holder_color"]
    c2 = o2["cities"][p2.start_city]["holder_color"]
    assert c1 != c2


def test_map_overlay_is_none_without_a_seat():
    from webapp import service
    from webapp.rooms import default_store

    room = _create_room(slots=2)
    room_obj = default_store().get(room["code"])
    assert service.map_overlay(room_obj, None) is None
    assert service.map_overlay(room_obj, "no_such_faction") is None
