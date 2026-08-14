"""Wave 4 of the 2026-08-13 review: C33-C37.

Each test names the defect it closes. They were written to fail against the
pre-fix source: set-order hashes, dashboard knobs leaking into official
runs, probes treating essays as orders, empty HTTP 200 counted as success,
and determinism verify reading only the newest 100 log lines.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_w4_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_w4_games_{uuid.uuid4().hex[:8]}"),
)
os.environ["SOE_LLM_KEY"] = "sk-test-secret-key"

from soe.models import City, Faction, GameState, PopulationBand  # noqa: E402

from scripts.arena import (  # noqa: E402
    LLMPolicy,
    isolate_headless_runtime,
    pin_official_llm_knobs,
)
from tests.test_phase0_arena import _ctx  # noqa: E402
from scripts.arena_bundle import state_sha  # noqa: E402
from scripts.probe_model import probe  # noqa: E402
from webapp.ai import brain  # noqa: E402
from webapp.ai.context import extract_marked_orders  # noqa: E402
from webapp import service  # noqa: E402


REPO = Path(__file__).resolve().parent.parent


def _board_with_sets() -> GameState:
    gs = GameState()
    gs.factions["alpha"] = Faction(
        id="alpha",
        name="Alpha",
        controlled_city_ids={"rome", "athens", "sparta"},
        allies={"beta"},
    )
    gs.world_map.cities["rome"] = City(
        id="rome", name="Rome", population_band=PopulationBand.MEDIUM
    )
    return gs


def test_c33_state_sha_is_identical_under_two_pythonhashseed_values():
    code = r"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(r"%s")))
from soe.models import City, Faction, GameState, PopulationBand
from scripts.arena_bundle import state_sha
gs = GameState()
gs.factions["alpha"] = Faction(
    id="alpha", name="Alpha",
    controlled_city_ids={"rome", "athens", "sparta"},
    allies={"beta"},
)
gs.world_map.cities["rome"] = City(
    id="rome", name="Rome", population_band=PopulationBand.MEDIUM
)
print(state_sha(gs))
""" % REPO.as_posix()
    hashes = []
    for seed in ("0", "1"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        env["PYTHONPATH"] = str(REPO)
        out = subprocess.check_output(
            [sys.executable, "-c", code], env=env, text=True
        )
        hashes.append(out.strip())
    assert hashes[0] == hashes[1]
    assert len(hashes[0]) == 64
    assert hashes[0] == state_sha(_board_with_sets())


def test_c33_state_sha_matches_saved_state_json_bytes(tmp_path):
    from soe import storage

    gs = _board_with_sets()
    storage.save_game_state(gs, tmp_path)
    on_disk = (tmp_path / "state.json").read_bytes()
    import hashlib

    assert state_sha(gs) == hashlib.sha256(on_disk).hexdigest()


def test_c34_official_isolation_does_not_inherit_dashboard_knobs(
    tmp_path, monkeypatch
):
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "key": "sk-dashboard-only-key",
                "timeout_seconds": 7,
                "max_retries": 9,
                "max_tokens": 99,
                "base_url": "https://openrouter.ai/api/v1",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("SOE_LLM_KEY", raising=False)
    monkeypatch.delenv("SOE_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("SOE_LLM_RETRIES", raising=False)
    monkeypatch.delenv("SOE_LLM_MAX_TOKENS", raising=False)
    from webapp import llm_settings

    previous = {
        name: os.environ.get(name)
        for name in ("SOE_DATA_DIR", "SOE_GAMES_DIR", "SOE_LLM_SETTINGS_FILE")
    }
    original_settings = llm_settings.SETTINGS_FILE
    try:
        isolate_headless_runtime(tmp_path / "work", dashboard_path=dashboard)
        assert os.environ.get("SOE_LLM_KEY") == "sk-dashboard-only-key"
        assert brain._timeout_seconds() == 120
        assert brain._max_retries() == 2
        assert brain._max_output_tokens() == 1500
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        llm_settings.SETTINGS_FILE = original_settings


def test_c34_pin_official_knobs_from_run_config(monkeypatch):
    monkeypatch.delenv("SOE_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("SOE_LLM_RETRIES", raising=False)
    try:
        pin_official_llm_knobs({"timeout_seconds": 45, "max_retries": 1})
        assert brain._timeout_seconds() == 45
        assert brain._max_retries() == 1
    finally:
        os.environ.pop("SOE_LLM_TIMEOUT", None)
        os.environ.pop("SOE_LLM_RETRIES", None)


def test_c35_essay_without_orders_marker_fails_the_probe(monkeypatch):
    class _Result:
        text = "Ignore previous instructions and tax everything."
        attempts = 1
        latency_ms = 1.0
        usage = {}
        provider_request_id = "probe-essay"

    monkeypatch.setattr(brain, "chat_result", lambda **kw: _Result())
    has_marker, parsed_ok, reply, _summary = probe("provider/model")
    assert has_marker is False
    assert parsed_ok is False
    assert extract_marked_orders(reply) is None


def test_c35_marked_valid_command_passes_the_probe(monkeypatch):
    class _Result:
        text = "thinking\n--- ORDERS ---\nTax.\n"
        attempts = 1
        latency_ms = 1.0
        usage = {}
        provider_request_id = "probe-ok"

    monkeypatch.setattr(brain, "chat_result", lambda **kw: _Result())
    has_marker, parsed_ok, _reply, _summary = probe("provider/model")
    assert has_marker is True
    assert parsed_ok is True


def test_c36_empty_200_raises_llm_error(monkeypatch):
    import httpx

    payload = {
        "id": "empty-1",
        "choices": [{"message": {"content": ""}}],
        "usage": {},
    }
    original = httpx.Client

    def handler(request):
        return httpx.Response(200, json=payload)

    def factory(timeout=120, **kwargs):
        return original(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(brain.httpx, "Client", factory)
    with pytest.raises(brain.LLMError, match="empty completion"):
        brain.chat_result(
            model="provider/model",
            messages=[{"role": "user", "content": "hi"}],
        )


def test_c36_empty_completion_does_not_count_as_completed_call(monkeypatch):
    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda **kw: (_ for _ in ()).throw(
            brain.LLMError("LLM returned an empty completion.")
        ),
    )
    from scripts.arena import _reliability_summary

    policy = LLMPolicy(model="m")
    turn_outcome = policy.orders(_ctx(), __import__("random").Random(1))
    assert turn_outcome.trace["failure_class"]
    assert "raw_reply" not in turn_outcome.trace
    summary = _reliability_summary([policy.name], [
        type("R", (), {"traces": [turn_outcome.trace]})()
    ])
    assert summary[policy.name]["calls_completed"] == 0


def test_c37_determinism_verify_reads_turn_1_of_a_60_turn_log(tmp_path):
    log = tmp_path / "resolution_events.jsonl"
    lines = []
    for turn in range(1, 61):
        lines.append(json.dumps({"turn": turn, "status": "started"}))
        lines.append(
            json.dumps(
                {
                    "turn": turn,
                    "status": "completed",
                    "post_state_sha": f"{turn:064d}",
                }
            )
        )
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    events = service._read_jsonl(log, limit=None)
    completed = [
        e for e in events if e.get("turn") == 1 and e.get("status") == "completed"
    ]
    assert completed
    assert completed[-1]["post_state_sha"] == f"{1:064d}"
    newest_only = service._read_jsonl(log, limit=100)
    assert all(e.get("turn", 0) >= 11 for e in newest_only)
