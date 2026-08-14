"""
Phase 2, first half: a coach tries a blueprint without an operator.

A training run is an arena run, so these tests check the layer that decides
*who may run what* and *what the record is allowed to contain*, and then check
that the arena actually plays it. All model calls are faked — no network.

What the phase demands of this half:

* a training arena with a fixed scenario and predefined opponents;
* training quotas per coach and per version;
* no private chain-of-thought on disk;
* every number a debrief will show coming from the persisted match record.
"""

import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p2_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p2_games_{uuid.uuid4().hex[:8]}"),
)
os.environ["SOE_LLM_KEY"] = "sk-test-secret-key"

from webapp import blueprints as blueprints_mod  # noqa: E402
from webapp import training  # noqa: E402
from webapp.ai import brain  # noqa: E402
from webapp.blueprints import BlueprintStore  # noqa: E402
from webapp.coaches import CoachStore  # noqa: E402
from webapp.training import (  # noqa: E402
    QuotaExceeded,
    TrainingError,
    TrainingStore,
)

FAKE_USAGE = {
    "prompt_tokens": 300,
    "completion_tokens": 40,
    "total_tokens": 340,
    "cost": 0.0001,
}
#: The first line is exactly what must never reach disk.
PRIVATE_REASONING = "Internally I think the opponent is weak and I will feint."
FAKE_REPLY = (
    f"{PRIVATE_REASONING}\n"
    "--- ORDERS ---\n"
    "Tax.\n"
    "Have Emperor Marcus tax.\n"
    "Wait for 1 day.\n"
)

DOCTRINE = {
    "objective": "Take the nearest unsecured city, then hold it.",
    "economy": "Soldiers first.",
    "risk": "Accept losses to hold a contested town.",
    "diplomacy": "Neutral unless attacked.",
}


@pytest.fixture
def fake_brain(monkeypatch):
    calls = {"n": 0}

    def fake_chat_result(*, model, messages, temperature=0.0, max_tokens=1500, images=()):
        calls["n"] += 1
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
    monkeypatch.setattr(brain, "chat", lambda **kwargs: fake_chat_result(**kwargs).text)
    return calls


@pytest.fixture
def bp_store(tmp_path) -> BlueprintStore:
    return BlueprintStore(tmp_path / "blueprints.json")


@pytest.fixture
def store(tmp_path) -> TrainingStore:
    return TrainingStore(tmp_path / "training.json", runs_root=tmp_path / "runs")


@pytest.fixture
def ada(tmp_path):
    coach, _ = CoachStore(tmp_path / "coaches.json").create("Ada")
    return coach


@pytest.fixture
def bruno(tmp_path):
    coach, _ = CoachStore(tmp_path / "coaches2.json").create("Bruno")
    return coach


@pytest.fixture
def frozen(bp_store, ada):
    """A frozen blueprint of Ada's, ready to be trained."""
    blueprint = bp_store.create(
        ada,
        "Fast Expansion",
        doctrine=DOCTRINE,
        persona="Blunt.",
        runtime={"model": "openai/gpt-4o-mini", "temperature": 0.0},
    )
    bp_store.freeze(ada, blueprint.id, 1)
    return blueprint


@pytest.fixture
def fast_scenario(monkeypatch):
    """The catalogue, shortened so a test plays in a second, not a minute."""
    catalogue = {
        key: training.Scenario(
            id=value.id,
            name=value.name,
            description=value.description,
            map="starter_map.json",
            turns=2,
            seed_pairs=1,
            opponent=value.opponent,
            max_spend_usd=value.max_spend_usd,
        )
        for key, value in training.scenarios().items()
    }
    monkeypatch.setattr(training, "_scenarios", catalogue)
    return catalogue


@pytest.fixture(autouse=True)
def _clean_games():
    from webapp.rooms import GAMES_ROOT

    yield
    if GAMES_ROOT.exists():
        shutil.rmtree(GAMES_ROOT, ignore_errors=True)


# ======================================================================
# the catalogue is fixed, not chosen at request time
# ======================================================================


def test_the_scenario_catalogue_loads_and_names_its_opponents():
    catalogue = training.scenarios()
    assert set(catalogue) == {"sparring", "aggressor", "wild-card"}
    assert catalogue["sparring"].opponent_label == "scripted:balanced"
    assert catalogue["aggressor"].opponent_label == "scripted:military"
    assert catalogue["wild-card"].opponent_label == "random"
    for scenario in catalogue.values():
        # A run a coach cannot pay for is a run the operator pays for.
        assert scenario.max_spend_usd > 0
        # One seed pair minimum: a single game is start-city luck.
        assert scenario.seed_pairs >= 1


