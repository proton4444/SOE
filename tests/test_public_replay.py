"""The leakage test for the public replay file.

`MARKETING_CLOSED_ALPHA.md` requires a test that loads an exported replay and
fails if anything outside the allowlist reaches it. The forbidden list is not
hypothetical: the decision traces beside every recorded match carry `model`,
`provider_request_id`, `raw_reply`, `usage`, and the full order text, and the
turn log carries state hashes and seeds. This test is what stands between that
material and the public page.
"""

from __future__ import annotations

import json

import pytest

from soe import public_replay
from soe.public_replay import LeakageError


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _frame(turn: int, city_a: str, city_b: str, secured: str | None) -> dict:
    return {
        "turn": turn,
        "pieces": [
            {"id": "c1", "seat": "player_1", "city_id": city_a, "kind": "character"},
            {"id": "c2", "seat": "player_2", "city_id": city_b, "kind": "character"},
            {"id": "s1", "seat": "player_1", "city_id": city_a, "kind": "stack"},
        ],
        "cities": [
            {
                "id": "zelothvale",
                "occupied_by": sorted(
                    {"player_1"} if city_a == "zelothvale" else set()
                    | ({"player_2"} if city_b == "zelothvale" else set())
                ),
                "secured_by": secured,
            },
            {"id": "narunon", "occupied_by": [], "secured_by": None},
        ],
    }


@pytest.fixture
def clean() -> dict:
    """A watchable replay: pieces move and territory changes hands."""
    frames = [
        _frame(0, "zelothvale", "narunon", None),
        _frame(1, "narunon", "narunon", "player_1"),
        _frame(2, "zelothvale", "zelothvale", "player_2"),
        _frame(3, "narunon", "zelothvale", "player_1"),
        _frame(4, "zelothvale", "narunon", "player_2"),
    ]
    return public_replay.build(
        map_file="calib_12.json",
        match_id="AR001_ab",
        label="official-gate",
        seats={
            "player_1": "llm:openai/gpt-4o-mini:expansionist-v1",
            "player_2": "scripted:military",
        },
        frames=frames,
        winner_seat="player_1",
        decided_by="secured",
    )


# ---------------------------------------------------------------------------
# the happy path
# ---------------------------------------------------------------------------


def test_clean_replay_passes(clean):
    public_replay.validate(clean)


def test_schema_is_named(clean):
    assert clean["schema"] == "soe.public_replay.v1"


def test_seat_labels_drop_provider_and_model(clean):
    labels = {seat["label"] for seat in clean["seats"]}
    assert labels == {"expansionist-v1", "scripted (military)"}
    assert "openai" not in json.dumps(clean)
    assert "gpt-4o-mini" not in json.dumps(clean)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("llm:openai/gpt-4o-mini:expansionist-v1", "expansionist-v1"),
        ("llm:anthropic/claude-3:consolidation-v1", "consolidation-v1"),
        ("scripted:military", "scripted (military)"),
        ("llm:openai/gpt-4o-mini", "doctrine"),
    ],
)
def test_seat_label_sanitiser(raw, expected):
    assert public_replay.sanitise_seat_label(raw) == expected


def test_exported_file_round_trips(clean, tmp_path):
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(clean), encoding="utf-8")
    assert public_replay.validate_file(path)["match_id"] == "AR001_ab"


# ---------------------------------------------------------------------------
# a key outside the allowlist
# ---------------------------------------------------------------------------


def test_unknown_top_level_key_fails(clean):
    clean["provider"] = "openai"
    with pytest.raises(LeakageError, match="not on the allowlist"):
        public_replay.validate(clean)


def test_unknown_nested_key_fails(clean):
    clean["frames"][0]["pieces"][0]["gold"] = 120
    with pytest.raises(LeakageError, match="not on the allowlist"):
        public_replay.validate(clean)


def test_missing_required_key_fails(clean):
    del clean["result"]
    with pytest.raises(LeakageError, match="required key is missing"):
        public_replay.validate(clean)


