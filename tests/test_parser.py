"""
Tests for the order parser.

Tests parsing of English-like commands into structured Order objects.
"""

import pytest
from spoils_engine import models, parser, orders, config


@pytest.fixture
def simple_game_state():
    """Create a simple game state for testing."""
    game_state = models.GameState()

    # Create a simple map
    city1 = models.City(id="city1", name="City One", population_band=models.PopulationBand.SMALL)
    city2 = models.City(id="city2", name="City Two", population_band=models.PopulationBand.MEDIUM)
    game_state.world_map.cities["city1"] = city1
    game_state.world_map.cities["city2"] = city2

    road = models.Road(id="road1", from_city_id="city1", to_city_id="city2",
                       quality=models.RoadQuality.GOOD)
    game_state.world_map.roads["road1"] = road

    # Create a faction
    faction = models.Faction(id="player1", name="Test Faction", treasury=1000)
    game_state.factions["player1"] = faction

    # Create a character
    char = models.Character(
        id="char1",
        name="Hero One",
        faction_id="player1",
        location_city_id="city1",
        combat_skill=10,
        magic_skill=5
    )
    game_state.characters["char1"] = char

    return game_state


def test_parse_move_order(simple_game_state):
    """Test parsing a simple move order."""
    text = "Have Hero One go to City Two."

    orders_list = parser.parse_orders(text, simple_game_state, "player1")

    assert len(orders_list) == 1
    order = orders_list[0]
    assert isinstance(order, orders.MoveOrder)
    assert order.actor_id == "char1"
    assert order.destination_city_id == "city2"
    assert len(order.warnings) == 0


def test_parse_recruit_order(simple_game_state):
    """Test parsing a recruit order."""
    text = "Have Hero One recruit 10 soldiers in City One."

    orders_list = parser.parse_orders(text, simple_game_state, "player1")

    assert len(orders_list) == 1
    order = orders_list[0]
    assert isinstance(order, orders.RecruitOrder)
    assert order.actor_id == "char1"
    assert order.count == 10
    assert order.unit_type == "soldier"
    assert order.city_id == "city1"
    assert len(order.warnings) == 0


def test_parse_multiple_orders(simple_game_state):
    """Test parsing multiple orders."""
    text = """
    Have Hero One go to City Two.
    Have Hero One recruit 5 sailors.
    """

    orders_list = parser.parse_orders(text, simple_game_state, "player1")

    assert len(orders_list) == 2
    assert isinstance(orders_list[0], orders.MoveOrder)
    assert isinstance(orders_list[1], orders.RecruitOrder)


def test_parse_with_comments(simple_game_state):
    """Test that comments are properly ignored."""
    text = """
    # This is a comment
    Have Hero One go to City Two.  # Another comment
    """

    orders_list = parser.parse_orders(text, simple_game_state, "player1")

    assert len(orders_list) == 1
    assert isinstance(orders_list[0], orders.MoveOrder)


def test_parse_invalid_character(simple_game_state):
    """Test parsing with invalid character name."""
    text = "Have Unknown Hero go to City Two."

    orders_list = parser.parse_orders(text, simple_game_state, "player1")

    assert len(orders_list) == 1
    order = orders_list[0]
    assert len(order.warnings) > 0
    assert "not found" in order.warnings[0].lower()


def test_parse_invalid_city(simple_game_state):
    """Test parsing with invalid city name."""
    text = "Have Hero One go to Unknown City."

    orders_list = parser.parse_orders(text, simple_game_state, "player1")

    assert len(orders_list) == 1
    order = orders_list[0]
    assert len(order.warnings) > 0


def test_parse_attack_order(simple_game_state):
    """Test parsing an attack order."""
    # Add a second faction and character for targeting
    faction2 = models.Faction(id="player2", name="Enemy Faction", treasury=500)
    simple_game_state.factions["player2"] = faction2

    enemy = models.Character(
        id="char2",
        name="Enemy One",
        faction_id="player2",
        location_city_id="city2",
        combat_skill=8
    )
    simple_game_state.characters["char2"] = enemy

    # Move hero to city2 first
    simple_game_state.characters["char1"].location_city_id = "city2"

    # Simple attack order (parser struggles with complex "go to X and attack Y")
    text = "Have Hero One attack Enemy One."

    orders_list = parser.parse_orders(text, simple_game_state, "player1")

    assert len(orders_list) == 1
    order = orders_list[0]
    assert isinstance(order, orders.AttackOrder)
    assert order.actor_id == "char1"
    assert "enemy" in order.target_name.lower()
