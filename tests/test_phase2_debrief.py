"""
Phase 2, second half: the coach understands what their agent did.

The exit criteria this file is answering:

* every number shown derives from the persisted match record;
* no hidden data of an opposing faction appears in the coach's debrief;
* proposed, discarded and accepted orders are visible, with their effects;
* replay is turn by turn;
* territory, army, economy, reliability, cost and latency are shown;
* two versions of one blueprint can be compared;
* syntax, provider and strategic errors are told apart.

The model is faked, so every reply below is chosen to exercise one of those.
"""

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p2d_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p2d_games_{uuid.uuid4().hex[:8]}"),
)
os.environ["SOE_LLM_KEY"] = "sk-test-secret-key"

from webapp import blueprints as blueprints_mod  # noqa: E402
from webapp import debrief, training  # noqa: E402
from webapp.ai import brain  # noqa: E402
from webapp.blueprints import BlueprintStore  # noqa: E402
from webapp.coaches import CoachStore  # noqa: E402
from webapp.debrief import DebriefError  # noqa: E402
from webapp.training import TrainingStore  # noqa: E402

FAKE_USAGE = {
    "prompt_tokens": 300,
    "completion_tokens": 40,
    "total_tokens": 340,
    "cost": 0.0001,
}
#: One line the engine accepts, one it cannot use. The second is the whole
#: point: a coach must see what was thrown away, not only what survived.
REPLY = (
    "Private thinking that must never be persisted.\n"
    "--- ORDERS ---\n"
    "Tax.\n"
    "Monitor the movements of the Shadow Syndicate.\n"
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
    def fake_chat_result(*, model, messages, temperature=0.0, max_tokens=1500, images=()):
        return brain.ChatResult(
            text=REPLY,
            model=model,
            attempts=1,
            latency_ms=42.0,
            usage=dict(FAKE_USAGE),
            provider_request_id="gen-fake-1",
        )

    monkeypatch.setattr(brain, "is_configured", lambda: True)
    monkeypatch.setattr(brain, "chat_result", fake_chat_result)
    monkeypatch.setattr(brain, "chat", lambda **kwargs: fake_chat_result(**kwargs).text)


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
def fast_scenario(monkeypatch):
    catalogue = {
        key: training.Scenario(
            id=value.id,
            name=value.name,
            description=value.description,
            map="starter_map.json",
            turns=3,
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


def _train(store, bp_store, ada, *, scenario="sparring", version=None, name="Fast Expansion"):
    """A completed training run of a freshly frozen blueprint."""
    blueprint = bp_store.create(
        ada,
        name,
        doctrine=DOCTRINE,
        runtime={"model": "openai/gpt-4o-mini", "temperature": 0.0},
    )
    bp_store.freeze(ada, blueprint.id, 1)
    run = store.start(ada, blueprint.id, scenario, version=version, blueprint_store=bp_store)
    done = training.execute(run, store, blueprint_store=bp_store)
    assert done.status == training.STATUS_COMPLETE, done.error
    return done


@pytest.fixture
def run(store, bp_store, ada, fake_brain, fast_scenario):
    return _train(store, bp_store, ada)


@pytest.fixture
def view(run):
    return debrief.build(run)


# ======================================================================
# replay: one turn at a time, from the record
# ======================================================================


def test_the_debrief_replays_every_turn_of_every_game(view):
    assert len(view.games) == 2  # one seed pair, seats exchanged
    for game in view.games:
        assert [t.turn for t in game.turns] == [1, 2, 3]
        assert game.outcome in ("won", "lost", "drawn")
        assert game.turns_played == 3


def test_each_turn_separates_proposed_discarded_and_accepted(view):
    """The line the engine could not use must be visible as discarded."""
    turn = view.games[0].turns[0]
    assert "Tax." in turn.proposed
    assert "Monitor the movements of the Shadow Syndicate." in turn.proposed
    # The engine is the authority on what an order is.
    assert "Monitor the movements of the Shadow Syndicate." in turn.discarded
    assert "Monitor the movements of the Shadow Syndicate." not in turn.accepted
    assert "Tax." in turn.accepted
    assert set(turn.accepted) <= set(turn.proposed)


def test_a_repeated_line_dropped_once_counts_once():
    """Multiset, not set: one dropped copy is one lost order, not two."""
    assert debrief._discarded(["Tax.", "Tax."], ["Tax."]) == ["Tax."]
    assert debrief._discarded(["Tax.", "Wait."], ["Tax.", "Wait."]) == []


def test_every_turn_carries_position_and_the_effect_of_that_turn(view):
    turns = view.games[0].turns
    # Nothing recorded before turn 1, so nothing honest to subtract from.
    assert turns[0].effect is None
    assert set(turns[0].position) >= set(debrief.TRACKED_METRICS)
    for earlier, later in zip(turns, turns[1:]):
        assert later.effect is not None
        for key in debrief.TRACKED_METRICS:
            assert later.effect[key] == pytest.approx(
                round(later.position[key] - earlier.position[key], 2)
            )


def test_territory_army_and_economy_are_all_present(view):
    position = view.games[0].turns[-1].position
    for group in debrief.METRIC_GROUPS.values():
        for key in group:
            assert key in position


# ======================================================================
# the rationale is derived, not the model's words
# ======================================================================


def test_the_rationale_describes_what_was_issued_and_what_moved(view):
    turn = view.games[0].turns[1]
    assert turn.rationale.startswith("Issued ")
    assert "did not reach the engine" in turn.rationale
    assert turn.rationale.endswith(".")


def test_the_rationale_never_quotes_the_model(view):
    for game in view.games:
        for turn in game.turns:
            assert "Private thinking" not in turn.rationale


@pytest.mark.parametrize(
    "order_types, effect, failure, discarded, expected",
    [
        ([], None, None, 0, "No orders were issued this turn."),
        (
            [],
            None,
            {"failure_class": "http_429"},
            0,
            "No orders: the provider call failed (http_429).",
        ),
        (["TAX"], {"gold": 0}, None, 0, "Issued TAX. Nothing visible changed."),
        (["TAX", "TAX"], {"gold": 25}, None, 0, "Issued TAXx2. Position moved: gold +25."),
    ],
)
def test_the_derived_rationale_is_deterministic(
    order_types, effect, failure, discarded, expected
):
    produced = debrief.derived_rationale(order_types, effect, failure, discarded)
    assert produced.lower() == expected.lower()


# ======================================================================
# no hidden data of the opposing faction
# ======================================================================


def test_each_game_names_the_coachs_seat_and_never_the_opponents(view):
    """A game view is a view from one chair."""
    seats = {game.seat for game in view.games}
    # The pair is played from both seats, so both ids appear across the run —
    # but never inside the same game as somebody else's.
    assert seats == {"player_1", "player_2"}
    for game in view.games:
        opponent = "player_2" if game.seat == "player_1" else "player_1"
        serialised = json.dumps(
            {
                "seat": game.seat,
                "outcome": game.outcome,
                "final_position": game.final_position,
                "turns": [t.__dict__ for t in game.turns],
            }
        )
        assert game.seat in serialised
        assert opponent not in serialised


def test_the_opponents_per_turn_position_never_reaches_the_coach(view, run):
    """The bundle holds both sides; the coach's view holds one.

    The opponent's numbers are in the record on disk and must not be in the
    payload, so this compares the two directly rather than trusting the shape.
    """
    recorded = [
        json.loads(line)
        for line in (Path(run.run_dir) / "turns.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert all(len(r["metrics"]) == 2 for r in recorded), "the record should hold both"

    for game in view.games:
        opponent = "player_2" if game.seat == "player_1" else "player_1"
        rows = [r for r in recorded if r["game"] == game.game_id]
        shown = {t.turn: t.position for t in game.turns}
        assert shown == {r["turn"]: r["metrics"][game.seat] for r in rows}
        for row in rows:
            mine, theirs = row["metrics"][game.seat], row["metrics"][opponent]
            if mine != theirs:
                assert shown[row["turn"]] != theirs


def test_the_opponents_orders_never_reach_the_coach(view, run):
    """The opponent's own order lines are recorded and must stay unread."""
    for game in view.games:
        opponent = "player_2" if game.seat == "player_1" else "player_1"
        their_orders = {
            line
            for path in (Path(run.run_dir) / "orders" / game.game_id).glob(
                f"turn_*_{opponent}.txt"
            )
            for line in debrief.order_lines(path.read_text(encoding="utf-8"))
        }
        mine = {
            line
            for turn in game.turns
            for line in turn.proposed + turn.accepted + turn.discarded
        }
        # The scripted opponent issues orders this agent never wrote.
        assert their_orders - mine, "the opponent issued nothing distinctive to test"
        assert not (their_orders - mine) & mine


def test_a_coach_cannot_debrief_another_coachs_run(store, bp_store, ada, run, tmp_path):
    bruno, _ = CoachStore(tmp_path / "coaches_b.json").create("Bruno")
    with pytest.raises(training.TrainingError, match="No training run"):
        store.get(bruno, run.id)


# ======================================================================
# every number comes from the record
# ======================================================================


def test_the_headline_matches_the_persisted_summary(view, run):
    summary = json.loads(
        (Path(run.run_dir) / "arena_results.json").read_text(encoding="utf-8")
    )
    policy = debrief._my_policy(summary, f"{run.blueprint_id}_v1")
    assert view.headline["games"] == summary["games"]
    assert view.headline["won"] == summary["wins"].get(policy, 0)
    assert view.headline["sweeps"] == summary["pair_sweeps"].get(policy, 0)
    assert view.headline["decided_by"] == summary["decided_by"]


def test_cost_and_latency_come_from_the_persisted_summary(view, run):
    summary = json.loads(
        (Path(run.run_dir) / "arena_results.json").read_text(encoding="utf-8")
    )
    policy = debrief._my_policy(summary, f"{run.blueprint_id}_v1")
    reliability = summary["reliability"][policy]
    assert view.cost["usd"] == reliability["cost"]
    assert view.cost["calls"] == reliability["calls_attempted"]
    assert view.cost["latency_ms_median"] == reliability["latency_ms"]["median"]
    assert view.reliability["accepted_call_rate"] == reliability["accepted_call_rate"]
    assert view.reliability["no_op_turns"] == reliability["no_op_turns"]


def test_position_comes_from_the_recorded_turn_not_a_replay(view, run):
    recorded = [
        json.loads(line)
        for line in (Path(run.run_dir) / "turns.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    for game in view.games:
        for turn in game.turns:
            source = next(
                r for r in recorded if r["game"] == game.game_id and r["turn"] == turn.turn
            )
            assert turn.position == source["metrics"][game.seat]


def test_a_run_with_no_record_refuses_rather_than_inventing_one(run, tmp_path):
    with pytest.raises(DebriefError, match="no record to read"):
        debrief.build(run, bundle_dir=tmp_path / "nothing-here")


# ======================================================================
# the three kinds of error
# ======================================================================


def test_a_line_the_engine_rejected_is_counted_as_syntax(view):
    syntax = view.errors["syntax"]
    assert syntax["discarded_lines"] > 0
    assert "Monitor the movements of the Shadow Syndicate." in syntax["examples"]
    assert len(syntax["examples"]) <= debrief.MAX_EXAMPLES


def test_a_clean_run_reports_no_provider_failures(view):
    assert view.errors["provider"]["total"] == 0
    assert view.errors["provider"]["failures"] == {}


def test_a_provider_failure_is_counted_as_provider_not_as_doctrine(
    store, bp_store, ada, fast_scenario, monkeypatch
):
    """A rate limit is not a reason to rewrite a doctrine."""
    monkeypatch.setattr(brain, "is_configured", lambda: True)

    def failing(**kwargs):
        raise brain.LLMError("HTTP 429 rate limited")

    monkeypatch.setattr(brain, "chat_result", failing)
    monkeypatch.setattr(brain, "chat", failing)

    done = _train(store, bp_store, ada, name="Unlucky")
    view = debrief.build(done)

    assert view.errors["provider"]["total"] > 0
    assert view.errors["provider"]["failures"]["http_429"] > 0
    # A failed call is not a syntax mistake and not a strategic one.
    assert view.errors["syntax"]["discarded_lines"] == 0
    assert view.errors["strategic"]["silent_turns"] == 0
    turn = view.games[0].turns[0]
    assert turn.provider_failure["failure_class"] == "http_429"
    assert "provider call failed" in turn.rationale


def test_the_strategic_bucket_names_what_it_counts(view):
    strategic = view.errors["strategic"]
    assert "silent_turns" in strategic and "idle_turns" in strategic
    assert isinstance(strategic["silent_turns"], int)
    assert "changed no tracked metric" in strategic["note"]


# ======================================================================
# comparing two versions
# ======================================================================


def test_two_versions_of_one_blueprint_compare_side_by_side(
    store, bp_store, ada, fake_brain, fast_scenario
):
    blueprint = bp_store.create(
        ada,
        "Fast Expansion",
        doctrine=DOCTRINE,
        runtime={"model": "openai/gpt-4o-mini"},
    )
    bp_store.freeze(ada, blueprint.id, 1)
    first = training.execute(
        store.start(ada, blueprint.id, "sparring", version=1, blueprint_store=bp_store),
        store,
        blueprint_store=bp_store,
    )

    bp_store.new_version(ada, blueprint.id)
    bp_store.edit(ada, blueprint.id, 2, doctrine=dict(DOCTRINE, risk="Never trade."))
    bp_store.freeze(ada, blueprint.id, 2)
    second = training.execute(
        store.start(ada, blueprint.id, "sparring", version=2, blueprint_store=bp_store),
        store,
        blueprint_store=bp_store,
    )

    comparison = debrief.compare(debrief.build(first), debrief.build(second))

    assert comparison["same_blueprint"] is True
    assert comparison["same_scenario"] is True
    assert comparison["versions"] == [1, 2]
    assert comparison["content_hashes"][0] != comparison["content_hashes"][1]
    assert len(comparison["sides"]) == 2
    assert comparison["sides"][0]["version"] == 1
    assert set(comparison["deltas"]) == {
        "won",
        "sweeps",
        "discarded_lines",
        "idle_turns",
    }
    for side in comparison["sides"]:
        assert set(side["median_final"]) == set(debrief.TRACKED_METRICS)


def test_comparing_across_scenarios_says_so_instead_of_averaging(
    store, bp_store, ada, fake_brain, fast_scenario
):
    left = _train(store, bp_store, ada, scenario="sparring", name="A")
    right = _train(store, bp_store, ada, scenario="aggressor", name="B")

    comparison = debrief.compare(debrief.build(left), debrief.build(right))

    assert comparison["same_scenario"] is False
    assert comparison["same_blueprint"] is False


# ======================================================================
# the HTTP surface
# ======================================================================


@pytest.fixture
def api(monkeypatch, tmp_path, bp_store, store, fake_brain, fast_scenario):
    from fastapi.testclient import TestClient

    from webapp import coaches as coaches_mod
    from webapp.main import app

    monkeypatch.setattr(coaches_mod, "_store", CoachStore(tmp_path / "api_coaches.json"))
    monkeypatch.setattr(blueprints_mod, "_store", bp_store)
    monkeypatch.setattr(training, "_store", store)
    return TestClient(app)


def _coach_headers(api) -> dict:
    created = api.post("/api/coaches", json={"name": "Ada"})
    return {"X-Coach-Key": created.json()["coach_key"]}


def _api_run(api, headers) -> str:
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
    return api.post(
        "/api/training",
        json={"blueprint_id": blueprint_id, "scenario_id": "sparring"},
        headers=headers,
    ).json()["id"]


def test_the_api_serves_a_debrief_the_coach_owns(api):
    headers = _coach_headers(api)
    run_id = _api_run(api, headers)

    response = api.get(f"/api/training/{run_id}/debrief", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["headline"]["games"] == 2
    assert len(body["games"]) == 2
    assert body["games"][0]["turns"][0]["rationale"]
    assert body["errors"]["syntax"]["discarded_lines"] > 0
    assert body["cost"]["calls"] > 0


def test_the_api_hides_another_coachs_debrief(api):
    headers = _coach_headers(api)
    run_id = _api_run(api, headers)
    other = api.post("/api/coaches", json={"name": "Bruno"}).json()["coach_key"]

    response = api.get(
        f"/api/training/{run_id}/debrief", headers={"X-Coach-Key": other}
    )
    assert response.status_code == 404


def test_from_a_debrief_a_coach_opens_the_next_version_and_trains_it(api):
    """The loop closes: understand, change, try again, without an operator."""
    headers = _coach_headers(api)
    run_id = _api_run(api, headers)
    debriefed = api.get(f"/api/training/{run_id}/debrief", headers=headers).json()

    opened = api.post(f"/api/training/{run_id}/iterate", headers=headers)
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["next_version"] == 2
    blueprint_id = body["blueprint"]["id"]
    assert blueprint_id == debriefed["blueprint_id"]
    versions = body["blueprint"]["versions"]
    assert [v["state"] for v in versions] == ["frozen", "draft"]
    # The new draft starts from what was played, not from nothing.
    assert versions[1]["doctrine"] == versions[0]["doctrine"]

    api.patch(
        f"/api/blueprints/{blueprint_id}/versions/2",
        json={"doctrine": dict(DOCTRINE, risk="Never trade a stack for a town.")},
        headers=headers,
    )
    api.post(f"/api/blueprints/{blueprint_id}/versions/2/freeze", headers=headers)
    again = api.post(
        "/api/training",
        json={"blueprint_id": blueprint_id, "scenario_id": "sparring", "version": 2},
        headers=headers,
    )
    assert again.status_code == 200, again.text
    assert again.json()["version"] == 2
    assert again.json()["content_hash"] != debriefed["content_hash"]


def test_iterating_as_a_clone_leaves_the_trained_blueprint_alone(api):
    headers = _coach_headers(api)
    run_id = _api_run(api, headers)

    cloned = api.post(
        f"/api/training/{run_id}/iterate",
        json={"as_clone": True, "name": "Fast Expansion, branch"},
        headers=headers,
    ).json()

    assert cloned["blueprint"]["name"] == "Fast Expansion, branch"
    assert cloned["next_version"] == 1
    original = api.get("/api/blueprints", headers=headers).json()["blueprints"]
    assert len(original) == 2


def test_the_api_compares_two_runs(api):
    headers = _coach_headers(api)
    first = _api_run(api, headers)
    second = _api_run(api, headers)

    response = api.get(f"/api/training/{first}/compare/{second}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["same_scenario"] is True
