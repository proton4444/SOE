"""
Tests for command execution
"""

import pytest
from src.soe.models import (
    Character, Location, Order, OrderType, OrderStatus,
    ResourceType
)
from src.soe.game import GameState
from src.soe.commands import CommandExecutor


@pytest.fixture
def game_state():
    """Create a test game state"""
    state = GameState(game_id="test")

    # Create test locations
    loc1 = Location(name="Starting City")
    loc2 = Location(name="Destination City")
    loc1.add_connection(loc2.id, 100)

    state.add_location(loc1)
    state.add_location(loc2)

    # Create test character
    char = Character(name="Hero", player_id="player1", location_id=loc1.id)
    state.add_character(char)

    # Give character some resources
    inv = state.get_character_inventory(char.id)
    inv.add(ResourceType.GOLD, 1000)
    inv.add(ResourceType.SOLDIER, 50)

    return state


def test_name_command(game_state):
    """Test NAME command execution"""
    char = list(game_state.characters.values())[0]

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.NAME,
        parameters={"new_name": "Champion", "title": "Sir"}
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(order)

    assert result.success
    assert char.name == "Champion"
    assert char.title == "Sir"
    assert char.full_name == "Sir Champion"


def test_promote_command(game_state):
    """Test PROMOTE command execution"""
    char = list(game_state.characters.values())[0]
    char.title = "Captain"

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.PROMOTE,
        parameters={"new_title": "General"}
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(order)

    assert result.success
    assert char.title == "General"


def test_go_command(game_state):
    """Test GO command execution"""
    char = list(game_state.characters.values())[0]
    destination = list(game_state.locations.values())[1]

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.GO,
        parameters={"destination": destination.name}
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(order)

    assert result.success
    assert char.location_id == destination.id


def test_halt_command(game_state):
    """Test HALT command execution"""
    char = list(game_state.characters.values())[0]

    # Queue some pending orders
    order1 = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.GO,
        parameters={"destination": "Somewhere"}
    )
    order2 = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.GO,
        parameters={"destination": "Elsewhere"}
    )

    game_state.add_order(order1)
    game_state.add_order(order2)

    # Execute HALT
    halt_order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.HALT
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(halt_order)

    assert result.success
    assert order1.status == OrderStatus.CANCELLED
    assert order2.status == OrderStatus.CANCELLED


def test_assign_command(game_state):
    """Test ASSIGN command execution"""
    char = list(game_state.characters.values())[0]

    # Create a second character
    subordinate = Character(name="Soldier", player_id=char.player_id)
    game_state.add_character(subordinate)

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.ASSIGN,
        parameters={
            "resource_type": "soldier",
            "quantity": 10,
            "target_name": subordinate.name
        }
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(order)

    assert result.success

    char_inv = game_state.get_character_inventory(char.id)
    sub_inv = game_state.get_character_inventory(subordinate.id)

    assert char_inv.get(ResourceType.SOLDIER) == 40
    assert sub_inv.get(ResourceType.SOLDIER) == 10


def test_give_command(game_state):
    """Test GIVE command execution"""
    char = list(game_state.characters.values())[0]
    loc = game_state.get_location(char.location_id)

    # Create another character at same location
    other = Character(name="Friend", player_id="player2", location_id=loc.id)
    game_state.add_character(other)

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.GIVE,
        parameters={
            "resource_type": "gold",
            "quantity": 100,
            "target_name": other.name
        }
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(order)

    assert result.success

    char_inv = game_state.get_character_inventory(char.id)
    other_inv = game_state.get_character_inventory(other.id)

    assert char_inv.get(ResourceType.GOLD) == 900
    assert other_inv.get(ResourceType.GOLD) == 100


def test_get_command(game_state):
    """Test GET command execution"""
    char = list(game_state.characters.values())[0]
    loc = game_state.get_location(char.location_id)

    # Add resources to location
    loc_inv = game_state.get_location_inventory(loc.id)
    loc_inv.add(ResourceType.GOLD, 500)

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.GET,
        parameters={
            "resource_type": "gold",
            "quantity": 200
        }
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(order)

    assert result.success

    char_inv = game_state.get_character_inventory(char.id)
    assert char_inv.get(ResourceType.GOLD) == 1200
    assert loc_inv.get(ResourceType.GOLD) == 300


def test_command_validation_failure(game_state):
    """Test that invalid commands fail validation"""
    char = list(game_state.characters.values())[0]

    # Try to give more gold than character has
    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.GIVE,
        parameters={
            "resource_type": "gold",
            "quantity": 10000,  # More than character has
            "target_name": "Someone"
        }
    )

    executor = CommandExecutor(game_state)
    result = executor.execute_order(order)

    assert not result.success
    assert "Insufficient" in result.message