@pytest.mark.parametrize(
    "key",
    ["health", "morale", "inventory", "skills", "messages", "password", "seed"],
)
def test_forbidden_piece_fields_fail(clean, key):
    clean["frames"][1]["pieces"][0][key] = 1
    with pytest.raises(LeakageError):
        public_replay.validate(clean)


# ---------------------------------------------------------------------------
# order and report text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "leak",
    [
        "Recruit 10 soldiers in Zelothvale.",
        "ATTACK",
        "--- ORDERS ---",
        "Have Emperor Marcus go to Narunon.",
        "Tax.",
    ],
)
def test_order_text_fails(clean, leak):
    clean["match_id"] = leak
    with pytest.raises(LeakageError):
        public_replay.validate(clean)


def test_multiline_report_fails(clean):
    clean["match_id"] = "TURN 4\nYour scouts report nothing."
    with pytest.raises(LeakageError):
        public_replay.validate(clean)


def test_prose_length_fails(clean):
    clean["match_id"] = "x" * 200
    with pytest.raises(LeakageError, match="prose is not publishable"):
        public_replay.validate(clean)


# ---------------------------------------------------------------------------
# hashes, seeds, keys, paths
# ---------------------------------------------------------------------------


def test_state_hash_fails(clean):
    clean["match_id"] = "ddabceecdba0395f8f4a0b38fb9a5d3245a3888abf46b3ce9b0df7080fbc557b"
    with pytest.raises(LeakageError, match="looks like a hash"):
        public_replay.validate(clean)


def test_seed_integer_fails(clean):
    clean["turns"] = 15953712850728089001
    with pytest.raises(LeakageError, match="seed-sized"):
        public_replay.validate(clean)


def test_small_integers_are_fine(clean):
    clean["turns"] = 30
    public_replay.validate(clean)


@pytest.mark.parametrize(
    "leak",
    ["sk-abc123def456", "Bearer abc123", "api_key=zzz"],
)
def test_api_key_fails(clean, leak):
    clean["match_id"] = leak
    with pytest.raises(LeakageError):
        public_replay.validate(clean)


@pytest.mark.parametrize(
    "leak",
    [
        "games/arena/run-20260813-141002-20e66d",
        "C:\\Antigravity\\SOE\\maps\\calib_12.json",
        "/var/soe/state.json",
        "./decisions/AR000_ab",
    ],
)
def test_filesystem_path_fails(clean, leak):
    clean["match_id"] = leak
    with pytest.raises(LeakageError):
        public_replay.validate(clean)


def test_map_is_a_bare_filename(clean):
    assert "/" not in clean["map"] and "\\" not in clean["map"]


@pytest.mark.parametrize("leak", ["openai", "anthropic", "gpt-4o-mini", "claude-3"])
def test_provider_name_fails(clean, leak):
    clean["match_id"] = leak
    with pytest.raises(LeakageError, match="model provider"):
        public_replay.validate(clean)


# ---------------------------------------------------------------------------
# internal consistency
# ---------------------------------------------------------------------------


def test_undeclared_seat_fails(clean):
    clean["frames"][1]["pieces"][0]["seat"] = "player_9"
    with pytest.raises(LeakageError, match="not a declared seat"):
        public_replay.validate(clean)


def test_undeclared_secured_by_fails(clean):
    clean["frames"][1]["cities"][0]["secured_by"] = "player_9"
    with pytest.raises(LeakageError, match="not a declared seat"):
        public_replay.validate(clean)


def test_unknown_piece_kind_fails(clean):
    clean["frames"][1]["pieces"][0]["kind"] = "elite_unit"
    with pytest.raises(LeakageError, match="kind"):
        public_replay.validate(clean)


def test_bad_label_fails(clean):
    clean["label"] = "official"
    with pytest.raises(LeakageError, match="label"):
        public_replay.validate(clean)


def test_build_rejects_unknown_label():
    with pytest.raises(ValueError, match="label must be one of"):
        public_replay.build(
            map_file="calib_12.json",
            match_id="x",
            label="promo",
            seats={},
            frames=[],
            winner_seat=None,
            decided_by="draw",
        )


# ---------------------------------------------------------------------------
# the visual bar
# ---------------------------------------------------------------------------


