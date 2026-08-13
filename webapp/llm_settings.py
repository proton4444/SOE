"""
Persisted LLM settings for the war-room dashboard (server-wide).

The webapp reads model configuration from ``server_data/llm_settings.json``
so an operator can configure the bot brain from the dashboard instead of the
environment. Precedence is deliberately **env wins, settings file fills the
gap**: official arena runs keep pinning their configuration through
``SOE_LLM_*`` variables, while a bare ``uvicorn`` boots with the dashboard's
settings.

The API key is stored plaintext on the server (same trust boundary as
``rooms.json`` host keys) but is never returned by the API: only a masked
fingerprint and a set/unset flag leave the module.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
#: The settings file can live elsewhere (the headless arena isolates its
#: SOE_DATA_DIR into a temp workdir but must still honour the dashboard's
#: LLM setup, so it points this at the live server_data copy).
SETTINGS_FILE = Path(
    os.environ.get("SOE_LLM_SETTINGS_FILE", str(SERVER_DATA / "llm_settings.json"))
)

DEFAULTS: dict = {
    "base_url": "",
    "key": "",
    "model": "",
    "temperature": 0.0,
    "timeout_seconds": 120,
    "max_retries": 2,
    "max_tokens": 1500,
}

#: Hosts the brain may be pointed at. The API key travels in an
#: ``Authorization: Bearer`` header to whatever base URL is configured, so an
#: arbitrary URL is a key-exfiltration channel, not merely a routing choice.
DEFAULT_BASE_HOSTS: tuple[str, ...] = (
    "openrouter.ai",
    "api.openai.com",
    "api.anthropic.com",
    "api.deepseek.com",
    "api.groq.com",
    "api.mistral.ai",
    "generativelanguage.googleapis.com",
)

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_lock = threading.RLock()


def settings_path() -> Path:
    return SETTINGS_FILE


def allowed_base_hosts() -> tuple[str, ...]:
    """The fixed allowlist plus hosts the operator pinned in the environment."""
    extra = tuple(
        host.strip().lower()
        for host in os.environ.get("SOE_LLM_BASE_ALLOWLIST", "").split(",")
        if host.strip()
    )
    return DEFAULT_BASE_HOSTS + extra


def base_url_error(url: str) -> str:
    """Why ``url`` may not receive the API key; empty string when it may.

    A local proxy (ollama, llama.cpp) is reachable over plain http, but only
    on loopback: everything else must be https on the allowlist.
    """
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not host or parts.scheme not in ("http", "https"):
        return "Base URL must be an absolute http(s) URL."
    if parts.username or parts.password:
        return "Base URL must not carry credentials."
    loopback = host in _LOOPBACK_HOSTS
    if parts.scheme != "https" and not loopback:
        return "Base URL must use https (plain http only for loopback)."
    if not loopback and host not in allowed_base_hosts():
        return (
            f"Base URL host '{host}' is not on the allowlist "
            "(extend it with SOE_LLM_BASE_ALLOWLIST)."
        )
    return ""


def load_settings() -> dict:
    """The persisted settings; missing fields fall back to DEFAULTS."""
    if not SETTINGS_FILE.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save_settings(patch: dict) -> dict:
    """Merge ``patch`` into the persisted settings. Empty strings keep the
    existing value (use ``key=None`` or the clear flag to remove a key)."""
    with _lock:
        current = load_settings()
        for field, value in patch.items():
            if value is None or field == "updated_at":
                continue
            current[field] = value
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_FILE.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(current, indent=2), encoding="utf-8", newline="\n"
        )
        tmp.replace(SETTINGS_FILE)
        return current


def clear_key() -> dict:
    return save_settings({"key": ""})


def redact(key: str) -> str:
    """``sk-or-...1234``; empty when unset. Never reveals the full key."""
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "·" * len(key)
    return key[:6] + "…" + key[-4:]


def public_settings() -> dict:
    """A safe view for the dashboard: the key is masked, never returned."""
    settings = load_settings()
    return {
        "base_url": settings.get("base_url", ""),
        "model": settings.get("model", ""),
        "temperature": settings.get("temperature", 0.0),
        "timeout_seconds": settings.get("timeout_seconds", 120),
        "max_retries": settings.get("max_retries", 2),
        "max_tokens": settings.get("max_tokens", 1500),
        "key_set": bool((settings.get("key", "") or "").strip()),
        "key_masked": redact(settings.get("key", "")),
        "file": str(SETTINGS_FILE),
        "updated_at": settings.get("updated_at", ""),
    }


def effective(field: str, env_name: str, default):
    """Settings file value, unless the environment overrides it."""
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value
    settings = load_settings()
    value = settings.get(field)
    if value not in (None, ""):
        if field == "base_url" and base_url_error(str(value)):
            # A persisted base URL that is not on the allowlist is treated as
            # unset. The file is writable by anything that can write
            # server_data; the key must never be sent where it points.
            return default
        return value
    return default
