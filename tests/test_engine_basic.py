"""
Tests for the turn processing engine.

Tests basic turn phases: movement, recruitment, combat, etc.
"""

import pytest
import copy
from spoils_engine import models, engine, orders, config


@pytest.fixture
def test_game_state():
    """Create a test game state with two factions."""
    game_state = models.GameState()

    # Create cities
    city1 = models.City(
        id="city1",
        name="City One",
        population_band=models.PopulationBand.MEDIUM,
        is_port=True
    )
    city2 = models.City(
        id="city2",
        name="City Two",
        population_band=models.PopulationBand.SMALL,
        is_port=True  # ships can only dock at ports
    )
    game_state.world_map.cities["city1"] = city1
    game_state.world_map.cities["city2"] = city2

    # Create road
    road = models.Road(
        id="road1",
        from_city_id="city1",
        to_city_id="city2",
        quality=models.RoadQuality.GOOD
    )
    game_state.world_map.roads["road1"] = road

    # Create two factions
    faction1 = models.Faction(
        id="player1",
        name="Faction One",
        treasury=1000,
        controlled_city_ids={"city1"}
    )
    faction2 = models.Faction(
        id="player2",
        name="Faction Two",
        treasury=1000,
        controlled_city_ids={"city2"}
    )
    game_state.factions["player1"] = faction1
    game_state.factions["player2"] = faction2

    # Create characters
    char1 = models.Character(
        id="char1",
        name="Hero One",
        faction_id="player1",
        location_city_id="city1",
        combat_skill=15,
        magic_skill=5,
        movement_points=10
    )
    char2 = models.Character(
        id="char2",
        name="Hero Two",
        faction_id="player2",
        location_city_id="city2",
        combat_skill=10,
        movement_points=10
    )
    game_state.characters["char1"] = char1
    game_state.characters["char2"] = char2

    return game_state


def test_movement_phase(test_game_state):
    """Test that characters can move between cities."""
    # Create move order
    move_order = orders.MoveOrder(
        player_id="player1",
        actor_id="char1",
        destination_city_id="city2"
    )

    orders_by_player = {
        "player1": [move_order],
        "player2": []
    }

    # Run turn
    updated_state, turn_log = engine.run_turn(test_game_state, orders_by_player, seed=42)

    # Check that character moved
    char = updated_state.characters["char1"]
    assert char.location_city_id == "city2"

    # Movement points reset at end of turn, but check logs for movement
    events = turn_log.get_player_events("player1")
    move_events = [e for e in events if e.event_type == "move"]
    assert len(move_events) > 0  # Movement occurred


def test_recruit_phase(test_game_state):
    """Test that factions can recruit units."""
    # Create recruit order
    recruit_order = orders.RecruitOrder(
        player_id="player1",
        actor_id="char1",
        city_id="city1",
        unit_type="soldier",
        count=10
    )

    orders_by_player = {
        "player1": [recruit_order],
        "player2": []
    }

    initial_treasury = test_game_state.factions["player1"].treasury

    # Run turn
    updated_state, turn_log = engine.run_turn(test_game_state, orders_by_player, seed=42)

    # Check that units were created
    player1_stacks = [s for s in updated_state.unit_stacks.values() if s.faction_id == "player1"]
    assert len(player1_stacks) > 0
    total_soldiers = sum(s.count for s in player1_stacks if s.unit_type == models.UnitType.SOLDIER)
    assert total_soldiers == 10

    # Check that gold was deducted (recruitment + upkeep). City income does not
    # reach the treasury automatically -- it waits in the tax pool for a TAX order.
    faction = updated_state.factions["player1"]
    cost = config.get_recruit_cost(models.UnitType.SOLDIER) * 10
    upkeep = config.UPKEEP_PER_UNIT[models.UnitType.SOLDIER] * 10  # 10 soldiers upkeep
    expected = initial_treasury - cost - upkeep
    assert abs(faction.treasury - expected) < 0.5  # Allow small rounding difference


def test_buy_ship_phase(test_game_state):
    """Test that factions can buy ships at ports."""
    # Create buy ship order
    buy_order = orders.BuyShipOrder(
        player_id="player1",
        actor_id="char1",
        city_id="city1",
        ship_type="galley",
        count=1
    )

    orders_by_player = {
        "player1": [buy_order],
        "player2": []
    }

    # Run turn
    updated_state, turn_log = engine.run_turn(test_game_state, orders_by_player, seed=42)

    # Check that ship was created
    player1_ships = [s for s in updated_state.ships.values() if s.faction_id == "player1"]
    assert len(player1_ships) == 1
    assert player1_ships[0].ship_type == models.ShipType.GALLEY


def test_combat_phase(test_game_state):
    """Test basic combat resolution."""
    # Add units to both factions
    stack1 = models.UnitStack(
        id="stack1",
        faction_id="player1",
        location_city_id="city2",
        unit_type=models.UnitType.SOLDIER,
        count=50
    )
    stack2 = models.UnitStack(
        id="stack2",
        faction_id="player2",
        location_city_id="city2",
        unit_type=models.UnitType.SOLDIER,
        count=30
    )
    test_game_state.unit_stacks["stack1"] = stack1
    test_game_state.unit_stacks["stack2"] = stack2

    # Move char1 to city2 first
    test_game_state.characters["char1"].location_city_id = "city2"

    # Create attack order
    attack_order = orders.AttackOrder(
        player_id="player1",
        actor_id="char1",
        location_city_id="city2",
        target_faction_id="player2",
        target_name="Hero Two"
    )

    orders_by_player = {
        "player1": [attack_order],
        "player2": []
    }

    # Run turn
    updated_state, turn_log = engine.run_turn(test_game_state, orders_by_player, seed=42)

    # Check that casualties occurred
    total_units_after = sum(s.count for s in updated_state.unit_stacks.values())
    assert total_units_after < 80  # Some casualties should have occurred