def test_an_unknown_scenario_says_what_the_choices_are(store, ada, frozen, bp_store):
    with pytest.raises(TrainingError, match="sparring"):
        store.start(ada, frozen.id, "whatever", blueprint_store=bp_store)


# ======================================================================
# who may run what
# ======================================================================


def test_starting_a_run_enrolls_the_frozen_version(store, ada, frozen, bp_store):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)

    assert run.coach_id == ada.id
    assert run.blueprint_id == frozen.id
    assert run.blueprint_version == 1
    assert run.blueprint_hash == bp_store.get(ada, frozen.id).version(1).content_hash
    assert run.status == training.STATUS_QUEUED
    assert run.opponent == "scripted:balanced"
    assert run.model == "openai/gpt-4o-mini"


def test_a_draft_cannot_be_trained(store, ada, bp_store):
    draft = bp_store.create(ada, "Half an idea", doctrine=DOCTRINE)
    with pytest.raises(Exception, match="no frozen version"):
        store.start(ada, draft.id, "sparring", blueprint_store=bp_store)


def test_a_coach_cannot_train_another_coachs_private_blueprint(
    store, ada, bruno, frozen, bp_store
):
    with pytest.raises(Exception, match="No blueprint"):
        store.start(bruno, frozen.id, "sparring", blueprint_store=bp_store)


def test_a_coach_cannot_read_another_coachs_run(store, ada, bruno, frozen, bp_store):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    with pytest.raises(TrainingError, match="No training run"):
        store.get(bruno, run.id)
    assert store.for_coach(bruno) == []


# ======================================================================
# quotas
# ======================================================================


def test_the_daily_quota_stops_a_coach(store, ada, frozen, bp_store, monkeypatch):
    monkeypatch.setattr(training, "QUOTA_PER_COACH_DAILY", 2)
    monkeypatch.setattr(training, "QUOTA_PER_VERSION", 99)

    store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    with pytest.raises(QuotaExceeded, match="today"):
        store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)


def test_the_daily_quota_rolls_off_after_a_day(store, ada, frozen, bp_store, monkeypatch):
    monkeypatch.setattr(training, "QUOTA_PER_COACH_DAILY", 1)
    monkeypatch.setattr(training, "QUOTA_PER_VERSION", 99)

    old = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    old.created_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

    # Yesterday's run neither blocks today nor is forgotten.
    fresh = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    assert len(store.for_coach(ada)) == 2
    assert fresh.id != old.id


def test_the_per_version_quota_stops_a_coach_rerunning_one_version(
    store, ada, frozen, bp_store, monkeypatch
):
    monkeypatch.setattr(training, "QUOTA_PER_COACH_DAILY", 99)
    monkeypatch.setattr(training, "QUOTA_PER_VERSION", 2)

    store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    store.start(ada, frozen.id, "aggressor", blueprint_store=bp_store)
    with pytest.raises(QuotaExceeded, match="new version"):
        store.start(ada, frozen.id, "wild-card", blueprint_store=bp_store)

    # A new version has its own allowance, which is the point of the limit.
    bp_store.new_version(ada, frozen.id)
    bp_store.freeze(ada, frozen.id, 2)
    second = store.start(ada, frozen.id, "sparring", version=2, blueprint_store=bp_store)
    assert second.blueprint_version == 2


def test_quota_state_reports_both_allowances(store, ada, frozen, bp_store):
    store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    state = store.quota_state(ada, frozen.id, 1)
    assert state["daily_used"] == 1
    assert state["version_used"] == 1
    assert state["daily_remaining"] == training.QUOTA_PER_COACH_DAILY - 1
    assert state["version_remaining"] == training.QUOTA_PER_VERSION - 1


# ======================================================================
# the run config: by value, redacted, pinned
# ======================================================================


def test_the_run_config_carries_the_blueprint_by_value(store, ada, frozen, bp_store):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    config = training.run_config(run, blueprint_store=bp_store)

    entrant = config["entrants"][0]
    assert entrant["type"] == "llm"
    assert entrant["blueprint_inline"]["doctrine"] == DOCTRINE
    assert entrant["blueprint_label"] == f"{frozen.id}_v1"
    assert entrant["blueprint_content_hash"] == run.blueprint_hash
    # There is no file to point at, so there must be no file reference.
    assert "blueprint" not in entrant
    assert config["entrants"][1] == {"type": "scripted", "style": "balanced"}
    assert config["redact_reasoning"] is True


