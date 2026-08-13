"""Phase 0 arena scoring contracts."""

from scripts.arena import GameResult, TIEBREAK, decide_winner, summarise


def metrics(**overrides):
    values = {
        "secured": 1,
        "controlled": 1,
        "soldiers": 10,
        "characters_alive": 1,
        "gold": 100,
    }
    values.update(overrides)
    return values


def test_tiebreak_prioritises_position_and_force_over_gold():
    assert TIEBREAK == (
        "secured", "controlled", "soldiers", "characters_alive", "gold",
    )
    result = decide_winner({
        "territory": metrics(controlled=2, gold=0),
        "hoarder": metrics(controlled=1, gold=100_000),
    })
    assert result == "territory"


def test_eliminated_faction_cannot_win():
    result = decide_winner({
        "dead": metrics(secured=10, controlled=10, soldiers=500,
                        characters_alive=0, gold=100_000),
        "alive": metrics(secured=0, controlled=0, soldiers=0,
                         characters_alive=1, gold=0),
    })
    assert result == "alive"


def test_mutual_elimination_is_a_draw():
    result = decide_winner({
        "dead_a": metrics(characters_alive=0),
        "dead_b": metrics(characters_alive=0),
    })
    assert result is None


def test_summary_attributes_an_elimination_to_elimination(tmp_path):
    game_metrics = {
        "dead": metrics(secured=5, characters_alive=0),
        "alive": metrics(secured=0, characters_alive=1),
    }
    result = GameResult(
        code="test", map_file="map.json", turns_played=1,
        seats={"dead": "random", "alive": "scripted:balanced"},
        metrics=game_metrics, winner=decide_winner(game_metrics),
    )

    summary = summarise(
        ["scripted:balanced", "random"], [result], [], 1, "map.json",
        tmp_path,
    )

    assert summary["decided_by"] == {"elimination": 1}