def test_income_phase(test_game_state):
    """Income accrues to a city's tax pool, not straight to the treasury."""
    initial_treasury = test_game_state.factions["player1"].treasury

    # Run turn with no orders
    updated_state, turn_log = engine.run_turn(test_game_state, {}, seed=42)

    expected_income = config.get_income_for_city(models.PopulationBand.MEDIUM)

    # The gold waits in the city until a character collects it with TAX
    assert updated_state.tax_pools["city1"] == expected_income

    # ...and is not also handed to the treasury, which would pay it out twice
    faction = updated_state.factions["player1"]
    assert faction.treasury == initial_treasury


def test_income_is_not_double_counted(test_game_state):
    """A turn's income either stays in the pool or moves to the treasury, never both."""
    treasury_before = test_game_state.factions["player1"].treasury
    assert test_game_state.tax_pools.get("city1", 0) == 0

    # Station soldiers so the TAX order can be carried out
    test_game_state.unit_stacks["stack_tax"] = models.UnitStack(
        id="stack_tax",
        faction_id="player1",
        location_city_id="city1",
        unit_type=models.UnitType.SOLDIER,
        count=40,
    )
    tax_order = orders.TaxOrder(player_id="player1", actor_id="char1",
                                city_id="city1", duration_days=7)

    updated_state, _ = engine.run_turn(test_game_state, {"player1": [tax_order]}, seed=42)

    income = config.get_income_for_city(models.PopulationBand.MEDIUM)
    upkeep = 40 * config.UPKEEP_PER_UNIT[models.UnitType.SOLDIER]

    # Whatever is no longer in the pool is what the TAX order collected
    collected = income - updated_state.tax_pools["city1"]
    assert collected > 0

    # Treasury gains exactly that, less upkeep. Before the fix the treasury also
    # received the full income automatically, paying the same gold out twice.
    assert abs(updated_state.factions["player1"].treasury
               - (treasury_before + collected - upkeep)) < 0.5


def test_deterministic_execution(test_game_state):
    """Test that same seed produces same results."""
    # Create some orders
    recruit_order = orders.RecruitOrder(
        player_id="player1",
        actor_id="char1",
        city_id="city1",
        unit_type="soldier",
        count=20
    )

    orders_by_player = {
        "player1": [recruit_order],
        "player2": []
    }

    # Run twice with same seed (use deepcopy to avoid mutation)
    state1, log1 = engine.run_turn(copy.deepcopy(test_game_state), orders_by_player, seed=12345)
    state2, log2 = engine.run_turn(copy.deepcopy(test_game_state), orders_by_player, seed=12345)

    # Results should be identical
    assert state1.factions["player1"].treasury == state2.factions["player1"].treasury
    assert len(state1.unit_stacks) == len(state2.unit_stacks)


def test_turn_increment(test_game_state):
    """Test that turn number increments."""
    initial_turn = test_game_state.turn_number

    updated_state, turn_log = engine.run_turn(test_game_state, {}, seed=42)

    assert updated_state.turn_number == initial_turn + 1


def test_sail_phase(test_game_state):
    """Test that factions can sail ships."""
    # Setup: Create sea lane between cities
    sea_lane = models.Road(
        id="sea1",
        from_city_id="city1",
        to_city_id="city2",
        quality=models.RoadQuality.SEA
    )
    test_game_state.world_map.roads["sea1"] = sea_lane

    # Make city1 a port
    test_game_state.world_map.cities["city1"].is_port = True

    # Add a ship at city1
    ship = models.Ship(
        id="ship1",
        faction_id="player1",
        location_city_id="city1",
        ship_type=models.ShipType.GALLEY
    )
    test_game_state.ships["ship1"] = ship

    # Add sailors (need at least 10)
    sailors = models.UnitStack(
        id="sailors1",
        faction_id="player1",
        location_city_id="city1",
        unit_type=models.UnitType.SAILOR,
        count=50  # 10 required + 40 rowers = optimal
    )
    test_game_state.unit_stacks["sailors1"] = sailors

    # Create sail order
    sail_order = orders.SailOrder(
        player_id="player1",
        actor_id="char1",
        destination_city_id="city2"
    )

    orders_by_player = {
        "player1": [sail_order],
        "player2": []
    }

    # Run turn
    updated_state, turn_log = engine.run_turn(test_game_state, orders_by_player, seed=42)

    # Check that ship moved
    ship_after = updated_state.ships["ship1"]
    assert ship_after.location_city_id == "city2"

    # Check that captain moved
    char = updated_state.characters["char1"]
    assert char.location_city_id == "city2"

    # Check that sailors moved with the ship
    sailors_after = updated_state.unit_stacks["sailors1"]
    assert sailors_after.location_city_id == "city2"

    # Check sail event was logged
    events = turn_log.get_player_events("player1")
    sail_events = [e for e in events if e.event_type == "sail"]
    assert len(sail_events) > 0
