"""
The ``?key=`` credential fallback: deprecated, warn-once, and hard-refusable.

Agents still authenticate through the query string, so the default keeps
working; ``SOE_REJECT_QUERY_KEYS`` (here patched directly) is the migration
end-state where only headers are accepted.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_qkey_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_qkey_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_store():
    from webapp import rooms

    rooms.default_store()._rooms.clear()
    yield


@pytest.fixture(autouse=True)
def _reset_warn_flag():
    from webapp import main as web_main

    web_main._query_credential_warned = False
    yield
    web_main._query_credential_warned = False


def _room():
    resp = client.post("/api/rooms", json={"name": "Q", "slots": 2})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_query_key_still_works_by_default():
    from webapp import main as web_main

    assert not web_main.REJECT_QUERY_KEYS
    room = _room()
    resp = client.get(
        f"/api/rooms/{room['code']}/status", params={"key": room["host_key"]}
    )
    assert resp.status_code == 200, resp.text


def test_header_key_is_unaffected_by_rejection(monkeypatch):
    from webapp import main as web_main

    monkeypatch.setattr(web_main, "REJECT_QUERY_KEYS", True)
    room = _room()
    resp = client.get(
        f"/api/rooms/{room['code']}/status",
        headers={"X-Agent-Key": room["host_key"]},
    )
    assert resp.status_code == 200, resp.text


def test_reject_mode_refuses_the_query_credential(monkeypatch):
    from webapp import main as web_main

    monkeypatch.setattr(web_main, "REJECT_QUERY_KEYS", True)
    room = _room()
    url = f"/api/rooms/{room['code']}/status"
    assert client.get(url, params={"key": room["host_key"]}).status_code == 401
    # A wrong header key is still just unauthorized -- same status, honest.
    assert (
        client.get(url, headers={"X-Agent-Key": "nope"}).status_code == 403
    )


def test_coach_key_in_query_is_deprecated_too(monkeypatch):
    from webapp import main as web_main

    monkeypatch.setattr(web_main, "REJECT_QUERY_KEYS", True)
    resp = client.post("/api/coaches", json={"name": "Ada"})
    assert resp.status_code == 200, resp.text
    coach_key = resp.json()["coach_key"]
    blueprint = {
        "name": "N",
        "doctrine": {
            "objective": "Hold.",
            "economy": "Save.",
            "risk": "Low.",
            "diplomacy": "Neutral.",
        },
    }
    url = "/api/blueprints"
    by_query = client.post(url, params={"key": coach_key}, json=blueprint)
    assert by_query.status_code == 401
    by_header = client.post(
        url, headers={"X-Coach-Key": coach_key}, json=blueprint
    )
    assert by_header.status_code == 200, by_header.text