def test_a_run_whose_blueprint_moved_refuses_before_it_costs_anything(
    store, ada, frozen, bp_store
):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    bp_store.get(ada, frozen.id).version(1).doctrine["objective"] = "Turtle."

    with pytest.raises(Exception, match="no longer matches"):
        training.run_config(run, blueprint_store=bp_store)


def test_execute_records_a_blueprint_that_moved_as_a_failed_run(
    store, ada, frozen, bp_store, fake_brain, fast_scenario
):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    bp_store.get(ada, frozen.id).version(1).doctrine["objective"] = "Turtle."

    done = training.execute(run, store, blueprint_store=bp_store)

    assert done.status == training.STATUS_FAILED
    assert "no longer matches" in done.error
    assert fake_brain["n"] == 0


# ======================================================================
# playing one
# ======================================================================


def test_a_training_run_plays_and_records_where_its_evidence_is(
    store, ada, frozen, bp_store, fake_brain, fast_scenario
):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    done = training.execute(run, store, blueprint_store=bp_store)

    assert done.status == training.STATUS_COMPLETE, done.error
    assert done.run_id
    bundle_dir = Path(done.run_dir)
    assert (bundle_dir / "manifest.json").exists()
    assert (bundle_dir / "arena_results.json").exists()
    assert (bundle_dir / "turns.jsonl").exists()
    # One seed pair is two games, seats exchanged.
    assert done.result["games"] == 2
    assert done.result["wins"] + done.result["opponent_wins"] + done.result["draws"] == 2
    assert fake_brain["n"] > 0


def test_the_run_headline_comes_from_the_persisted_summary(
    store, ada, frozen, bp_store, fake_brain, fast_scenario
):
    """Every number a coach is shown must be re-derivable from the record."""
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    done = training.execute(run, store, blueprint_store=bp_store)

    summary = json.loads(
        (Path(done.run_dir) / "arena_results.json").read_text(encoding="utf-8")
    )
    mine = done.result["policy"]
    assert done.result["games"] == summary["games"]
    assert mine in summary["policies"]
    assert done.result["wins"] == summary["wins"].get(mine, 0)
    assert done.result["opponent_wins"] == sum(
        wins for policy, wins in summary["wins"].items() if policy != mine
    )
    assert done.result["sweeps"] == summary["pair_sweeps"].get(mine, 0)


def test_a_training_run_persists_no_private_reasoning(
    store, ada, frozen, bp_store, fake_brain, fast_scenario
):
    """The model's text before the orders marker must not reach disk."""
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    done = training.execute(run, store, blueprint_store=bp_store)

    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in Path(done.run_dir).rglob("turn_*_player_*.json")
    ]
    llm_records = [r for r in records if str(r.get("policy", "")).startswith("llm:")]
    assert llm_records, "the run recorded no model decisions"
    for record in llm_records:
        assert "raw_reply" not in record
        assert "rationale" not in record
        assert record["reasoning_redacted"] is True
        # What the agent did is still fully there.
        assert "orders_text" in record
        assert "orders_extracted_text" in record
        assert "order_types" in record

    for path in Path(done.run_dir).rglob("*"):
        if path.is_file():
            assert PRIVATE_REASONING not in path.read_text(
                encoding="utf-8", errors="ignore"
            )


def test_the_bundle_holds_the_blueprint_that_was_played(
    store, ada, frozen, bp_store, fake_brain, fast_scenario
):
    """The run stays readable after the coach's store has moved on."""
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    done = training.execute(run, store, blueprint_store=bp_store)

    written = Path(done.run_dir) / "blueprints" / f"{frozen.id}_v1.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8"))["doctrine"] == DOCTRINE

    manifest = json.loads(
        (Path(done.run_dir) / "manifest.json").read_text(encoding="utf-8")
    )
    entry = next(b for b in manifest["blueprints"] if b["id"] == f"{frozen.id}_v1")
    assert entry["hash"] and entry["file"] == f"{frozen.id}_v1.json"


def test_a_run_cannot_be_played_twice(
    store, ada, frozen, bp_store, fake_brain, fast_scenario
):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    training.execute(run, store, blueprint_store=bp_store)
    with pytest.raises(TrainingError, match="already been started"):
        training.execute(run, store, blueprint_store=bp_store)


# ======================================================================
# the HTTP surface a coach actually uses
# ======================================================================


