"""
Phase 0 WP3+WP4: LLM arena policy and resumable run bundle.

The LLM seat must run through the same context/prompt/filter as the
production bot, degrade provider failures into recorded no-ops, respect fog
of war and per-turn reports, and write everything into a resumable bundle
whose replay reproduces the interrupted run byte for byte. All model calls
are faked -- no network.
"""

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p0_arena_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p0_games_{uuid.uuid4().hex[:8]}"),
)
os.environ["SOE_LLM_KEY"] = "sk-test-secret-key"

from webapp.ai import brain  # noqa: E402
from webapp.ai import context  # noqa: E402

from scripts.arena import (  # noqa: E402
    LLMPolicy,
    RandomPolicy,
    _blueprint_behavior_gap,
    _decision_context,
    _emitted_line_metrics,
    _failure_class,
    _load_blueprint,
    _one_sided_sweep_p,
    _order_line_metrics,
    _phase0_run_gate,
    build_policies_from_config,
    load_config,
    play_game,
    prepare_bundle,
    resume_bundle,
    run_batch,
    validate_official_preflight,
)
from scripts.arena_bundle import BundleError, RunBundle  # noqa: E402

FAKE_USAGE = {
    "prompt_tokens": 300,
    "completion_tokens": 40,
    "total_tokens": 340,
    "cost": 0.0001,
}
FAKE_REPLY = (
    "I will tax and recruit.\n"
    "--- ORDERS ---\n"
    "Tax.\n"
    "Have Emperor Marcus tax.\n"
    "Wait for 1 day.\n"
)

MAP = "starter_map.json"


@pytest.fixture(autouse=True)
def _clean_store():
    from webapp import rooms
    from webapp.ai import registry as ai_registry
    from webapp.rooms import GAMES_ROOT, ROOMS_FILE

    rooms.default_store()._rooms.clear()
    ai_registry.default_registry()._profiles.clear()
    if ROOMS_FILE.exists():
        ROOMS_FILE.unlink()
    if ai_registry.AGENTS_FILE.exists():
        ai_registry.AGENTS_FILE.unlink()
    if GAMES_ROOT.exists():
        shutil.rmtree(GAMES_ROOT)
    yield


@pytest.fixture
def fake_brain(monkeypatch):
    """Deterministic fake model: fixed reply, fixed usage, call counter."""
    calls = {"n": 0, "messages": []}

    def fake_chat_result(*, model, messages, temperature=0.0, max_tokens=1500, images=()):
        calls["n"] += 1
        calls["messages"].append(messages)
        return brain.ChatResult(
            text=FAKE_REPLY,
            model=model,
            attempts=1,
            latency_ms=42.0,
            usage=dict(FAKE_USAGE),
            provider_request_id="gen-fake-1",
        )

    monkeypatch.setattr(brain, "is_configured", lambda: True)
    monkeypatch.setattr(brain, "chat_result", fake_chat_result)
    monkeypatch.setattr(
        brain,
        "chat",
        lambda **kwargs: fake_chat_result(**kwargs).text,
    )
    return calls


def _smoke_config(**overrides) -> dict:
    config = {
        "mode": "smoke",
        "map": MAP,
        "turns": 3,
        "seed_pairs": 2,
        "temperature": 0.0,
        "max_tokens": 1500,
        "max_spend_usd": 2.0,
        "entrants": [
            {"type": "llm", "model": "openai/gpt-4o-mini", "blueprint": "expansionist-v1"},
            {"type": "random"},
        ],
    }
    config.update(overrides)
    return config


def _policy_pair(fake_brain=None):
    policies = build_policies_from_config(_smoke_config())
    return policies


