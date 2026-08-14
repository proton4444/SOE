"""
Phase 4: the closed alpha is measurable.

Real invitees close the go criteria. These tests check the instrument: a
20–30 roster, three trainings per version, a funnel anyone can recompute, a
shareable result that is not a ranking, a concrete pay-or-key choice, and
one observable final.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p4_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_p4_games_{uuid.uuid4().hex[:8]}"),
)
os.environ["SOE_LLM_KEY"] = "sk-test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from webapp import alpha as alpha_mod  # noqa: E402
from webapp import blueprints as blueprints_mod  # noqa: E402
from webapp import coaches as coaches_mod  # noqa: E402
from webapp import competition  # noqa: E402
from webapp import training  # noqa: E402
from webapp.ai import brain  # noqa: E402
from webapp.alpha import (  # noqa: E402
    AlphaError,
    AlphaStore,
    funnel,
    load_format,
)
from webapp.blueprints import BlueprintStore  # noqa: E402
from webapp.coaches import CoachStore  # noqa: E402
from webapp.competition import CompetitionStore, Regulation, STATUS_COMPLETE  # noqa: E402
from webapp.main import app  # noqa: E402
from webapp import main as web_main  # noqa: E402
from webapp.training import QuotaExceeded, TrainingStore  # noqa: E402

DOCTRINE = {
    "objective": "Take the nearest unsecured city, then hold it.",
    "economy": "Soldiers first.",
    "risk": "Accept losses to hold a contested town.",
    "diplomacy": "Neutral unless attacked.",
}
OTHER = {
    "objective": "Hold the start city and tax.",
    "economy": "Hoard gold.",
    "risk": "Never trade a stack for a town.",
    "diplomacy": "Neutral unless attacked.",
}
FAKE_USAGE = {
    "prompt_tokens": 300,
    "completion_tokens": 40,
    "total_tokens": 340,
    "cost": 0.0001,
}
REPLY = "thinking\n--- ORDERS ---\nTax.\nWait for 1 day.\n"


@pytest.fixture
def fake_brain(monkeypatch):
    def fake_chat_result(*, model, messages, temperature=0.0, max_tokens=1500, images=()):
        return brain.ChatResult(
            text=REPLY,
            model=model,
            attempts=1,
            latency_ms=20.0,
            usage=dict(FAKE_USAGE),
            provider_request_id="gen-alpha",
        )

    monkeypatch.setattr(brain, "is_configured", lambda: True)
    monkeypatch.setattr(brain, "chat_result", fake_chat_result)
    monkeypatch.setattr(brain, "chat", lambda **kwargs: fake_chat_result(**kwargs).text)


@pytest.fixture
def roster(tmp_path) -> AlphaStore:
    return AlphaStore(tmp_path / "alpha.json")


@pytest.fixture
def coaches(tmp_path) -> CoachStore:
    return CoachStore(tmp_path / "coaches.json")


@pytest.fixture
def blueprints(tmp_path) -> BlueprintStore:
    return BlueprintStore(tmp_path / "blueprints.json")


@pytest.fixture
def train(tmp_path) -> TrainingStore:
    return TrainingStore(tmp_path / "training.json", runs_root=tmp_path / "tr")


@pytest.fixture
def league(tmp_path) -> CompetitionStore:
    return CompetitionStore(tmp_path / "competitions.json", matches_root=tmp_path / "mt")


@pytest.fixture(autouse=True)
def _clean_games():
    from webapp.rooms import GAMES_ROOT

    yield
    if GAMES_ROOT.exists():
        shutil.rmtree(GAMES_ROOT, ignore_errors=True)


def _freeze(blueprints, coach, name, doctrine=None):
    item = blueprints.create(
        coach, name, doctrine=doctrine or DOCTRINE, runtime={"model": "openai/gpt-4o-mini"}
    )
    blueprints.freeze(coach, item.id, 1)
    return blueprints.get(coach, item.id)


def test_the_format_is_three_trainings_and_thirty_invites():
    fmt = load_format()
    assert fmt.training_per_version == 3
    assert fmt.capacity == 30
    assert fmt.minimum_invites == 20
    assert fmt.gates["activation"] == 0.6
    assert fmt.gates["iteration"] == 0.4


def test_the_roster_will_not_issue_a_thirty_first_invite(roster):
    for index in range(30):
        roster.issue(f"Person {index:02d}")
    with pytest.raises(AlphaError, match="full"):
        roster.issue("One more")


def test_an_invitation_is_shown_once_and_hashed(roster, coaches):
    invite, code = roster.issue("Ada")
    assert code.startswith("inv_")
    assert code not in roster.path.read_text(encoding="utf-8")
    assert invite.code_sha256 in roster.path.read_text(encoding="utf-8")
    roster.open()
    coach, _ = coaches.create("Ada")
    roster.claim(code, coach)
    with pytest.raises(AlphaError, match="already"):
        roster.claim(code, coach)


def test_an_invited_coach_gets_three_trainings_per_version(
    roster, coaches, blueprints, train, monkeypatch
):
    monkeypatch.setattr(alpha_mod, "_store", roster)
    roster.open()
    _, code = roster.issue("Ada")
    coach, _ = coaches.create("Ada")
    roster.claim(code, coach)
    item = _freeze(blueprints, coach, "Fast")
    assert train.quota_state(coach, item.id, 1)["version_limit"] == 3
    for _ in range(3):
        train.start(coach, item.id, "sparring", version=1, blueprint_store=blueprints)
    with pytest.raises(QuotaExceeded, match="3"):
        train.start(coach, item.id, "sparring", version=1, blueprint_store=blueprints)


def test_funnel_rates_are_sums_of_the_ledgers(
    roster, coaches, blueprints, train, league
):
    roster.open()
    field = []
    for name in ("Ada", "Bruno", "Cara", "Dewi", "Eve"):
        _, code = roster.issue(name)
        coach, _ = coaches.create(name)
        roster.claim(code, coach)
        field.append(coach)
    for coach in field[:3]:
        _freeze(blueprints, coach, coach.display_name)
    ada, bruno = field[0], field[1]
    run = train.start(
        ada,
        blueprints.owned_by(ada)[0].id,
        "sparring",
        version=1,
        blueprint_store=blueprints,
    )
    train.mark(run, training.STATUS_COMPLETE, finished_at=run.created_at)
    blueprints.new_version(ada, run.blueprint_id, from_version=1)
    roster.record_intent(ada, "pay", source=run.id)
    roster.share(ada, run.id)

    season = league.create_season("Alpha I", regulation=Regulation(model="openai/gpt-4o-mini", turns=1, map="starter_map.json"))
    league.freeze(season.id)
    league.enter(ada, season.id, blueprints.owned_by(ada)[0].id, 1, blueprint_store=blueprints)
    league.enter(bruno, season.id, _freeze(blueprints, bruno, "Bruno B").id, 1, blueprint_store=blueprints)
    other = league.create_season("Alpha II", regulation=Regulation(model="openai/gpt-4o-mini", turns=1, map="starter_map.json"))
    league.freeze(other.id)
    league.enter(ada, other.id, blueprints.owned_by(ada)[0].id, 1, blueprint_store=blueprints)

    report = funnel(
        roster,
        coaches=coaches,
        blueprints=blueprints,
        training=train,
        competition=league,
    )
    assert report["issued"] == 5
    assert report["activated"] == 3
    assert report["rates"]["activation"] == 0.6
    assert report["iterated"] == 1
    assert report["willing"] == 1
    assert report["shared"] == 1
    assert report["returned"] == 1
    assert "rating" not in str(report).lower()
    assert "elo" not in str(report).lower()


def test_the_final_is_one_match_not_a_rating(league, coaches, blueprints):
    ada, _ = coaches.create("Ada")
    bruno, _ = coaches.create("Bruno")
    season = league.create_season(
        "Alpha I",
        regulation=Regulation(model="openai/gpt-4o-mini", turns=1, map="starter_map.json"),
    )
    league.freeze(season.id)
    left = league.enter(ada, season.id, _freeze(blueprints, ada, "Ada").id, 1, blueprint_store=blueprints)
    right = league.enter(
        bruno, season.id, _freeze(blueprints, bruno, "Bruno", doctrine=OTHER).id, 1, blueprint_store=blueprints
    )
    league.pair(season.id)
    match = league.matches(season.id)[0]
    match.status = "complete"
    match.result = {
        "games": 2,
        "left_entry_id": left.id,
        "right_entry_id": right.id,
        "left_wins": 2,
        "right_wins": 0,
        "draws": 0,
        "left_sweeps": 1,
        "right_sweeps": 0,
    }
    job = league.job_for_match(match.id)
    job.status = "complete"
    season.status = STATUS_COMPLETE
    league.save()
    final = league.stage_final(season.id)
    assert final.id != match.id
    assert {final.left_entry_id, final.right_entry_id} == {left.id, right.id}
    assert league.job_for_match(final.id).kind == "final"
    assert league.stage_final(season.id).id == final.id


@pytest.fixture
def desk(monkeypatch, tmp_path, fake_brain):
    monkeypatch.setattr(coaches_mod, "_store", CoachStore(tmp_path / "coaches.json"))
    monkeypatch.setattr(blueprints_mod, "_store", BlueprintStore(tmp_path / "blueprints.json"))
    monkeypatch.setattr(
        training, "_store", TrainingStore(tmp_path / "training.json", runs_root=tmp_path / "runs")
    )
    monkeypatch.setattr(alpha_mod, "_store", AlphaStore(tmp_path / "alpha.json"))
    monkeypatch.setattr(
        competition,
        "_store",
        CompetitionStore(tmp_path / "competitions.json", matches_root=tmp_path / "matches"),
    )
    monkeypatch.setattr(web_main, "OPERATOR_KEY", "test-operator")
    return TestClient(app, headers={web_main.OPERATOR_HEADER: "test-operator"})


def test_invite_register_share_and_intent_are_walkable(desk, fake_brain, monkeypatch):
    from webapp import training as training_mod

    catalogue = {
        key: training_mod.Scenario(
            id=value.id,
            name=value.name,
            description=value.description,
            map="starter_map.json",
            turns=2,
            seed_pairs=1,
            opponent=value.opponent,
            max_spend_usd=value.max_spend_usd,
        )
        for key, value in training_mod.scenarios().items()
    }
    monkeypatch.setattr(training_mod, "_scenarios", catalogue)

    opened = desk.post("/ops/alpha/open", follow_redirects=True)
    assert opened.status_code == 200
    issued = desk.post("/ops/alpha/invites", data={"name": "Ada"}, follow_redirects=True)
    assert issued.status_code == 200, issued.text
    import re

    match = re.search(r"inv_[0-9a-f]+", issued.text)
    assert match, issued.text[:1500]
    code = match.group(0)

    desk.post("/coach/leave")
    gated = desk.get("/coach")
    assert "Invitation" in gated.text
    registered = desk.post(
        "/coach/register", data={"name": "Ada", "invite": code}, follow_redirects=True
    )
    assert registered.status_code == 200
    assert "Your agents" in registered.text

    created = desk.post(
        "/coach/blueprints",
        data={"name": "Fast Expansion", **DOCTRINE, "model": "openai/gpt-4o-mini"},
        follow_redirects=True,
    )
    bp = str(created.url).rstrip("/").split("/")[-1]
    desk.post(f"/coach/blueprints/{bp}/versions/1/freeze", follow_redirects=True)
    run = desk.post(
        "/coach/training",
        data={"blueprint_id": bp, "version": "1", "scenario_id": "sparring"},
        follow_redirects=True,
    )
    assert run.status_code == 200
    assert "I would pay for more training" in run.text
    run_id = str(run.url).rstrip("/").split("/")[-1]
    desk.post("/coach/alpha/intent", data={"kind": "pay", "source": run_id}, follow_redirects=True)
    shared = desk.post(f"/coach/training/{run_id}/share", follow_redirects=True)
    assert shared.status_code == 200
    assert "Not a ranking" in shared.text
    assert "Proposed" not in shared.text
    assert "elo" not in shared.text.lower()
    assert "rating" not in shared.text.lower()

    panel = desk.get("/ops/alpha")
    assert "activation" in panel.text
    assert "pass" in panel.text or "short" in panel.text or "pending" in panel.text
