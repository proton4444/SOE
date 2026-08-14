"""
Dashboard LLM setup: persisted settings, env precedence, masked key, and the
setup-page endpoints (save / clear / probe). The probe path is faked -- no
network.

These settings hold the API key every bot on the process uses and decide which
host that key is sent to, so the write paths are operator-only and the base URL
is allowlisted (C1).
"""

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_llmset_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_llmset_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp import main as web_main  # noqa: E402
from webapp.main import app  # noqa: E402
from webapp import llm_settings  # noqa: E402

client = TestClient(app)

KEY = "sk-or-v1-abcdefghijklmnopqrstuvwxyz1234"
OPERATOR = "operator-secret-for-tests"
ALLOWED_BASE = "https://openrouter.ai/api/v1"


@pytest.fixture(autouse=True)
def _clean_store():
    import shutil

    from webapp import rooms
    from webapp.ai import registry as ai_registry
    from webapp.rooms import ROOMS_FILE

    rooms.default_store()._rooms.clear()
    ai_registry.default_registry()._profiles.clear()
    if ROOMS_FILE.exists():
        ROOMS_FILE.unlink()
    if ai_registry.AGENTS_FILE.exists():
        ai_registry.AGENTS_FILE.unlink()
    client.cookies.clear()
    yield


@pytest.fixture(autouse=True)
def _operator_secret(monkeypatch):
    """A configured operator secret: TestClient is not loopback, so every
    write path must present the key explicitly."""
    monkeypatch.setattr(web_main, "OPERATOR_KEY", OPERATOR)
    return OPERATOR


def _op(**kwargs) -> dict:
    """Request kwargs carrying the operator credential."""
    headers = dict(kwargs.pop("headers", {}) or {})
    headers[web_main.OPERATOR_HEADER] = OPERATOR
    kwargs["headers"] = headers
    return kwargs


@pytest.fixture
def settings_file(monkeypatch, tmp_path):
    path = tmp_path / "llm_settings.json"
    monkeypatch.setattr(llm_settings, "SETTINGS_FILE", path)
    return path


@pytest.fixture
def _no_env_key(monkeypatch):
    monkeypatch.delenv("SOE_LLM_KEY", raising=False)
    monkeypatch.delenv("SOE_LLM_BASE", raising=False)
    monkeypatch.delenv("SOE_LLM_MODEL", raising=False)


# ===========================================================================
# settings module
# ===========================================================================


def test_settings_roundtrip(settings_file):
    llm_settings.save_settings({"key": KEY, "model": "poolside/laguna-s-2.1:free"})
    loaded = llm_settings.load_settings()
    assert loaded["key"] == KEY
    assert loaded["model"] == "poolside/laguna-s-2.1:free"
    assert loaded["updated_at"]


def test_public_view_masks_key(settings_file):
    llm_settings.save_settings({"key": KEY, "model": "m"})
    public = llm_settings.public_settings()
    assert public["key_set"] is True
    assert KEY not in json.dumps(public)
    assert public["key_masked"].endswith("1234")
    assert public["key_masked"].startswith("sk-or-")
    assert "file" not in public


def test_clear_key(settings_file):
    llm_settings.save_settings({"key": KEY})
    llm_settings.clear_key()
    assert llm_settings.load_settings()["key"] == ""
    assert llm_settings.public_settings()["key_set"] is False


def test_env_wins_over_settings(settings_file, monkeypatch):
    llm_settings.save_settings({"key": KEY, "base_url": ALLOWED_BASE})
    monkeypatch.setenv("SOE_LLM_KEY", "sk-env-key")
    assert llm_settings.effective("key", "SOE_LLM_KEY", "") == "sk-env-key"
    assert llm_settings.effective("base_url", "SOE_LLM_BASE", "") == ALLOWED_BASE
    monkeypatch.delenv("SOE_LLM_KEY", raising=False)
    assert llm_settings.effective("key", "SOE_LLM_KEY", "") == KEY


def test_brain_uses_settings_file(settings_file, _no_env_key):
    from webapp.ai import brain

    llm_settings.save_settings({"key": KEY, "model": "poolside/laguna-s-2.1:free"})
    assert brain.is_configured() is True
    assert brain.model_name("") == "poolside/laguna-s-2.1:free"
    assert brain.model_name("openai/gpt-4o-mini") == "openai/gpt-4o-mini"
    llm_settings.clear_key()
    assert brain.is_configured() is False


# ===========================================================================
# endpoints
# ===========================================================================


def _create_room():
    resp = client.post("/api/rooms", json={"name": "Setup LLM", "slots": 2})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _as_host(room):
    client.cookies.set(f"soe_host_{room['code']}", room["host_key"])


def test_setup_page_shows_masked_key(settings_file, _no_env_key):
    room = _create_room()
    _as_host(room)
    llm_settings.save_settings({"key": KEY})
    page = client.get(f"/room/{room['code']}/setup")
    assert page.status_code == 200
    assert "not set" not in page.text
    assert "1234" in page.text
    assert KEY not in page.text