def test_visual_bar_scores_movement_and_territory(clean):
    bar = public_replay.visual_bar(clean)
    assert bar["moves"] >= public_replay.MIN_MOVES
    assert bar["territory_changes"] >= public_replay.MIN_TERRITORY_CHANGES
    assert bar["passes"]


def test_static_match_cannot_be_labelled_official_gate():
    """The doctrine bundle's real failure mode: 80 games, nothing to watch.

    Zero attacks and zero eliminations is a behavioural result. Labelling it
    `official-gate` on the poster would promise a war the file cannot show.
    """
    still = [_frame(turn, "zelothvale", "narunon", None) for turn in range(5)]
    replay = public_replay.build(
        map_file="calib_12.json",
        match_id="AR000_ab",
        label="official-gate",
        seats={"player_1": "scripted:balanced", "player_2": "scripted:balanced"},
        frames=still,
        winner_seat=None,
        decided_by="draw",
    )
    assert not public_replay.visual_bar(replay)["passes"]
    with pytest.raises(LeakageError, match="fails the visual bar"):
        public_replay.validate(replay)


def test_static_match_is_fine_as_an_exhibition():
    still = [_frame(turn, "zelothvale", "narunon", None) for turn in range(5)]
    replay = public_replay.build(
        map_file="calib_12.json",
        match_id="EX000",
        label="exhibition",
        seats={"player_1": "scripted:balanced", "player_2": "scripted:balanced"},
        frames=still,
        winner_seat=None,
        decided_by="draw",
    )
    public_replay.validate(replay)


# ---------------------------------------------------------------------------
# the sanitiser against real state
# ---------------------------------------------------------------------------


def test_frame_from_state_drops_everything_but_position():
    """A frame built from a live engine state carries position and nothing else."""
    from soe import models

    state = models.GameState(turn_number=1)
    state.world_map.cities["zelothvale"] = models.City(
        id="zelothvale",
        name="Zelothvale",
        population_band=models.PopulationBand.TINY,
    )
    state.factions["player_1"] = models.Faction(
        id="player_1", name="Aurelia", secured_city_ids={"zelothvale"}
    )
    state.characters["char_player_1_leader"] = models.Character(
        id="char_player_1_leader",
        name="Emperor Marcus",
        faction_id="player_1",
        location_city_id="zelothvale",
        gold=999.0,
        health=42,
        combat_skill=7,
    )
    state.unit_stacks["stack_1"] = models.UnitStack(
        id="stack_1",
        faction_id="player_1",
        location_city_id="zelothvale",
        unit_type=models.UnitType.SOLDIER,
        count=10,
    )

    frame = public_replay.frame_from_state(state, 1, public_replay._PieceRegistry())

    assert {p["kind"] for p in frame["pieces"]} == {"character", "stack"}
    assert all(set(p) == {"id", "seat", "city_id", "kind"} for p in frame["pieces"])
    # The leader's personal name never reaches the file; the id is opaque.
    blob = json.dumps(frame)
    assert "Emperor Marcus" not in blob
    assert "char_player_1_leader" not in blob
    assert "999" not in blob and "42" not in blob
    assert frame["cities"][0]["secured_by"] == "player_1"
    assert frame["cities"][0]["occupied_by"] == ["player_1"]


def test_dead_and_independent_pieces_are_not_shown():
    from soe import models

    state = models.GameState(turn_number=1)
    state.world_map.cities["narunon"] = models.City(
        id="narunon", name="Narunon", population_band=models.PopulationBand.TINY
    )
    state.factions["player_1"] = models.Faction(id="player_1", name="Aurelia")
    state.characters["dead"] = models.Character(
        id="dead",
        name="Fallen",
        faction_id="player_1",
        location_city_id="narunon",
        is_dead=True,
    )
    state.characters["npc"] = models.Character(
        id="npc",
        name="Hermit",
        faction_id="independent",
        location_city_id="narunon",
    )

    frame = public_replay.frame_from_state(state, 1, public_replay._PieceRegistry())
    assert frame["pieces"] == []
    assert frame["cities"][0]["occupied_by"] == []

