"""
War-room bot tests: managed AI players decide and submit turns.

The LLM is faked by monkeypatching ``webapp.ai.brain`` — no network in tests.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_bots_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_bots_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp.main import app  # noqa: E402

client = TestClient(app)

FAKE_ORDERS = "--- ORDERS ---\nReport.\nWait for 1 day.\n"

# Captured before the autouse fake-chat fixture replaces it.
from webapp.ai import brain as _brain_module  # noqa: E402

ORIGINAL_CHAT = _brain_module.chat


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


@pytest.fixture(autouse=True)
def captured(monkeypatch):
    from webapp.ai import brain

    monkeypatch.setattr(brain, "is_configured", lambda: True)
    captured = {"all": []}

    def fake_chat(**kwargs):
        captured["all"].append(kwargs)
        captured["last"] = kwargs
        return FAKE_ORDERS

    monkeypatch.setattr(brain, "chat", fake_chat)
    return captured


def _create_room(slots=2):
    resp = client.post("/api/rooms", json={"name": "Bot War", "slots": slots})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _enable_bot(room, faction_id="player_1"):
    resp = client.put(
        f"/api/rooms/{room['code']}/agents/{faction_id}",
        headers={"X-Agent-Key": room["host_key"]},
        json={"enabled": True, "persona": "Test persona"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _join(code, pin, name):
    resp = client.post("/api/join", json={"code": code, "pin": pin, "name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_run_requires_host_key():
    room = _create_room()
    _enable_bot(room)
    guest = client.post(
        "/api/join",
        json={"code": room["code"], "pin": room["pin"], "name": "Alice"},
    ).json()
    url = f"/api/rooms/{room['code']}/agents/player_1/run"
    assert client.post(url).status_code == 401
    assert client.post(url, headers={"X-Agent-Key": "nope"}).status_code == 403
    assert (
        client.post(url, headers={"X-Agent-Key": guest["agent_key"]}).status_code == 403
    )


def test_run_bot_submits_orders_and_marks_state(captured):
    from webapp.ai import default_registry
    from webapp.rooms import default_store

    room = _create_room()
    _enable_bot(room)
    url = f"/api/rooms/{room['code']}/agents/player_1/run"
    resp = client.post(url, headers={"X-Agent-Key": room["host_key"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parsed"] >= 2
    assert body["state"] == "submitted"

    room_obj = default_store().get(room["code"])
    bucket = room_obj.submissions[room_obj.next_turn()]
    assert bucket["player_1"]["parsed"] >= 2

    profile = default_registry().get(room["code"], "player_1")
    assert profile.state == "submitted"
    assert profile.last_run_at
    assert profile.last_error == ""

    # The model got the persona, the state, and the marker instruction.
    last = captured["last"]
    joined = " ".join(str(m.get("content", "")) for m in last["messages"])
    assert "Test persona" in joined
    assert "STRUCTURED STATE" in joined
    assert "--- ORDERS ---" in joined
    assert last["temperature"] == 0.0


def test_run_bot_refuses_when_llm_not_configured(monkeypatch):
    from webapp.ai import brain

    monkeypatch.setattr(brain, "is_configured", lambda: False)
    room = _create_room()
    _enable_bot(room)
    resp = client.post(
        f"/api/rooms/{room['code']}/agents/player_1/run",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 503
    assert "SOE_LLM_KEY" in resp.json()["detail"]


def test_run_bot_refuses_when_not_enabled():
    room = _create_room()
    resp = client.post(
        f"/api/rooms/{room['code']}/agents/player_1/run",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 400
    assert "enabled" in resp.json()["detail"]


def test_run_bot_failure_marks_error_and_keeps_state(monkeypatch):
    from webapp.ai import default_registry
    from webapp.ai import brain

    def boom(**kwargs):
        raise brain.LLMError("model on fire")

    monkeypatch.setattr(brain, "chat", boom)
    room = _create_room()
    _enable_bot(room)
    resp = client.post(
        f"/api/rooms/{room['code']}/agents/player_1/run",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 503
    profile = default_registry().get(room["code"], "player_1")
    assert profile.state == "error"
    assert "model on fire" in profile.last_error


def test_run_all_runs_only_enabled_bots():
    from webapp.ai import default_registry

    room = _create_room(slots=3)
    _enable_bot(room, "player_1")
    _enable_bot(room, "player_3")
    resp = client.post(
        f"/api/rooms/{room['code']}/agents/run-all",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    factions = {r["faction_id"] for r in results}
    assert factions == {"player_1", "player_3"}
    assert all(r.get("state") == "submitted" for r in results)
    assert default_registry().get(room["code"], "player_1").state == "submitted"


def test_run_all_with_no_bots():
    room = _create_room()
    resp = client.post(
        f"/api/rooms/{room['code']}/agents/run-all",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 400


def test_setup_form_run_action_submits_orders():
    from webapp.rooms import default_store

    room = _create_room()
    client.cookies.set(f"soe_host_{room['code']}", room["host_key"])
    try:
        resp = client.post(
            f"/room/{room['code']}/setup/agents/player_1",
            data={
                "model": "openai/gpt-4o-mini",
                "persona": "Test persona",
                "temperature": "0",
                "enabled": "on",
                "action": "run",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        room_obj = default_store().get(room["code"])
        bucket = room_obj.submissions[room_obj.next_turn()]
        assert bucket["player_1"]["parsed"] >= 2

        page = client.get(f"/room/{room['code']}/setup").text
        assert "submitted" in page
    finally:
        client.cookies.delete(f"soe_host_{room['code']}")


def test_extract_orders_marker_handling():
    from webapp.ai.orchestrator import ORDERS_MARKER, extract_orders

    reply = "Consider taxes.\n" + ORDERS_MARKER + "\nReport.\nWait for 1 day."
    assert extract_orders(reply) == "Report.\nWait for 1 day."
    assert extract_orders("Report.") == "Report."
    assert extract_orders("") == ""


def test_extract_orders_handles_trailing_empty_marker():
    # Some models end with a second, empty marker after the orders.
    from webapp.ai.orchestrator import ORDERS_MARKER, extract_orders

    reply = (
        "Reasoning here.\n---\n" + ORDERS_MARKER + "\nReport.\nTax.\n" + ORDERS_MARKER
    )
    assert extract_orders(reply) == "Report.\nTax."
    assert "Reasoning" not in extract_orders(reply)


def test_bot_turn_runs_intel_and_field_subagents(captured):
    from webapp.ai import default_registry

    room = _create_room()
    _enable_bot(room)
    resp = client.post(
        f"/api/rooms/{room['code']}/agents/player_1/run",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subagents"]["intel"] is True
    assert body["subagents"]["field_characters"] >= 1

    calls = captured["all"]
    assert len(calls) >= 3
    intel_system = calls[0]["messages"][0]["content"]
    field_system = calls[1]["messages"][0]["content"]
    strategist_user = calls[-1]["messages"][1]["content"]
    assert "intel analyst" in intel_system
    assert "field commander" in field_system
    assert "INTEL BRIEFING" in strategist_user
    assert "FIELD DRAFTS" in strategist_user
    # Subagents are cheaper/looser than the strategist.
    assert calls[0]["max_tokens"] == 600
    assert calls[-1].get("max_tokens", 1500) > 600
    assert default_registry().get(room["code"], "player_1").state == "submitted"


def test_subagent_failure_degrades_not_wedges(monkeypatch):
    from webapp.ai import brain

    def intel_boom(**kwargs):
        if "intel analyst" in kwargs["messages"][0]["content"]:
            raise brain.LLMError("intel down")
        return FAKE_ORDERS

    monkeypatch.setattr(brain, "chat", intel_boom)
    room = _create_room()
    _enable_bot(room)
    resp = client.post(
        f"/api/rooms/{room['code']}/agents/player_1/run",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["subagents"]["intel"] is False


def test_filter_clean_orders_drops_unparseable_lines():
    from webapp.ai.orchestrator import _filter_clean_orders
    from webapp.rooms import default_store

    room = _create_room()
    room_obj = default_store().get(room["code"])
    player = room_obj.players[0]
    text = (
        "Monitor the movements of the Shadow Syndicate.\n"
        "Tax.\n"
        "Have Emperor Marcus go to Redport.\n"
        "Prepare for potential negotiations.\n"
    )
    filtered = _filter_clean_orders(room_obj, player, text)
    assert "Monitor" not in filtered
    assert "Prepare" not in filtered
    assert "Tax." in filtered
    assert "go to Redport" in filtered


def test_filter_clean_orders_keeps_raw_when_nothing_parses():
    from webapp.ai.orchestrator import _filter_clean_orders
    from webapp.rooms import default_store

    room = _create_room()
    room_obj = default_store().get(room["code"])
    player = room_obj.players[0]
    text = "Sing a song about the sea.\nDance at dawn.\n"
    assert _filter_clean_orders(room_obj, player, text) == text


def test_filter_clean_orders_keeps_clean_text_untouched():
    from webapp.ai.orchestrator import _filter_clean_orders
    from webapp.rooms import default_store

    room = _create_room()
    room_obj = default_store().get(room["code"])
    player = room_obj.players[0]
    text = "Report.\nWait for 1 day.\n"
    assert _filter_clean_orders(room_obj, player, text) == text


def test_filter_clean_orders_strips_markdown_separators():
    from webapp.ai.orchestrator import _filter_clean_orders
    from webapp.rooms import default_store

    room = _create_room()
    room_obj = default_store().get(room["code"])
    player = room_obj.players[0]
    text = "---\nHave Emperor Marcus study defense tactics.\nTax.\n***\n"
    filtered = _filter_clean_orders(room_obj, player, text)
    assert "---" not in filtered
    assert "***" not in filtered
    assert "study" not in filtered
    assert "Tax." in filtered


# ============================================================================
# auto-play controller (M4)
# ============================================================================


def test_autoplay_runs_bots_and_resolves_turns(captured):
    from webapp.ai.autoplay import AutoplayController
    from webapp.rooms import default_store

    room = _create_room()
    _enable_bot(room)
    _enable_bot(room, "player_2")
    controller = AutoplayController()
    controller.start(room["code"], turns=2, delay=0.1)
    try:
        status = _wait_status(controller, "running", False, timeout=30)
        assert status["turns_done"] == 2
        assert status["last_turn"] == 2
        assert status["last_error"] == ""
        room_obj = default_store().get(room["code"])
        assert room_obj.last_resolved_turn == 2
        assert 1 in room_obj.reports and 2 in room_obj.reports
    finally:
        controller.stop(room["code"])


def test_autoplay_refuses_double_start_and_no_bots(captured):
    from webapp.ai.autoplay import AutoplayController, AutoplayError
    import pytest

    room = _create_room()
    _enable_bot(room)
    controller = AutoplayController()
    controller.start(room["code"], turns=5, delay=0.1)
    try:
        with pytest.raises(AutoplayError, match="already running"):
            controller.start(room["code"], turns=1, delay=0.1)
    finally:
        controller.stop(room["code"])
    _wait_status(controller, "running", False, timeout=20)

    other = _create_room()
    with pytest.raises(AutoplayError, match="No enabled bots"):
        controller.start(other["code"], turns=1, delay=0.1)


def test_autoplay_stop_interrupts(captured):
    from webapp.ai.autoplay import AutoplayController

    room = _create_room()
    _enable_bot(room)
    _enable_bot(room, "player_2")
    controller = AutoplayController()
    controller.start(room["code"], turns=50, delay=0.05)
    try:
        assert controller.status()["running"] is True
        controller.stop(room["code"])
        status = _wait_status(controller, "running", False, timeout=20)
        assert status["turns_done"] < 50
    finally:
        controller.stop(room["code"])


def test_autoplay_endpoint_requires_host_and_starts(captured):
    room = _create_room()
    _enable_bot(room)
    url = f"/room/{room['code']}/master/autoplay"
    assert client.post(url).status_code == 403

    client.cookies.set(f"soe_host_{room['code']}", room["host_key"])
    try:
        resp = client.post(
            url,
            data={"action": "start", "turns": "1", "delay": "0.1"},
        )
        assert resp.status_code == 200
        assert "running" in resp.text
        resp = client.post(url, data={"action": "stop"})
        assert resp.status_code == 200
    finally:
        client.cookies.delete(f"soe_host_{room['code']}")


def _wait_status(controller, key, want, timeout=30):
    import time

    status = controller.status()
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = controller.status()
        if status.get(key) == want:
            return status
        time.sleep(0.2)
    raise AssertionError(f"status {key} never became {want}: {status}")


# ============================================================================
# hardening (M6)
# ============================================================================


def test_brain_retries_on_429_then_succeeds(monkeypatch):
    from webapp.ai import brain

    monkeypatch.setattr(brain, "chat", ORIGINAL_CHAT)
    calls = {"n": 0}

    def fake_post(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise brain._RetryableError(429, "rate limited", 0.01)
        return "ok", {}, "req-1"

    monkeypatch.setattr(brain, "MAX_RETRIES", 1)
    monkeypatch.setattr(brain, "_post_once", fake_post)
    out = brain.chat(model="x", messages=[{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert calls["n"] == 2


def test_brain_surfaces_provider_message_on_400(monkeypatch):
    from webapp.ai import brain
    import pytest

    monkeypatch.setattr(brain, "chat", ORIGINAL_CHAT)

    def refuse(*a, **kw):
        raise brain.LLMError("LLM refused the request (HTTP 400): Insufficient credits")

    monkeypatch.setattr(brain, "_post_once", refuse)
    with pytest.raises(brain.LLMError, match="Insufficient credits"):
        brain.chat(model="x", messages=[{"role": "user", "content": "hi"}])


def test_autoplay_suspends_bot_after_consecutive_failures(monkeypatch):
    from webapp.ai import autoplay
    from webapp.ai import brain

    def always_fail(**kwargs):
        raise brain.LLMError("provider down")

    monkeypatch.setattr(brain, "chat", always_fail)
    room = _create_room()
    _enable_bot(room)
    controller = autoplay.AutoplayController()
    controller.start(room["code"], turns=6, delay=0.05)
    try:
        status = _wait_status(controller, "running", False, timeout=30)
    finally:
        controller.stop(room["code"])
    suspended = [line for line in status["log"] if "suspended" in line]
    assert suspended, "bot should have been suspended after repeated failures"
    assert status["turns_done"] >= 1


def test_resolution_records_state_sha():
    from webapp import service
    from webapp.rooms import default_store

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
    room_obj = default_store().get(room["code"])
    events = service._read_jsonl(
        room_obj.game_dir() / "resolution_events.jsonl", limit=10
    )
    completed = [e for e in events if e.get("status") == "completed"]
    assert completed and completed[-1].get("post_state_sha")
    assert len(completed[-1]["post_state_sha"]) == 64


def test_healthz_reports_ai_config():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert "ai" in body
    assert "configured" in body["ai"]
    assert "model" in body["ai"]