def test_setup_page_requires_host(settings_file):
    room = _create_room()
    assert client.get(f"/room/{room['code']}/setup").status_code == 403
    assert client.post(f"/room/{room['code']}/setup/llm").status_code == 403


def test_save_settings_from_dashboard(settings_file, _no_env_key):
    room = _create_room()
    _as_host(room)
    resp = client.post(
        f"/room/{room['code']}/setup/llm",
        data={
            "base_url": ALLOWED_BASE,
            "key": KEY,
            "model": "poolside/laguna-s-2.1:free",
            "temperature": "0",
            "timeout_seconds": "90",
            "max_retries": "1",
            "max_tokens": "1200",
        },
        follow_redirects=False,
        **_op(),
    )
    assert resp.status_code == 303
    saved = llm_settings.load_settings()
    assert saved["key"] == KEY
    assert saved["model"] == "poolside/laguna-s-2.1:free"
    assert saved["timeout_seconds"] == 90
    assert saved["max_retries"] == 1
    assert saved["max_tokens"] == 1200


def test_blank_key_field_keeps_existing(settings_file, _no_env_key):
    room = _create_room()
    _as_host(room)
    llm_settings.save_settings({"key": KEY})
    client.post(
        f"/room/{room['code']}/setup/llm", data={"model": "other-model"}, **_op()
    )
    assert llm_settings.load_settings()["key"] == KEY
    assert llm_settings.load_settings()["model"] == "other-model"


def test_clear_key_from_dashboard(settings_file, _no_env_key):
    room = _create_room()
    _as_host(room)
    llm_settings.save_settings({"key": KEY})
    client.post(
        f"/room/{room['code']}/setup/llm", data={"clear_key": "on"}, **_op()
    )
    assert llm_settings.load_settings()["key"] == ""


def _unquote(url: str) -> str:
    from urllib.parse import unquote

    return unquote(url)


def test_probe_action_reports_success(settings_file, _no_env_key, monkeypatch):
    from webapp.ai import brain

    room = _create_room()
    _as_host(room)
    llm_settings.save_settings({"key": KEY})

    def fake_chat_result(*, model, messages, temperature=0.0, max_tokens=None, images=()):
        return brain.ChatResult(
            text="--- ORDERS ---\nTax.\nRecruit 5 soldiers in Highfell.",
            model=model,
            attempts=1,
            latency_ms=123.4,
            usage={"prompt_tokens": 200, "completion_tokens": 30,
                   "total_tokens": 230, "cost": 0.0001},
            provider_request_id="gen-probe-1",
        )

    monkeypatch.setattr(brain, "chat_result", fake_chat_result)
    resp = client.post(
        f"/room/{room['code']}/setup/llm",
        data={"action": "probe", "model": "poolside/laguna-s-2.1:free"},
        follow_redirects=False,
        **_op(),
    )
    assert resp.status_code == 303
    location = _unquote(resp.headers["location"])
    assert "Probe OK" in location
    assert "orders=yes" in location
    assert "123" in location


def test_probe_action_without_key_reports_failure(settings_file, _no_env_key):
    room = _create_room()
    _as_host(room)
    resp = client.post(
        f"/room/{room['code']}/setup/llm",
        data={"action": "probe"},
        follow_redirects=False,
        **_op(),
    )
    assert resp.status_code == 303
    assert "Probe failed" in _unquote(resp.headers["location"])


def test_settings_file_override_env(monkeypatch, tmp_path):
    """SOE_LLM_SETTINGS_FILE lets isolated processes (the arena) honour the
    dashboard's LLM setup without touching its data dir."""
    live_file = tmp_path / "live.json"
    isolated = tmp_path / "isolated.json"
    live_file.write_text(
        json.dumps({"key": KEY, "model": "poolside/laguna-s-2.1:free"}),
        encoding="utf-8",
    )
    monkeypatch.delenv("SOE_LLM_KEY", raising=False)
    monkeypatch.setattr(llm_settings, "SETTINGS_FILE", live_file)
    monkeypatch.setattr(
        llm_settings,
        "SERVER_DATA",
        tmp_path / "isolated_server_data",
    )
    from webapp.ai import brain

    assert brain.is_configured() is True
    assert brain.model_name("") == "poolside/laguna-s-2.1:free"


# ===========================================================================
# standalone /llm-settings page (reachable from home)
# ===========================================================================


def test_home_page_links_to_llm_settings(settings_file):
    page = client.get("/")
    assert page.status_code == 200
    assert "/llm-settings" in page.text
    assert "Model setup" in page.text


def test_llm_settings_page_requires_operator_to_save(settings_file):
    page = client.get("/llm-settings")
    assert page.status_code == 200
    assert "operator-only" in page.text
    assert client.post("/llm-settings", data={"model": "m"}).status_code == 403