def _ctx(seed=0, turn=1):
    from webapp import service, rooms as rooms_mod
    from webapp.rooms import Room, RoomPlayer

    code = f"CTX{seed:02d}"
    store = rooms_mod.default_store()
    old = store._rooms.pop(code, None)
    if old is not None:
        shutil.rmtree(old.game_dir(), ignore_errors=True)
    room = Room(
        code=code,
        pin="0000",
        name=f"arena {code}",
        map_file=MAP,
        host_key=f"host-{code}",
        created_at="2026-08-11T00:00:00+00:00",
        slots=2,
        players=[
            RoomPlayer(slot=0, faction_id="player_1", faction_name="The Golden Empire",
                       display_name="a", kind="agent", agent_key="k1"),
            RoomPlayer(slot=1, faction_id="player_2", faction_name="The Silver Horde",
                       display_name="b", kind="agent", agent_key="k2"),
        ],
    )
    store._rooms[code] = room
    store.save()
    service.create_game(room)
    return _decision_context(
        service.load_state(room), "player_1", turn, room, MAP, seed, 0,
        {"player_1": "(no report yet)", "player_2": "(no report yet)"},
    )


# ===========================================================================
# WP3: LLMPolicy
# ===========================================================================


def test_llm_policy_happy_path(fake_brain):
    policy = LLMPolicy(
        model="openai/gpt-4o-mini",
        blueprint=_load_blueprint("expansionist-v1"),
        blueprint_id="expansionist-v1",
    )
    turn_outcome = policy.orders(_ctx(), __import__("random").Random(1))
    assert not turn_outcome.trace.get("failure_class")
    assert "Tax." in turn_outcome.text
    assert turn_outcome.trace["rationale"] == "I will tax and recruit."
    assert turn_outcome.trace["raw_reply"] == FAKE_REPLY
    assert turn_outcome.trace["usage"] == FAKE_USAGE
    assert turn_outcome.trace["attempts"] == 1
    assert turn_outcome.trace["latency_ms"] == 42.0
    assert turn_outcome.trace["orders_accepted"] >= 3
    assert turn_outcome.trace["input_hashes"]["messages"]
    assert turn_outcome.trace["blueprint_id"] == "expansionist-v1"


def test_llm_policy_missing_marker_falls_back_to_whole_reply(fake_brain, monkeypatch):
    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda **kw: brain.ChatResult(
            text="Tax.\nRecruit 5 soldiers in Highfell.", model="m", attempts=1,
            latency_ms=1.0, usage={},
        ),
    )
    policy = LLMPolicy(model="m")
    turn_outcome = policy.orders(_ctx(), __import__("random").Random(1))
    assert "Tax." in turn_outcome.text
    assert "Recruit 5 soldiers in Highfell." in turn_outcome.text


def test_llm_policy_empty_reply_is_noop(fake_brain, monkeypatch):
    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda **kw: brain.ChatResult(
            text="", model="m", attempts=1, latency_ms=1.0, usage={},
        ),
    )
    policy = LLMPolicy(model="m")
    turn_outcome = policy.orders(_ctx(), __import__("random").Random(1))
    assert turn_outcome.trace["no_op"] is True
    assert turn_outcome.trace["orders_accepted"] == 0


def test_llm_policy_narrative_lines_are_dropped(fake_brain, monkeypatch):
    reply = (
        "--- ORDERS ---\n"
        "monitor the movements of the Shadow Syndicate.\n"
        "Do the thing.\n"
        "Tax.\n"
    )
    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda **kw: brain.ChatResult(
            text=reply, model="m", attempts=1, latency_ms=1.0, usage={},
        ),
    )
    policy = LLMPolicy(model="m")
    turn_outcome = policy.orders(_ctx(), __import__("random").Random(1))
    assert "monitor the movements" not in turn_outcome.text
    assert "Do the thing." not in turn_outcome.text
    assert "Tax." in turn_outcome.text


def test_llm_policy_preserves_emitted_warning_metric_before_filter(fake_brain, monkeypatch):
    reply = (
        "--- ORDERS ---\n"
        "Have Emperor Marcus attack Ashford.\n"
        "Tax.\n"
    )
    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda **kw: brain.ChatResult(
            text=reply, model="m", attempts=1, latency_ms=1.0, usage={},
        ),
    )
    outcome = LLMPolicy(model="m").orders(
        _ctx(), __import__("random").Random(1)
    )
    assert outcome.trace["orders_emitted"] == 2
    assert outcome.trace["emitted_warning_order_lines"] == 1
    assert outcome.trace["emitted_warning_messages"] >= 1
    assert "attack Ashford" in outcome.text
    assert outcome.trace["orders_accepted"] == 1


