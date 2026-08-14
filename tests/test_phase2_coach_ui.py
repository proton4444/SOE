"""
Phase 2 remainder: a new user finishes a training from the coach desk.

The API already closes create → try → understand → change. These tests walk
the same loop through the HTML, because the exit criterion is that nobody
needs an operator or curl. They also check that victory, the main error and
the match cost are on the debrief as named things, and that the opponent's
orders stay off it.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p2ui_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p2ui_games_{uuid.uuid4().hex[:8]}"),
)
os.environ["SOE_LLM_KEY"] = "sk-test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from webapp import blueprints as blueprints_mod  # noqa: E402
from webapp import coaches as coaches_mod  # noqa: E402
from webapp import coach_ui, debrief, training  # noqa: E402
from webapp.ai import brain  # noqa: E402
from webapp.blueprints import BlueprintStore  # noqa: E402
from webapp.coaches import CoachStore  # noqa: E402
from webapp.main import app  # noqa: E402
from webapp.training import TrainingStore  # noqa: E402

DOCTRINE = {
    "objective": "Take the nearest unsecured city, then hold it.",
    "economy": "Soldiers first.",
    "risk": "Accept losses to hold a contested town.",
    "diplomacy": "Neutral unless attacked.",
}
FAKE_USAGE = {
    "prompt_tokens": 300,
    "completion_tokens": 40,
    "total_tokens": 340,
    "cost": 0.0001,
}
REPLY = (
    "Private thinking that must never be persisted.\n"
    "--- ORDERS ---\n"
    "Tax.\n"
    "Monitor the movements of the Shadow Syndicate.\n"
    "Wait for 1 day.\n"
)
_KEY_RE = re.compile(r"coach_[0-9a-f]+")


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


@pytest.fixture
def desk(monkeypatch, tmp_path, fake_brain, fast_scenario):
    monkeypatch.setattr(coaches_mod, "_store", CoachStore(tmp_path / "coaches.json"))
    monkeypatch.setattr(blueprints_mod, "_store", BlueprintStore(tmp_path / "blueprints.json"))
    monkeypatch.setattr(
        training, "_store", TrainingStore(tmp_path / "training.json", runs_root=tmp_path / "runs")
    )
    return TestClient(app)


def _last_id(response) -> str:
    return str(response.url).rstrip("/").split("/")[-1].split("?")[0]


def _form(doctrine=None, **extra) -> dict:
    body = {
        "name": "Fast Expansion",
        "persona": "A coach's first agent.",
        **DOCTRINE,
        "model": "openai/gpt-4o-mini",
    }
    if doctrine:
        body.update(doctrine)
    body.update(extra)
    return body


# ======================================================================
# presentation of the three things a new user must read
# ======================================================================


def test_outcome_line_names_a_sweep():
    assert coach_ui.outcome_line({"games": 2, "won": 2, "lost": 0, "drawn": 0}) == (
        "Won every game"
    )
    assert coach_ui.outcome_kind({"games": 2, "won": 0, "lost": 2, "drawn": 0}) == "lost"


def test_main_error_puts_strategy_ahead_of_syntax():
    error = coach_ui.main_error(
        {
            "strategic": {"silent_turns": 1, "idle_turns": 2, "note": "idle"},
            "syntax": {"discarded_lines": 9, "examples": ["Bad."]},
            "provider": {"total": 3},
        }
    )
    assert error["kind"] == "strategic"
    assert "silent" in error["summary"]


def test_cost_line_shows_dollars_and_calls():
    assert "$0.0012" in coach_ui.cost_line({"usd": 0.0012, "calls": 12})
    assert "12" in coach_ui.cost_line({"usd": 0.0012, "calls": 12})


# ======================================================================
# the desk is the front door
# ======================================================================


def test_the_gate_is_the_front_door(desk):
    page = desk.get("/coach")
    assert page.status_code == 200
    assert "Register" in page.text
    assert "Create a coach account" in page.text


def test_an_unsigned_browser_is_sent_to_the_gate(desk):
    response = desk.get("/coach/blueprints/bp_missing", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/coach"


def test_the_home_page_links_to_the_desk(desk):
    page = desk.get("/")
    assert 'href="/coach"' in page.text


# ======================================================================
# the loop a new user walks
# ======================================================================


def test_a_new_user_completes_a_training_unassisted(desk):
    """Register, write, freeze, run, read, iterate — no API, no operator."""
    gate = desk.get("/coach")
    assert "Create a coach account" in gate.text

    registered = desk.post("/coach/register", data={"name": "Ada"}, follow_redirects=True)
    assert registered.status_code == 200
    assert str(registered.url).rstrip("/").endswith("/coach")
    assert "Your agents" in registered.text
    match = _KEY_RE.search(registered.text)
    assert match, "the key must be shown once, on the page that created it"
    key = match.group(0)
    assert desk.cookies.get("soe_coach") == key

    again = desk.get("/coach")
    assert key not in again.text
    assert "Your agents" in again.text

    created = desk.post("/coach/blueprints", data=_form(), follow_redirects=True)
    assert created.status_code == 200
    assert "Fast Expansion" in created.text
    assert "draft" in created.text
    blueprint_id = _last_id(created)
    assert blueprint_id.startswith("bp_")
    listed = desk.get("/coach")
    assert "Fast Expansion" in listed.text
    assert "v1" in listed.text

    frozen = desk.post(
        f"/coach/blueprints/{blueprint_id}/versions/1/freeze", follow_redirects=True
    )
    assert frozen.status_code == 200
    assert "frozen" in frozen.text
    assert "Start training" in frozen.text
    assert "Sparring partner" in frozen.text

    run_page = desk.post(
        "/coach/training",
        data={
            "blueprint_id": blueprint_id,
            "version": 1,
            "scenario_id": "sparring",
        },
        follow_redirects=True,
    )
    assert run_page.status_code == 200, run_page.text
    run_id = _last_id(run_page)
    assert run_id.startswith("tr_")
    html = run_page.text
    assert "Result" in html
    assert "Main error" in html
    assert "Match cost" in html
    assert "$" in html
    assert any(word in html for word in ("Won", "Lost", "Drawn"))
    assert "Open the next version" in html

    coach = coaches_mod.default_store().require(key)
    run = training.default_store().get(coach, run_id)
    assert run.status == training.STATUS_COMPLETE, run.error
    view = debrief.build(run)
    for game in view.games:
        opponent = "player_2" if game.seat == "player_1" else "player_1"
        theirs = {
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
        leaked = theirs - mine
        assert leaked, "the opponent issued nothing distinctive to test"
        for line in leaked:
            assert line not in html

    opened = desk.post(f"/coach/training/{run_id}/iterate", follow_redirects=True)
    assert opened.status_code == 200
    assert "draft" in opened.text
    assert "v=2" in str(opened.url) or "Version 2" in opened.text

    desk.post(
        f"/coach/blueprints/{blueprint_id}",
        data=_form(
            doctrine=dict(DOCTRINE, risk="Never trade a stack for a town."),
            version=2,
        ),
        follow_redirects=True,
    )
    desk.post(
        f"/coach/blueprints/{blueprint_id}/versions/2/freeze", follow_redirects=True
    )
    again_run = desk.post(
        "/coach/training",
        data={
            "blueprint_id": blueprint_id,
            "version": 2,
            "scenario_id": "sparring",
        },
        follow_redirects=False,
    )
    assert again_run.status_code == 303
    second_id = again_run.headers["location"].rstrip("/").split("/")[-1]
    first_hash = desk.get(f"/api/training/{run_id}").json()["content_hash"]
    second_hash = desk.get(f"/api/training/{second_id}").json()["content_hash"]
    assert first_hash
    assert first_hash != second_hash


def test_another_coach_cannot_open_this_desk_item(desk):
    desk.post("/coach/register", data={"name": "Ada"})
    created = desk.post("/coach/blueprints", data=_form(), follow_redirects=True)
    blueprint_id = _last_id(created)

    desk.post("/coach/leave")
    desk.post("/coach/register", data={"name": "Bruno"})
    response = desk.get(f"/coach/blueprints/{blueprint_id}")
    assert response.status_code == 404


def test_a_queued_run_polls_instead_of_inventing_a_debrief(desk):
    registered = desk.post("/coach/register", data={"name": "Ada"}, follow_redirects=True)
    key = _KEY_RE.search(registered.text).group(0)
    coach = coaches_mod.default_store().require(key)
    blueprint = blueprints_mod.default_store().create(coach, "Queued", doctrine=DOCTRINE)
    blueprints_mod.default_store().freeze(coach, blueprint.id, 1)
    run = training.default_store().start(coach, blueprint.id, "sparring")

    page = desk.get(f"/coach/training/{run.id}")
    assert page.status_code == 200
    assert "queued" in page.text
    assert "Main error" not in page.text
    assert 'hx-get="/coach/training/' in page.text

    panel = desk.get(f"/coach/training/{run.id}/panel")
    assert panel.status_code == 200
    assert "Waiting for the match record" in panel.text