@pytest.fixture
def api(monkeypatch, tmp_path, bp_store, fake_brain, fast_scenario):
    """The app wired to clean coach, blueprint and training stores."""
    from fastapi.testclient import TestClient

    from webapp import coaches as coaches_mod
    from webapp.main import app

    monkeypatch.setattr(
        coaches_mod, "_store", CoachStore(tmp_path / "api_coaches.json")
    )
    monkeypatch.setattr(blueprints_mod, "_store", bp_store)
    monkeypatch.setattr(
        training,
        "_store",
        TrainingStore(tmp_path / "api_training.json", runs_root=tmp_path / "api_runs"),
    )
    return TestClient(app)


def test_a_coach_runs_a_training_end_to_end_over_the_api(api, bp_store):
    created = api.post("/api/coaches", json={"name": "Ada"})
    assert created.status_code == 200, created.text
    headers = {"X-Coach-Key": created.json()["coach_key"]}

    catalogue = api.get("/api/training/scenarios", headers=headers)
    assert {s["id"] for s in catalogue.json()["scenarios"]} == {
        "sparring",
        "aggressor",
        "wild-card",
    }

    blueprint_id = api.post(
        "/api/blueprints",
        json={
            "name": "Fast Expansion",
            "doctrine": DOCTRINE,
            "runtime": {"model": "openai/gpt-4o-mini"},
        },
        headers=headers,
    ).json()["id"]
    api.post(f"/api/blueprints/{blueprint_id}/versions/1/freeze", headers=headers)

    started = api.post(
        "/api/training",
        json={"blueprint_id": blueprint_id, "scenario_id": "sparring"},
        headers=headers,
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["id"]

    # TestClient runs background tasks before returning, so by now it played.
    fetched = api.get(f"/api/training/{run_id}", headers=headers)
    body = fetched.json()
    assert body["status"] == "complete", body["error"]
    assert body["result"]["games"] == 2
    assert body["content_hash"]

    listing = api.get("/api/training", headers=headers).json()
    assert [r["id"] for r in listing["runs"]] == [run_id]
    assert listing["quota"]["daily_used"] == 1


def test_the_api_will_not_train_a_draft_or_another_coachs_blueprint(api, bp_store):
    ada = {
        "X-Coach-Key": api.post("/api/coaches", json={"name": "Ada"}).json()["coach_key"]
    }
    bruno = {
        "X-Coach-Key": api.post("/api/coaches", json={"name": "Bruno"}).json()[
            "coach_key"
        ]
    }
    blueprint_id = api.post(
        "/api/blueprints", json={"name": "Draft", "doctrine": DOCTRINE}, headers=ada
    ).json()["id"]

    draft_run = api.post(
        "/api/training",
        json={"blueprint_id": blueprint_id, "scenario_id": "sparring"},
        headers=ada,
    )
    assert draft_run.status_code == 400
    assert "frozen" in draft_run.json()["detail"]

    api.post(f"/api/blueprints/{blueprint_id}/versions/1/freeze", headers=ada)
    stolen = api.post(
        "/api/training",
        json={"blueprint_id": blueprint_id, "scenario_id": "sparring"},
        headers=bruno,
    )
    assert stolen.status_code == 404


def test_the_api_reports_an_exhausted_quota_as_429(api, bp_store, monkeypatch):
    monkeypatch.setattr(training, "QUOTA_PER_COACH_DAILY", 1)
    headers = {
        "X-Coach-Key": api.post("/api/coaches", json={"name": "Ada"}).json()["coach_key"]
    }
    blueprint_id = api.post(
        "/api/blueprints",
        json={
            "name": "Fast Expansion",
            "doctrine": DOCTRINE,
            "runtime": {"model": "openai/gpt-4o-mini"},
        },
        headers=headers,
    ).json()["id"]
    api.post(f"/api/blueprints/{blueprint_id}/versions/1/freeze", headers=headers)
    body = {"blueprint_id": blueprint_id, "scenario_id": "sparring"}

    assert api.post("/api/training", json=body, headers=headers).status_code == 200
    refused = api.post("/api/training", json=body, headers=headers)
    assert refused.status_code == 429
    assert "today" in refused.json()["detail"]


def test_runs_survive_a_reload_from_disk(
    store, ada, frozen, bp_store, fake_brain, fast_scenario
):
    run = store.start(ada, frozen.id, "sparring", blueprint_store=bp_store)
    training.execute(run, store, blueprint_store=bp_store)

    reloaded = TrainingStore(store.path, runs_root=store.runs_root)
    reread = reloaded.get(ada, run.id)
    assert reread.status == training.STATUS_COMPLETE
    assert reread.result["games"] == 2
    assert reread.blueprint_hash == run.blueprint_hash