def test_llm_settings_page_saves_for_operator(settings_file, _no_env_key):
    page = client.get("/llm-settings", **_op())
    assert page.status_code == 200
    assert "operator-only" not in page.text
    resp = client.post(
        "/llm-settings",
        data={"model": "poolside/laguna-s-2.1:free", "key": KEY},
        follow_redirects=False,
        **_op(),
    )
    assert resp.status_code == 303
    assert "LLM settings saved" in _unquote(resp.headers["location"])
    assert llm_settings.load_settings()["key"] == KEY
    assert llm_settings.load_settings()["model"] == "poolside/laguna-s-2.1:free"


def test_llm_settings_page_probe(settings_file, _no_env_key, monkeypatch):
    from webapp.ai import brain

    llm_settings.save_settings({"key": KEY})

    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda *a, **kw: brain.ChatResult(
            text="--- ORDERS ---\nTax.", model="m", attempts=1,
            latency_ms=5.0, usage={},
        ),
    )
    resp = client.post(
        "/llm-settings", data={"action": "probe"}, follow_redirects=False, **_op()
    )
    assert resp.status_code == 303
    assert "Probe OK" in _unquote(resp.headers["location"])


# ===========================================================================
# C1: operator-only writes, allowlisted base URL
# ===========================================================================


def test_host_session_cannot_change_llm_settings(settings_file, _no_env_key):
    """Creating a room is free, so a host cookie must not reach the key."""
    llm_settings.save_settings({"key": KEY, "base_url": ALLOWED_BASE})
    room = _create_room()
    _as_host(room)

    evil = "https://attacker.example/v1"
    assert (
        client.post(
            f"/room/{room['code']}/setup/llm",
            data={"base_url": evil, "action": "probe"},
        ).status_code
        == 403
    )
    assert client.post("/llm-settings", data={"base_url": evil}).status_code == 403
    assert llm_settings.load_settings()["base_url"] == ALLOWED_BASE
    assert llm_settings.load_settings()["key"] == KEY


def test_operator_cannot_point_the_key_at_a_foreign_host(settings_file, _no_env_key):
    llm_settings.save_settings({"key": KEY, "base_url": ALLOWED_BASE})
    resp = client.post(
        "/llm-settings",
        data={"base_url": "https://attacker.example/v1", "model": "m"},
        follow_redirects=False,
        **_op(),
    )
    assert resp.status_code == 303
    assert "Base URL rejected" in _unquote(resp.headers["location"])
    saved = llm_settings.load_settings()
    assert saved["base_url"] == ALLOWED_BASE
    # The whole submission is refused, not half-applied.
    assert saved.get("model", "") != "m"


def test_plain_http_is_refused_off_loopback(settings_file):
    assert llm_settings.base_url_error("http://openrouter.ai/api/v1")
    assert llm_settings.base_url_error("https://user:pw@openrouter.ai/api/v1")
    assert llm_settings.base_url_error("file:///etc/passwd")
    assert llm_settings.base_url_error("http://127.0.0.1:11434/v1") == ""
    assert llm_settings.base_url_error(ALLOWED_BASE) == ""


def test_allowlist_extends_from_env(settings_file, monkeypatch):
    assert llm_settings.base_url_error("https://llm.internal.example/v1")
    monkeypatch.setenv("SOE_LLM_BASE_ALLOWLIST", "llm.internal.example")
    assert llm_settings.base_url_error("https://llm.internal.example/v1") == ""


def test_persisted_off_allowlist_base_url_is_ignored(settings_file, _no_env_key):
    """The file is only as trustworthy as whatever can write server_data."""
    settings_file.write_text(
        json.dumps({"key": KEY, "base_url": "https://attacker.example/v1"}),
        encoding="utf-8",
    )
    assert llm_settings.effective("base_url", "SOE_LLM_BASE", "") == ""

    from webapp.ai import brain

    assert brain._api_base() == "https://openrouter.ai/api/v1"


def test_probe_refuses_a_just_changed_base_url(settings_file, _no_env_key, monkeypatch):
    """Changing where the key goes and sending it are two deliberate acts."""
    from webapp.ai import brain

    llm_settings.save_settings({"key": KEY, "base_url": ALLOWED_BASE})
    calls: list[str] = []
    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda *a, **kw: calls.append("sent")
        or brain.ChatResult(
            text="--- ORDERS ---\nTax.", model="m", attempts=1, latency_ms=1.0,
            usage={},
        ),
    )

    resp = client.post(
        "/llm-settings",
        data={"base_url": "http://127.0.0.1:11434/v1", "action": "probe"},
        follow_redirects=False,
        **_op(),
    )
    assert resp.status_code == 303
    assert "Probe again" in _unquote(resp.headers["location"])
    assert calls == []
    assert llm_settings.load_settings()["base_url"] == "http://127.0.0.1:11434/v1"

    # Second, deliberate probe against the now-saved URL does go out.
    resp = client.post(
        "/llm-settings", data={"action": "probe"}, follow_redirects=False, **_op()
    )
    assert "Probe OK" in _unquote(resp.headers["location"])
    assert calls == ["sent"]
