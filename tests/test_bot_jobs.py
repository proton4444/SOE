"""
Background bot-turn jobs: submit off the request path, poll for the result.

The LLM is faked by monkeypatching ``webapp.ai.brain`` -- no network in tests,
and each turn finishes fast enough to poll to completion.
"""

import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_botjobs_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_botjobs_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp.main import app  # noqa: E402

client = TestClient(app)

FAKE_ORDERS = "--- ORDERS ---\nReport.\nWait for 1 day.\n"


@pytest.fixture(autouse=True)
def _clean_store():
    from webapp import rooms
    from webapp.ai import bot_jobs, registry as ai_registry
    from webapp.rooms import ROOMS_FILE

    rooms.default_store()._rooms.clear()
    ai_registry.default_registry()._profiles.clear()
    bot_jobs.default_runner().reset()
    if ROOMS_FILE.exists():
        ROOMS_FILE.unlink()
    if ai_registry.AGENTS_FILE.exists():
        AGENTS_FILE = ai_registry.AGENTS_FILE  # noqa: F841 - readability below
        AGENTS_FILE.unlink(missing_ok=True)
    yield
    bot_jobs.default_runner().reset()


@pytest.fixture(autouse=True)
def captured(monkeypatch):
    from webapp.ai import brain

    monkeypatch.setattr(brain, "is_configured", lambda: True)
    captured = {"all": []}

    def fake_chat(**kwargs):
        captured["all"].append(kwargs)
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


def _wait_job(job_id, room, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(
            f"/api/bot-jobs/{job_id}", params={"key": room["host_key"]}
        ).json()
        if body.get("status") in ("complete", "error"):
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_background_run_returns_a_job_that_completes(captured):
    from webapp.rooms import default_store

    room = _create_room()
    _enable_bot(room)
    url = (
        f"/api/rooms/{room['code']}/agents/player_1/run"
        f"?key={room['host_key']}&background=1"
    )
    resp = client.post(url)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["status_url"].startswith("/api/bot-jobs/")

    job = _wait_job(body["job_id"], room)
    assert job["status"] == "complete", job.get("error")
    assert job["result"]["parsed"] >= 2
    assert job["result"]["state"] == "submitted"

    room_obj = default_store().get(room["code"])
    bucket = room_obj.submissions[room_obj.next_turn()]
    assert bucket["player_1"]["parsed"] >= 2


def test_job_status_requires_a_valid_room_key():
    room = _create_room()
    _enable_bot(room)
    url = (
        f"/api/rooms/{room['code']}/agents/player_1/run"
        f"?key={room['host_key']}&background=1"
    )
    job_id = client.post(url).json()["job_id"]
    poll_url = f"/api/bot-jobs/{job_id}"
    assert client.get(poll_url).status_code == 401
    assert (
        client.get(poll_url, headers={"X-Agent-Key": "nope"}).status_code == 403
    )
    assert (
        client.get(
            poll_url, params={"key": room["host_key"]}
        ).status_code
        == 200
    )


def test_unknown_job_is_a_404():
    resp = client.get("/api/bot-jobs/" + "0" * 16, params={"key": "anything"})
    assert resp.status_code == 404


def test_run_all_background_enqueues_one_job_per_enabled_bot():
    room = _create_room(slots=3)
    _enable_bot(room, "player_1")
    _enable_bot(room, "player_3")
    url = (
        f"/api/rooms/{room['code']}/agents/run-all"
        f"?key={room['host_key']}&background=1"
    )
    resp = client.post(url)
    assert resp.status_code == 202, resp.text
    jobs = resp.json()["jobs"]
    assert {j["faction_id"] for j in jobs} == {"player_1", "player_3"}

    outcomes = {}
    for entry in jobs:
        body = _wait_job(entry["job_id"], room)
        outcomes[body["faction_id"]] = body["status"]
    assert outcomes == {"player_1": "complete", "player_3": "complete"}


def test_queue_full_is_reported_as_503(monkeypatch):
    import queue as queue_mod

    from webapp.ai import bot_jobs

    room = _create_room()
    _enable_bot(room)
    runner = bot_jobs.default_runner()
    full = queue_mod.Queue(maxsize=1)
    full.put("occupied")
    monkeypatch.setattr(runner, "_pending", full)
    url = (
        f"/api/rooms/{room['code']}/agents/player_1/run"
        f"?key={room['host_key']}&background=1"
    )
    resp = client.post(url)
    assert resp.status_code == 503
    assert "queued" in resp.json()["detail"]


def test_a_bot_failure_lands_in_the_job_not_the_response(monkeypatch):
    from webapp.ai import brain, orchestrator

    room = _create_room()
    _enable_bot(room)

    def failing(*args, **kwargs):
        raise brain.LLMError("LLM request failed after 1 attempts: boom")

    monkeypatch.setattr(orchestrator, "_ask_strategist", failing)
    url = (
        f"/api/rooms/{room['code']}/agents/player_1/run"
        f"?key={room['host_key']}&background=1"
    )
    body = client.post(url).json()
    job = _wait_job(body["job_id"], room)
    assert job["status"] == "error"
    assert "boom" in job["error"]
