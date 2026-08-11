"""
Tests for upkeep and salary system.
"""

import pytest
from soe import models, engine, config


@pytest.fixture
def test_game_state():
    """Create a test game state with two factions."""
    game_state = models.GameState()

    # Create cities
    city1 = models.City(
        id="city1",
        name="City One",
        population_band=models.PopulationBand.MEDIUM
    )
    game_state.world_map.cities["city1"] = city1

    # Create faction
    faction1 = models.Faction(
        id="player1",
        name="Faction One",
        treasury=1000,
        controlled_city_ids={"city1"}
    )
    game_state.factions["player1"] = faction1

    # Create character
    char1 = models.Character(
        id="char1",
        name="Hero One",
        faction_id="player1",
        location_city_id="city1",
        combat_skill=10,
        magic_skill=5
    )
    game_state.characters["char1"] = char1

    return game_state


def test_upkeep_system(test_game_state):
    """Test that upkeep is deducted from treasury."""
    # Add some units
    stack = models.UnitStack(
        id="stack1",
        faction_id="player1",
        location_city_id="city1",
        unit_type=models.UnitType.SOLDIER,
        count=100  # 100 soldiers at 0.1g each = 10g upkeep
    )
    test_game_state.unit_stacks["stack1"] = stack

    initial_treasury = test_game_state.factions["player1"].treasury

    # Run turn with no orders
    updated_state, turn_log = engine.run_turn(test_game_state, {}, seed=42)

    # Check upkeep was deducted. Income goes to the city's tax pool, so it does
    # not offset upkeep until someone collects it with a TAX order.
    faction = updated_state.factions["player1"]
    expected_income = config.get_income_for_city(models.PopulationBand.MEDIUM)  # city1 income
    expected_upkeep = 100 * config.UPKEEP_PER_UNIT[models.UnitType.SOLDIER]  # 100 soldiers

    expected_treasury = initial_treasury - expected_upkeep
    assert abs(faction.treasury - expected_treasury) < 0.5  # Allow small rounding diff
    assert updated_state.tax_pools["city1"] == expected_income

    # Check upkeep event was logged
    events = turn_log.get_player_events("player1")
    upkeep_events = [e for e in events if e.event_type == "upkeep"]
    assert len(upkeep_events) > 0


def test_negative_treasury_warning(test_game_state):
    """Unpaid upkeep becomes wage debt and is reported."""
    # Set low funds and add expensive units
    test_game_state.factions["player1"].treasury = 5
    test_game_state.factions["player1"].controlled_city_ids = set()  # No income

    # Add many soldiers (high upkeep)
    stack = models.UnitStack(
        id="stack1",
        faction_id="player1",
        location_city_id="city1",
        unit_type=models.UnitType.SOLDIER,
        count=1000  # 1000 * 0.1 = 100g upkeep
    )
    test_game_state.unit_stacks["stack1"] = stack

    # Run turn
    updated_state, turn_log = engine.run_turn(test_game_state, {}, seed=42)

    # Available gold is spent; shortfall becomes wage debt
    faction = updated_state.factions["player1"]
    assert faction.treasury == 0
    assert faction.wage_debt > 0

    # Should have debt warning
    events = turn_log.get_player_events("player1")
    debt_events = [e for e in events if e.event_type == "debt"]
    assert len(debt_events) > 0
    assert not debt_events[0].success  # Marked as unsuccessful