def test_warning_metric_counts_a_warned_line_once():
    from soe.orders import MoveOrder

    order = MoveOrder(player_id="player_1", original_text="Do the thing.")
    order.warnings.extend(["first explanation", "second explanation"])
    assert _order_line_metrics([order]) == (1, 1, 2)


def test_emitted_metric_counts_physical_lines_not_parser_objects():
    ctx = _ctx()
    total, _, _, _ = _emitted_line_metrics(
        "--- orders ---\nTax; Wait for 1 day.\n", ctx.game_state, ctx.faction_id
    )
    assert total == 1


def test_exact_one_sided_sweep_probability():
    assert _one_sided_sweep_p(4, 0) == pytest.approx(0.0625)
    assert _one_sided_sweep_p(24, 0) == pytest.approx(5.960464477539063e-08)


def test_blueprint_behavior_gap_is_normalized():
    summary = {
        "blueprint_diff": {
            "a": {"orders": {"recruit": 80, "attack": 20}},
            "b": {"orders": {"recruit": 50, "attack": 50}},
        }
    }
    gap = _blueprint_behavior_gap(summary)
    assert gap["maximum_order_share_gap"] == pytest.approx(0.3)
    assert gap["family"] in {"recruit", "attack"}


def test_official_preflight_enforces_frozen_contract(monkeypatch, tmp_path):
    from scripts import arena, arena_bundle

    config = load_config(arena._REPO_ROOT / "configs" / "phase0_competence.json")
    receipt = tmp_path / "probe.json"
    receipt.write_text(
        json.dumps(
            {
                "probes": {
                    "openai/gpt-4o-mini": {
                        "success": True,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(arena, "PHASE0_PROBE_PATH", receipt)
    monkeypatch.setattr(brain, "is_configured", lambda: True)
    monkeypatch.setattr(
        arena_bundle,
        "git_provenance",
        lambda root: {"git_commit": "abc", "git_dirty": False},
    )
    validate_official_preflight(config)

    changed = json.loads(json.dumps(config))
    changed["entrants"][1] = {"type": "random"}
    with pytest.raises(BundleError, match="opponent"):
        validate_official_preflight(changed)


def test_official_preflight_refuses_dirty_worktree(monkeypatch, tmp_path):
    from scripts import arena, arena_bundle

    config = load_config(arena._REPO_ROOT / "configs" / "phase0_blueprints.json")
    receipt = tmp_path / "probe.json"
    receipt.write_text(
        json.dumps(
            {
                "probes": {
                    "openai/gpt-4o-mini": {
                        "success": True,
                        "checked_at": datetime.now(timezone.utc).isoformat(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(arena, "PHASE0_PROBE_PATH", receipt)
    monkeypatch.setattr(brain, "is_configured", lambda: True)
    monkeypatch.setattr(
        arena_bundle,
        "git_provenance",
        lambda root: {"git_commit": "abc", "git_dirty": True},
    )
    with pytest.raises(BundleError, match="clean worktree"):
        validate_official_preflight(config)


def test_official_preflight_requires_recent_probe(monkeypatch, tmp_path):
    from scripts import arena, arena_bundle

    config = load_config(arena._REPO_ROOT / "configs" / "phase0_competence.json")
    monkeypatch.setattr(brain, "is_configured", lambda: True)
    monkeypatch.setattr(arena, "PHASE0_PROBE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(
        arena_bundle,
        "git_provenance",
        lambda root: {"git_commit": "abc", "git_dirty": False},
    )
    with pytest.raises(BundleError, match="successful recent model probe"):
        validate_official_preflight(config)


def test_official_run_gate_is_machine_readable(tmp_path):
    from scripts.arena import _REPO_ROOT

    config = load_config(_REPO_ROOT / "configs" / "phase0_competence.json")
    llm = "llm:openai/gpt-4o-mini:expansionist-v1"
    opponent = "scripted:military"
    results = [
        {
            "turns_played": 30,
            "final_state_sha": "a" * 64,
            "wall_seconds": 1.0,
        }
        for _ in range(80)
    ]
    summary = {
        "policies": [llm, opponent],
        "pairs": [{} for _ in range(40)],
        "pair_sweeps": {llm: 24, opponent: 0},
        "games": 80,
        "errors": [],
        "results": results,
        "reliability": {
            llm: {
                "calls_attempted": 2400,
                "calls_completed": 2400,
                "parseable_call_rate": 1.0,
                "cost": 1.2,
            },
            opponent: {"n_a": True},
        },
        "emitted_order_quality": {
            llm: {"warning_order_rate": 0.04},
            opponent: {"n_a": True},
        },
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps({"git_dirty": False}), encoding="utf-8"
    )
    verdict = _phase0_run_gate(summary, config, tmp_path)
    assert verdict["status"] == "pass"
    assert verdict["sweep_test"]["one_sided_p"] < 0.01

    summary["emitted_order_quality"][llm]["warning_order_rate"] = 0.051
    verdict = _phase0_run_gate(summary, config, tmp_path)
    assert verdict["status"] == "fail"
    assert verdict["criteria"]["warning_order_rate"] is False


def test_llm_policy_provider_failure_is_recorded_noop(fake_brain, monkeypatch):
    monkeypatch.setattr(
        brain,
        "chat_result",
        lambda **kw: (_ for _ in ()).throw(
            brain.LLMError(
                "LLM request failed after 3 attempts: _RetryableError: HTTP 429: rate limited"
            )
        ),
    )
    policy = LLMPolicy(model="m")
    turn_outcome = policy.orders(_ctx(), __import__("random").Random(1))
    assert turn_outcome.trace["failure_class"] == "http_429"
    assert turn_outcome.trace["no_op"] is True
    assert turn_outcome.text.startswith("# no-op")


def test_llm_policy_unconfigured_is_recorded_noop(fake_brain, monkeypatch):
    monkeypatch.setattr(brain, "is_configured", lambda: False)
    policy = LLMPolicy(model="m")
    turn_outcome = policy.orders(_ctx(), __import__("random").Random(1))
    assert turn_outcome.trace["failure_class"] == "not_configured"
    assert turn_outcome.trace["no_op"] is True


def test_shared_spend_ceiling_prevents_provider_calls(fake_brain):
    policies = build_policies_from_config(_smoke_config(max_spend_usd=0.0))
    outcome = policies[0].orders(_ctx(), __import__("random").Random(1))
    assert outcome.trace["failure_class"] == "budget_exhausted"
    assert outcome.trace["no_op"] is True
    assert fake_brain["n"] == 0


def test_failure_class_classification():
    assert _failure_class(brain.LLMError("HTTP 429: rate")) == "http_429"
    assert _failure_class(brain.LLMError("HTTP 400: bad")) == "http_4xx"
    assert _failure_class(brain.LLMError("HTTP 500: boom")) == "http_5xx"
    assert _failure_class(brain.LLMError("ConnectError: refused")) == "transport"
    assert _failure_class(brain.LLMError("mystery")) == "other"


def test_llm_policy_blueprint_in_prompt_without_touching_system_rules(fake_brain):
    a = LLMPolicy(model="m", blueprint=_load_blueprint("expansionist-v1"), blueprint_id="expansionist-v1")
    b = LLMPolicy(model="m", blueprint=_load_blueprint("consolidation-v1"), blueprint_id="consolidation-v1")
    policy_a = a.orders(_ctx(seed=7, turn=1), __import__("random").Random(1))
    policy_b = b.orders(_ctx(seed=7, turn=1), __import__("random").Random(1))
    assert policy_a.trace["input_hashes"]["prompt_signature"] != policy_b.trace["input_hashes"]["prompt_signature"]


def test_blueprint_doctrines_share_sections_and_max_chars():
    from webapp.ai import context

    a = _load_blueprint("expansionist-v1")
    b = _load_blueprint("consolidation-v1")
    section_a = context.doctrine_section(a)
    section_b = context.doctrine_section(b)
    keys_a = {line.split(":")[0].strip() for line in section_a.splitlines()}
    keys_b = {line.split(":")[0].strip() for line in section_b.splitlines()}
    assert keys_a == keys_b == {"- objective", "- economy", "- risk", "- diplomacy"}
    for line in section_a.splitlines() + section_b.splitlines():
        assert len(line) <= 400


# ===========================================================================
# play_game: reports, fog, traces
# ===========================================================================


def test_turn_n_report_is_available_at_turn_n_plus_one(fake_brain):
    calls = {"seen": []}

    class SpyPolicy(RandomPolicy):
        name = "spy"

        def orders(self, ctx, rng):
            calls["seen"].append((ctx.turn, ctx.previous_report))
            return super().orders(ctx, rng)

    policies = [SpyPolicy(), RandomPolicy()]
    result = play_game("SP001", MAP, policies, 3, 1)
    assert result.turns_played == 3
    turn1, report1 = calls["seen"][0]
    turn2, report2 = calls["seen"][1]
    assert (turn1, turn2) == (1, 2)
    assert report1 == "(no report yet)"
    assert report2 != "(no report yet)"
    assert "SPOILS OF EMPIRE" in report2


def test_play_game_llm_vs_random_ends_with_winner(fake_brain):
    policies = _policy_pair()
    result = play_game("SP002", MAP, policies, 3, 2)
    assert result.turns_played == 3
    assert result.winner in (None, "player_1", "player_2")
    assert len(result.traces) == 6
    llm_traces = [t for t in result.traces if t["policy"].startswith("llm:")]
    assert len(llm_traces) == 3
    assert all(t["orders_accepted"] >= 0 for t in llm_traces)
    assert result.final_state_sha == ""


def test_play_game_fog_of_war_in_llm_messages(fake_brain):
    """The state section of the LLM payload leaks nothing about player_2."""
    ctx = _ctx(seed=5, turn=1)
    messages = context.build_messages(ctx)
    user = messages[1]["content"]
    state_section = user.split("=== STRUCTURED STATE ===")[1]
    state_section = state_section.split("=== YOUR LAST TURN REPORT")[0]
    assert "Silver Horde" not in state_section
    assert "Khan Tengri" not in state_section
    assert "player_2" not in state_section
    for city in json.loads(state_section)["cities"]:
        if not city["observed"]:
            assert city["controlled_by"] is None
            assert city["secured_by"] is None
            assert city["sovereign"] is None


# ===========================================================================
# WP4: run bundle and resume
# ===========================================================================


def test_bundle_records_decisions_idempotently(tmp_path):
    bundle = RunBundle(tmp_path / "run-test")
    bundle.run_dir.mkdir(parents=True)
    ok = bundle.record_decision("G1", 1, "player_1", {"orders_text": "Tax."})
    assert ok is True
    again = bundle.record_decision("G1", 1, "player_1", {"orders_text": "Tax."})
    assert again is False
    assert bundle.recorded_keys() == {("G1", 1, "player_1")}
    assert bundle.get_decision("G1", 1, "player_1")["orders_text"] == "Tax."


def test_bundle_detects_truncated_decision(tmp_path):
    bundle = RunBundle(tmp_path / "run-bad")
    bundle.run_dir.mkdir(parents=True)
    path = bundle.decision_path("G1", 1, "player_1")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BundleError):
        bundle.recorded_keys()
    with pytest.raises(BundleError):
        bundle.get_decision("G1", 1, "player_1")


def _partial_run(config, out_dir, bundle):
    """Seed 0 both orderings only -- simulates an interrupted batch."""
    policies = build_policies_from_config(config)
    from scripts.arena import play_game as _pg

    for ordering in ((0, 1), (1, 0)):
        seat_policies = [policies[ordering[0]], policies[ordering[1]]]
        _pg(
            "AR000", MAP, seat_policies, int(config["turns"]), 0,
            game_id=f"AR000_{'ab' if ordering == (0, 1) else 'ba'}",
            bundle=bundle,
        )
    bundle.finish("interrupted")


def test_resume_replays_recorded_decisions_without_model_calls(fake_brain, tmp_path):
    config = _smoke_config()
    turns = int(config["turns"])
    out = tmp_path / "arena"
    bundle = prepare_bundle(config, out)
    _partial_run(config, out, bundle)
    # One LLM seat per game: seed 0 only -> 2 games x turns calls.
    assert fake_brain["n"] == 2 * turns

    resumed = resume_bundle(out, bundle.run_id, config)
    summary = run_batch(config, resumed.run_dir, bundle=resumed)

    # Seed 0 was replayed from records; only seed 1 made model calls.
    assert fake_brain["n"] == 4 * turns
    assert summary["games"] == 4
    assert resumed.load_manifest()["status"] == "complete"
    assert (resumed.run_dir / "ARENA_REPORT.md").exists()
    assert "reliability" in summary and "strategy" in summary and "blueprint_diff" in summary
    llm = summary["policies"][0]
    random_policy = summary["policies"][1]
    assert summary["reliability"][random_policy]["n_a"] is True
    assert summary["emitted_order_quality"][llm]["order_lines"] > 0
    assert summary["warning_order_lines_total"][llm] <= summary["warnings_total"][llm]
    assert summary["warning_order_rate"][llm] is not None


def test_resume_reproduces_interrupted_run_state(fake_brain, tmp_path):
    config = _smoke_config()
    out = tmp_path / "arena"

    bundle = prepare_bundle(config, out)
    _partial_run(config, out, bundle)
    partial_state = bundle.get_turn("AR000_ab", 3)["state_sha"]

    resumed = resume_bundle(out, bundle.run_id, config)
    run_batch(config, resumed.run_dir, bundle=resumed)
    assert resumed.get_turn("AR000_ab", 3)["state_sha"] == partial_state

    # A fresh uninterrupted run with the same fake replies reproduces the
    # same final states and the same result.
    fresh_out = tmp_path / "arena-fresh"
    fresh_bundle = prepare_bundle(config, fresh_out)
    fresh_summary = run_batch(config, fresh_bundle.run_dir, bundle=fresh_bundle)
    resumed_summary = json.loads(
        (resumed.run_dir / "arena_results.json").read_text(encoding="utf-8")
    )
    for i in range(4):
        assert resumed_summary["results"][i]["final_state_sha"] == (
            fresh_summary["results"][i]["final_state_sha"]
        )
    assert resumed_summary["wins"] == fresh_summary["wins"]


def _turn_hashes(bundle) -> dict[tuple[str, int], str]:
    """Every recorded (game, turn) -> state hash in a run bundle."""
    hashes: dict[tuple[str, int], str] = {}
    for line in bundle.turns_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        hashes[(record["game"], record["turn"])] = record["state_sha"]
    return hashes


def test_resume_reproduces_every_turn_hash_not_just_the_final_one(fake_brain, tmp_path):
    """The reserve Phase 0 left open: equality of the whole trace.

    Matching final hashes only prove the two runs ended in the same place.
    A resumed batch that took a different route to it — replaying a decision
    against a state rebuilt slightly differently — would still pass that. The
    contract Phase 1 needs from a resumable league is stronger: turn by turn,
    game by game, an interrupted-and-resumed run and an uninterrupted one are
    the same run.
    """
    config = _smoke_config()
    out = tmp_path / "arena"

    bundle = prepare_bundle(config, out)
    _partial_run(config, out, bundle)
    resumed = resume_bundle(out, bundle.run_id, config)
    run_batch(config, resumed.run_dir, bundle=resumed)

    fresh_bundle = prepare_bundle(config, tmp_path / "arena-fresh")
    run_batch(config, fresh_bundle.run_dir, bundle=fresh_bundle)

    resumed_hashes = _turn_hashes(resumed)
    fresh_hashes = _turn_hashes(fresh_bundle)

    assert resumed_hashes, "the resumed run recorded no turns"
    assert set(resumed_hashes) == set(fresh_hashes)
    assert resumed_hashes == fresh_hashes
    # Every hash is a real digest, not an empty string compared to itself.
    assert all(len(sha) == 64 for sha in resumed_hashes.values())


def test_resume_refuses_changed_config(fake_brain, tmp_path):
    config = _smoke_config()
    out = tmp_path / "arena"
    bundle = prepare_bundle(config, out)
    _partial_run(config, out, bundle)

    changed = _smoke_config(turns=5)
    with pytest.raises(BundleError, match="turns"):
        resume_bundle(out, bundle.run_id, changed)


def test_resume_refuses_manifest_tamper(fake_brain, tmp_path):
    config = _smoke_config()
    out = tmp_path / "arena"
    bundle = prepare_bundle(config, out)
    _partial_run(config, out, bundle)

    manifest_path = bundle.run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["map"] = "world.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BundleError, match="map"):
        resume_bundle(out, bundle.run_id, config)


def test_no_credentials_in_bundle_records(fake_brain, tmp_path):
    config = _smoke_config()
    out = tmp_path / "arena"
    bundle = prepare_bundle(config, out)
    run_batch(config, bundle.run_dir, bundle=bundle)
    for path in bundle.run_dir.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".md", ".txt", ".jsonl"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "sk-test-secret-key" not in text


def test_manifest_carries_provenance(fake_brain, tmp_path):
    config = _smoke_config()
    out = tmp_path / "arena"
    bundle = prepare_bundle(config, out)
    manifest = bundle.load_manifest()
    assert manifest["schema_version"] == "1"
    assert manifest["status"] == "running"
    assert manifest["model"] == "openai/gpt-4o-mini"
    assert manifest["map_hash"]
    assert manifest["blueprints"][0]["id"] == "expansionist-v1"
    assert manifest["blueprints"][0]["hash"]
    assert manifest["git_commit"]
    assert manifest["git_dirty"] is True or manifest["git_dirty"] is False
    assert manifest["seed_pairs"] == 2
    assert manifest["prompt_hashes"]["expansionist-v1"]
    copied = bundle.blueprints_dir / "expansionist-v1.json"
    assert copied.exists()
    assert (
        copied.read_bytes()
        == (_REPO_ROOT / "configs" / "blueprints" / "expansionist-v1.json").read_bytes()
    )


def test_blueprint_ids_cannot_escape_the_blueprint_directory(tmp_path):
    """C6: the id becomes a path on both the read and the write side."""
    from scripts.arena import BLUEPRINTS_DIR, blueprint_path, build_policy
    from scripts.arena_bundle import RunBundle

    key_file = "../../server_data/llm_settings"
    for evil in (
        key_file,
        "..\\..\\server_data\\llm_settings",
        "/etc/passwd",
        "expansionist-v1/../../../pyproject",
        "Expansionist-V1",
        "",
        "  ",
    ):
        with pytest.raises(ValueError):
            blueprint_path(evil)

    with pytest.raises(ValueError):
        _load_blueprint(key_file)
    with pytest.raises(ValueError):
        build_policy(f"llm:openai/gpt-4o-mini:{key_file}")

    good = blueprint_path("expansionist-v1")
    assert good == (BLUEPRINTS_DIR / "expansionist-v1.json").resolve()
    assert _load_blueprint("expansionist-v1")["id"]

    # The bundle refuses to write a copy outside its own blueprints dir.
    bundle = RunBundle(tmp_path / "run")
    with pytest.raises(BundleError):
        bundle.copy_blueprints(
            {"../escaped": _REPO_ROOT / "configs" / "blueprints" / "expansionist-v1.json"}
        )
    assert not (tmp_path / "run" / "escaped.json").exists()
    assert not (tmp_path / "escaped.json").exists()


def test_manifest_rejects_a_traversing_blueprint_id(tmp_path):
    config = _smoke_config()
    config["entrants"][0]["blueprint"] = "../../server_data/llm_settings"
    with pytest.raises(ValueError):
        prepare_bundle(config, tmp_path / "arena")


def test_manifest_captures_git_state_before_writing_output(
    fake_brain, tmp_path, monkeypatch
):
    """A bundle inside the repo must not make its own manifest dirty."""
    from scripts import arena_bundle

    out = tmp_path / "arena"
    run_id = "official-candidate"
    run_dir = out / run_id

    def provenance_before_output(_root):
        return {
            "git_commit": "frozen-commit",
            "git_dirty": run_dir.exists(),
        }

    monkeypatch.setattr(arena_bundle, "git_provenance", provenance_before_output)
    bundle = prepare_bundle(_smoke_config(), out, run_id=run_id)
    manifest = bundle.load_manifest()
    assert manifest["git_commit"] == "frozen-commit"
    assert manifest["git_dirty"] is False


_REPO_ROOT = Path(__file__).resolve().parent.parent
