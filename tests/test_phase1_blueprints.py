"""
Phase 1 — the agent as an owned, versioned object.

One test per exit criterion in ``docs/ROADMAP.md``:

* a coach can create, edit, clone and freeze a blueprint;
* a frozen version cannot be altered;
* two versions of the same agent stay distinguishable and recoverable;
* no coach can read or write another coach's private blueprints;
* the runtime plays exactly the hash the match inscribed;
* migration and authorisation are covered.

The store is file-backed, so every test points ``SOE_DATA_DIR`` at a temp
directory and starts from an empty registry.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_bp_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_bp_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp import blueprints, coaches  # noqa: E402
from webapp.ai import registry as ai_registry  # noqa: E402
from webapp.blueprints import (  # noqa: E402
    BlueprintAccessError,
    BlueprintError,
    BlueprintIntegrityError,
    BlueprintRef,
    BlueprintStore,
)
from webapp.coaches import CoachStore  # noqa: E402
from webapp.main import app  # noqa: E402

client = TestClient(app)

DOCTRINE = {
    "objective": "Take the nearest unsecured city, then hold it.",
    "economy": "Soldiers first; gold sitting idle is territory forfeited.",
    "risk": "Accept losses to hold a contested town.",
    "diplomacy": "Neutral unless attacked.",
}


@pytest.fixture
def store(tmp_path) -> BlueprintStore:
    return BlueprintStore(tmp_path / "blueprints.json")


@pytest.fixture
def coach_store(tmp_path) -> CoachStore:
    return CoachStore(tmp_path / "coaches.json")


@pytest.fixture
def ada(coach_store):
    coach, key = coach_store.create("Ada")
    coach.key = key  # type: ignore[attr-defined]  - convenience for the test
    return coach


@pytest.fixture
def bruno(coach_store):
    coach, key = coach_store.create("Bruno")
    coach.key = key  # type: ignore[attr-defined]
    return coach


# ======================================================================
# create, edit, clone, freeze
# ======================================================================


def test_a_coach_creates_edits_and_freezes_a_blueprint(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE, persona="Blunt.")

    assert blueprint.coach_id == ada.id
    assert blueprint.latest().version == 1
    assert blueprint.latest().state == blueprints.STATE_DRAFT
    assert blueprint.latest().content_hash == ""

    store.edit(ada, blueprint.id, 1, persona="Terse and blunt.")
    assert store.get(ada, blueprint.id).version(1).persona == "Terse and blunt."

    frozen = store.freeze(ada, blueprint.id, 1)
    assert frozen.state == blueprints.STATE_FROZEN
    assert len(frozen.content_hash) == 64
    assert frozen.frozen_at


def test_freezing_twice_returns_the_same_hash(store, ada):
    """A retried freeze must not re-seal a version under a new hash."""
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    first = store.freeze(ada, blueprint.id, 1)
    second = store.freeze(ada, blueprint.id, 1)
    assert second.content_hash == first.content_hash
    assert second.frozen_at == first.frozen_at


def test_a_clone_is_owned_by_the_cloner_and_starts_as_a_private_draft(store, ada, bruno):
    source = store.create(
        ada, "Fast Expansion", doctrine=DOCTRINE, visibility=blueprints.VISIBILITY_PUBLIC
    )
    store.freeze(ada, source.id, 1)

    clone = store.clone(bruno, source.id, name="Fast Expansion, my way")

    assert clone.coach_id == bruno.id
    assert clone.id != source.id
    assert clone.visibility == blueprints.VISIBILITY_PRIVATE
    assert clone.latest().state == blueprints.STATE_DRAFT
    assert clone.latest().doctrine == store.get(ada, source.id).version(1).doctrine
    # Cloning someone's public agent does not republish it under a new owner.
    assert store.get(ada, source.id).visibility == blueprints.VISIBILITY_PUBLIC


def test_a_clone_hashes_differently_from_its_source(store, ada):
    """Identical text under a different id is a different agent."""
    source = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    store.freeze(ada, source.id, 1)
    clone = store.clone(ada, source.id, name="Fast Expansion copy")
    frozen_clone = store.freeze(ada, clone.id, 1)

    assert frozen_clone.content_hash != store.get(ada, source.id).version(1).content_hash


# ======================================================================
# a frozen version cannot be altered
# ======================================================================


@pytest.mark.parametrize(
    "change",
    [
        {"persona": "Something else"},
        {"doctrine": dict(DOCTRINE, objective="Turtle instead.")},
        {"runtime": {"model": "openai/gpt-4o", "temperature": 1.0}},
    ],
)
def test_a_frozen_version_cannot_be_altered(store, ada, change):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    frozen = store.freeze(ada, blueprint.id, 1)

    with pytest.raises(BlueprintError, match="frozen"):
        store.edit(ada, blueprint.id, 1, **change)

    assert store.get(ada, blueprint.id).version(1).content_hash == frozen.content_hash


def test_editorial_fields_stay_editable_after_freezing(store, ada):
    """Renaming a blueprint must not invalidate a match already played."""
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    frozen = store.freeze(ada, blueprint.id, 1)

    store.edit(ada, blueprint.id, 1, name="Fast Expansion (2026)", notes="Held the gate.")

    reread = store.get(ada, blueprint.id)
    assert reread.name == "Fast Expansion (2026)"
    assert reread.version(1).notes == "Held the gate."
    assert reread.version(1).content_hash == frozen.content_hash


# ======================================================================
# two versions stay distinguishable and recoverable
# ======================================================================


def test_two_versions_of_one_agent_stay_distinguishable_and_recoverable(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    v1 = store.freeze(ada, blueprint.id, 1)

    store.new_version(ada, blueprint.id)
    store.edit(
        ada,
        blueprint.id,
        2,
        doctrine=dict(DOCTRINE, risk="Never trade a stack for a town."),
    )
    v2 = store.freeze(ada, blueprint.id, 2)

    reread = store.get(ada, blueprint.id)
    assert [v.version for v in reread.versions] == [1, 2]
    assert v1.content_hash != v2.content_hash
    # Version 1 is still exactly what it was, not shadowed by the newer one.
    assert reread.version(1).doctrine["risk"] == DOCTRINE["risk"]
    assert reread.version(2).doctrine["risk"] == "Never trade a stack for a town."
    assert reread.latest_frozen().version == 2


def test_a_new_version_cannot_be_opened_over_an_open_draft(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    with pytest.raises(BlueprintError, match="still a draft"):
        store.new_version(ada, blueprint.id)


def test_versions_survive_a_reload_from_disk(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    store.freeze(ada, blueprint.id, 1)
    store.new_version(ada, blueprint.id)
    store.edit(ada, blueprint.id, 2, persona="Louder.")
    store.freeze(ada, blueprint.id, 2)

    reloaded = BlueprintStore(store.path)
    reread = reloaded.get(ada, blueprint.id)
    assert [v.version for v in reread.versions] == [1, 2]
    assert reread.version(2).persona == "Louder."
    assert reread.version(2).content_hash == store.get(ada, blueprint.id).version(2).content_hash


# ======================================================================
# authorisation
# ======================================================================


def test_a_coach_cannot_read_another_coachs_private_blueprint(store, ada, bruno):
    private = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)

    with pytest.raises(BlueprintAccessError):
        store.get(bruno, private.id)
    assert private.id not in [b.id for b in store.visible_to(bruno)]


def test_a_coach_cannot_edit_freeze_retire_or_enter_another_coachs_blueprint(
    store, ada, bruno
):
    private = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    store.freeze(ada, private.id, 1)

    for call in (
        lambda: store.edit(bruno, private.id, 1, notes="mine now"),
        lambda: store.freeze(bruno, private.id, 1),
        lambda: store.new_version(bruno, private.id),
        lambda: store.retire(bruno, private.id),
        lambda: store.clone(bruno, private.id),
        lambda: store.enroll(bruno, private.id),
    ):
        with pytest.raises(BlueprintAccessError):
            call()


def test_a_public_blueprint_is_readable_but_not_writable_by_another_coach(
    store, ada, bruno
):
    public = store.create(
        ada, "Fast Expansion", doctrine=DOCTRINE, visibility=blueprints.VISIBILITY_PUBLIC
    )
    store.freeze(ada, public.id, 1)

    assert store.get(bruno, public.id).id == public.id
    with pytest.raises(BlueprintAccessError, match="another coach"):
        store.edit(bruno, public.id, 1, notes="mine now")


def test_owned_by_lists_only_this_coachs_blueprints(store, ada, bruno):
    mine = store.create(ada, "Mine", doctrine=DOCTRINE)
    store.create(
        bruno, "Theirs", doctrine=DOCTRINE, visibility=blueprints.VISIBILITY_PUBLIC
    )
    assert [b.id for b in store.owned_by(ada)] == [mine.id]
    assert len(store.visible_to(ada)) == 2


# ======================================================================
# enrolling a version in a match
# ======================================================================


def test_only_a_frozen_version_can_be_entered(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    with pytest.raises(BlueprintError, match="no frozen version"):
        store.enroll(ada, blueprint.id)
    with pytest.raises(BlueprintError, match="draft"):
        store.enroll(ada, blueprint.id, 1)

    frozen = store.freeze(ada, blueprint.id, 1)
    ref = store.enroll(ada, blueprint.id)
    assert ref == BlueprintRef(blueprint.id, 1, frozen.content_hash)


def test_an_entry_carries_the_reference_not_the_text(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE, persona="Blunt.")
    store.freeze(ada, blueprint.id, 1)
    ref = store.enroll(ada, blueprint.id)

    serialised = str(ref.as_dict())
    assert "Blunt." not in serialised
    assert DOCTRINE["objective"] not in serialised


def test_a_retired_blueprint_cannot_be_entered_but_stays_resolvable(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    store.freeze(ada, blueprint.id, 1)
    ref = store.enroll(ada, blueprint.id)

    store.retire(ada, blueprint.id)

    with pytest.raises(BlueprintError, match="retired"):
        store.enroll(ada, blueprint.id)
    # A league's played matches stay readable.
    assert store.resolve(ref).version == 1


def test_the_runtime_refuses_a_version_that_moved_under_it(store, ada):
    """The hash is recomputed, so an edit made straight in the file is caught."""
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    store.freeze(ada, blueprint.id, 1)
    ref = store.enroll(ada, blueprint.id)

    # Not reachable through the API — this is the tamper case.
    blueprint.version(1).doctrine["objective"] = "Turtle instead."

    with pytest.raises(BlueprintIntegrityError, match="no longer matches"):
        store.resolve(ref)


def test_the_runtime_refuses_a_reference_whose_blueprint_is_gone(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    frozen = store.freeze(ada, blueprint.id, 1)
    ref = BlueprintRef(blueprint.id, 1, frozen.content_hash)
    store._blueprints.pop(blueprint.id)

    with pytest.raises(BlueprintIntegrityError, match="is gone"):
        store.resolve(ref)


def test_resolving_returns_the_entered_version_not_the_latest(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    store.freeze(ada, blueprint.id, 1)
    ref = store.enroll(ada, blueprint.id, 1)

    store.new_version(ada, blueprint.id)
    store.edit(ada, blueprint.id, 2, doctrine=dict(DOCTRINE, objective="Turtle."))
    store.freeze(ada, blueprint.id, 2)

    assert store.resolve(ref).doctrine["objective"] == DOCTRINE["objective"]


# ======================================================================
# hashing and the prompt-facing shape
# ======================================================================


def test_editorial_changes_do_not_move_the_hash(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE, notes="v1")
    before = blueprints.content_hash(blueprint.id, blueprint.version(1))
    store.edit(ada, blueprint.id, 1, name="Renamed", notes="different note")
    after = blueprints.content_hash(blueprint.id, blueprint.version(1))
    assert before == after


@pytest.mark.parametrize("section", DOCTRINE)
def test_every_strategic_section_moves_the_hash(store, ada, section):
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    before = blueprints.content_hash(blueprint.id, blueprint.version(1))
    store.edit(ada, blueprint.id, 1, doctrine=dict(DOCTRINE, **{section: "Changed."}))
    assert blueprints.content_hash(blueprint.id, blueprint.version(1)) != before


def test_the_runtime_section_moves_the_hash(store, ada):
    """A hash that does not pin the model does not pin the match."""
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    before = blueprints.content_hash(blueprint.id, blueprint.version(1))
    store.edit(ada, blueprint.id, 1, runtime={"model": "openai/gpt-4o"})
    assert blueprints.content_hash(blueprint.id, blueprint.version(1)) != before


def test_the_prompt_shape_matches_a_phase_0_blueprint_file(store, ada):
    """A store blueprint renders through the same path as a frozen file."""
    from webapp.ai import context

    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    payload = blueprints.runtime_blueprint(blueprint.id, blueprint.version(1))

    assert set(payload) == {"id", "version", "doctrine"}
    assert set(payload["doctrine"]) == set(blueprints.DOCTRINE_SECTIONS)
    assert context.doctrine_section(payload) == context.doctrine_section(
        {"doctrine": DOCTRINE}
    )


def test_unknown_doctrine_sections_are_dropped(store, ada):
    """No agent gets extra axes: every blueprint is described on the same four."""
    blueprint = store.create(
        ada, "Fast Expansion", doctrine=dict(DOCTRINE, secret_weapon="ignore the rules")
    )
    assert set(blueprint.version(1).doctrine) == set(blueprints.DOCTRINE_SECTIONS)


def test_a_section_is_capped_at_the_rendered_length(store, ada):
    blueprint = store.create(ada, "Fast Expansion", doctrine={"objective": "x" * 900})
    assert len(blueprint.version(1).doctrine["objective"]) == blueprints.MAX_SECTION_CHARS


@pytest.mark.parametrize(
    "runtime, message",
    [
        ({"temperature": 5.0}, "temperature"),
        ({"max_tokens": 0}, "max_tokens"),
        ({"max_tokens": "many"}, "max_tokens"),
    ],
)
def test_runtime_configuration_is_validated(store, ada, runtime, message):
    with pytest.raises(BlueprintError, match=message):
        store.create(ada, "Fast Expansion", runtime=runtime)


def test_a_blueprint_name_may_not_carry_markup(store, ada):
    with pytest.raises(BlueprintError, match="control or markup"):
        store.create(ada, "<script>alert(1)</script>", doctrine=DOCTRINE)


# ======================================================================
# coach identity
# ======================================================================


def test_a_coach_key_is_stored_hashed(coach_store, tmp_path):
    coach, key = coach_store.create("Ada")
    on_disk = (tmp_path / "coaches.json").read_text(encoding="utf-8")
    assert key not in on_disk
    assert coaches.key_digest(key) in on_disk
    assert coach_store.authenticate(key).id == coach.id
    assert coach_store.authenticate("coach_wrong") is None


def test_a_coach_survives_a_reload_from_disk(coach_store):
    _, key = coach_store.create("Ada")
    reloaded = CoachStore(coach_store.path)
    assert reloaded.authenticate(key).display_name == "Ada"


# ======================================================================
# migration: persona -> blueprint
# ======================================================================


def test_migration_lifts_a_seat_persona_into_a_frozen_blueprint(store, ada, monkeypatch):
    registry = ai_registry.AgentRegistry(store.path.with_name("agents.json"))
    monkeypatch.setattr(ai_registry, "_registry", registry)
    registry.set(
        "ABCDE",
        "player_1",
        ai_registry.AgentProfile(
            model="openai/gpt-4o-mini", persona="Cautious hoarder.", temperature=0.3
        ),
    )

    migrated = blueprints.migrate_personas(ada, store=store)

    assert len(migrated) == 1
    profile = registry.get("ABCDE", "player_1")
    assert profile.blueprint_id == migrated[0]["blueprint_id"]
    assert profile.blueprint_version == 1
    assert profile.blueprint_hash == migrated[0]["content_hash"]
    # The persona now lives in the blueprint, and only there.
    assert profile.persona == ""
    version = store.get(ada, profile.blueprint_id).version(1)
    assert version.state == blueprints.STATE_FROZEN
    assert version.persona == "Cautious hoarder."
    assert version.runtime["model"] == "openai/gpt-4o-mini"
    assert version.runtime["temperature"] == 0.3


def test_migration_is_idempotent_and_leaves_untouched_seats_alone(
    store, ada, monkeypatch
):
    registry = ai_registry.AgentRegistry(store.path.with_name("agents2.json"))
    monkeypatch.setattr(ai_registry, "_registry", registry)
    registry.set("ABCDE", "player_1", ai_registry.AgentProfile(persona="Cautious."))
    registry.set("ABCDE", "player_2", ai_registry.AgentProfile(persona=""))

    first = blueprints.migrate_personas(ada, store=store)
    second = blueprints.migrate_personas(ada, store=store)

    assert len(first) == 1
    assert second == []
    assert registry.get("ABCDE", "player_2").blueprint_id == ""
    assert len(store.owned_by(ada)) == 1


# ======================================================================
# the seat plays the hash it entered
# ======================================================================


def test_a_seat_with_no_blueprint_plays_its_own_persona(store, monkeypatch):
    from webapp.ai import orchestrator

    profile = ai_registry.AgentProfile(
        model="openai/gpt-4o-mini", persona="Cautious.", temperature=0.4
    )
    strategy = orchestrator._enrolled_strategy(profile)

    assert strategy.blueprint is None
    assert strategy.persona == "Cautious."
    assert strategy.model == "openai/gpt-4o-mini"
    assert strategy.temperature == 0.4


def test_a_seat_plays_the_blueprint_it_entered(store, ada, monkeypatch):
    from webapp.ai import orchestrator

    monkeypatch.setattr(blueprints, "_store", store)
    blueprint = store.create(
        ada,
        "Fast Expansion",
        doctrine=DOCTRINE,
        persona="Blunt.",
        runtime={"model": "openai/gpt-4o", "temperature": 0.7},
    )
    frozen = store.freeze(ada, blueprint.id, 1)
    profile = ai_registry.AgentProfile(model="openai/gpt-4o-mini", temperature=0.0)
    profile.blueprint_id = blueprint.id
    profile.blueprint_version = 1
    profile.blueprint_hash = frozen.content_hash

    strategy = orchestrator._enrolled_strategy(profile)

    assert strategy.blueprint["doctrine"] == DOCTRINE
    assert strategy.persona == "Blunt."
    # The blueprint's runtime wins over the seat's own settings.
    assert strategy.model == "openai/gpt-4o"
    assert strategy.temperature == 0.7


def test_a_seat_whose_blueprint_moved_refuses_to_play(store, ada, monkeypatch):
    from webapp.ai import orchestrator

    monkeypatch.setattr(blueprints, "_store", store)
    blueprint = store.create(ada, "Fast Expansion", doctrine=DOCTRINE)
    frozen = store.freeze(ada, blueprint.id, 1)
    profile = ai_registry.AgentProfile()
    profile.blueprint_id = blueprint.id
    profile.blueprint_version = 1
    profile.blueprint_hash = frozen.content_hash

    blueprint.version(1).doctrine["objective"] = "Turtle instead."

    with pytest.raises(orchestrator.BotError, match="no longer matches"):
        orchestrator._enrolled_strategy(profile)


# ======================================================================
# the HTTP surface a coach actually uses
# ======================================================================


@pytest.fixture
def api(monkeypatch, tmp_path):
    """A clean coach + blueprint store behind the running app."""
    monkeypatch.setattr(
        coaches, "_store", CoachStore(tmp_path / "api_coaches.json")
    )
    monkeypatch.setattr(
        blueprints, "_store", BlueprintStore(tmp_path / "api_blueprints.json")
    )
    monkeypatch.setenv("SOE_BETA_ACCESS_CODE", "")
    yield client


def _new_coach(api, name: str) -> str:
    response = api.post("/api/coaches", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["coach_key"]


def test_the_api_walks_a_coach_from_draft_to_frozen(api):
    key = _new_coach(api, "Ada")
    headers = {"X-Coach-Key": key}

    created = api.post(
        "/api/blueprints",
        json={"name": "Fast Expansion", "doctrine": DOCTRINE, "persona": "Blunt."},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    blueprint_id = created.json()["id"]

    edited = api.patch(
        f"/api/blueprints/{blueprint_id}/versions/1",
        json={"persona": "Terse."},
        headers=headers,
    )
    assert edited.json()["versions"][0]["persona"] == "Terse."

    frozen = api.post(
        f"/api/blueprints/{blueprint_id}/versions/1/freeze", headers=headers
    )
    assert frozen.status_code == 200
    assert frozen.json()["state"] == "frozen"
    assert len(frozen.json()["content_hash"]) == 64

    refused = api.patch(
        f"/api/blueprints/{blueprint_id}/versions/1",
        json={"persona": "Changed my mind."},
        headers=headers,
    )
    assert refused.status_code == 400
    assert "frozen" in refused.json()["detail"]

    opened = api.post(f"/api/blueprints/{blueprint_id}/versions", headers=headers)
    assert [v["version"] for v in opened.json()["versions"]] == [1, 2]


def test_the_api_hides_another_coachs_private_blueprint(api):
    ada = {"X-Coach-Key": _new_coach(api, "Ada")}
    bruno = {"X-Coach-Key": _new_coach(api, "Bruno")}

    blueprint_id = api.post(
        "/api/blueprints", json={"name": "Private", "doctrine": DOCTRINE}, headers=ada
    ).json()["id"]

    # 404, not 403: a 403 would confirm the id exists.
    assert api.get(f"/api/blueprints/{blueprint_id}", headers=bruno).status_code == 404
    assert (
        api.patch(
            f"/api/blueprints/{blueprint_id}/versions/1",
            json={"notes": "mine"},
            headers=bruno,
        ).status_code
        == 404
    )
    assert api.get("/api/blueprints", headers=bruno).json()["blueprints"] == []


def test_the_api_rejects_a_missing_or_unknown_coach_key(api):
    unauthenticated = api.get("/api/blueprints")
    assert unauthenticated.status_code == 401

    wrong = api.get("/api/blueprints", headers={"X-Coach-Key": "coach_nope"})
    assert wrong.status_code == 403


def test_a_coach_clones_a_public_blueprint_over_the_api(api):
    ada = {"X-Coach-Key": _new_coach(api, "Ada")}
    bruno_key = _new_coach(api, "Bruno")
    bruno = {"X-Coach-Key": bruno_key}

    blueprint_id = api.post(
        "/api/blueprints",
        json={"name": "Open Book", "doctrine": DOCTRINE, "visibility": "public"},
        headers=ada,
    ).json()["id"]
    api.post(f"/api/blueprints/{blueprint_id}/versions/1/freeze", headers=ada)

    clone = api.post(
        f"/api/blueprints/{blueprint_id}/clone",
        json={"name": "Open Book, my way"},
        headers=bruno,
    )
    assert clone.status_code == 200, clone.text
    body = clone.json()
    assert body["mine"] is True
    assert body["visibility"] == "private"
    assert body["versions"][0]["doctrine"] == DOCTRINE
