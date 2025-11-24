"""
Tests for advanced movement commands
"""

import pytest
from src.soe.models import (
    Character, Location, Order, OrderType,
    ResourceType, SkillType
)
from src.soe.game import GameState
from src.soe.commands import CommandExecutor


@pytest.fixture
def movement_game_state():
    """Create a test game state for movement"""
    state = GameState(game_id="movement-test")

    # Create test locations
    start = Location(name="Start City")
    dest = Location(name="Destination City")
    magic_free = Location(name="Magic Free Zone", is_magic_free_zone=True)

    state.add_location(start)
    state.add_location(dest)
    state.add_location(magic_free)

    # Create test character with magic skills
    mage = Character(name="Mage", player_id="player1", location_id=start.id)
    mage.set_skill_level(SkillType.MAGIC, 6)
    state.add_character(mage)

    # Create sailor with ship
    sailor = Character(name="Sailor", player_id="player1", location_id=start.id)
    state.add_character(sailor)
    inv = state.get_character_inventory(sailor.id)
    inv.add(ResourceType.SHIP, 1)

    return state


def test_fly_command(movement_game_state):
    """Test FLY command"""
    mage = movement_game_state.get_character_by_name("Mage")
    dest = movement_game_state.get_location_by_name("Destination City")

    order = Order(
        character_id=mage.id,
        player_id=mage.player_id,
        order_type=OrderType.FLY,
        parameters={"destination": dest.name}
    )

    executor = CommandExecutor(movement_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert mage.location_id == dest.id
    assert "flew" in result.message.lower()


def test_fly_requires_magic_skill(movement_game_state):
    """Test that FLY requires magic skill"""
    # Create character without magic skill
    char = Character(name="Warrior", player_id="player1")
    char.location_id = movement_game_state.locations[list(movement_game_state.locations.keys())[0]].id
    movement_game_state.add_character(char)

    dest = movement_game_state.get_location_by_name("Destination City")

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.FLY,
        parameters={"destination": dest.name}
    )

    executor = CommandExecutor(movement_game_state)
    result = executor.execute_order(order)

    assert not result.success
    assert "magic skill" in result.message.lower()


def test_sail_command(movement_game_state):
    """Test SAIL command"""
    sailor = movement_game_state.get_character_by_name("Sailor")
    dest = movement_game_state.get_location_by_name("Destination City")

    order = Order(
        character_id=sailor.id,
        player_id=sailor.player_id,
        order_type=OrderType.SAIL,
        parameters={"destination": dest.name}
    )

    executor = CommandExecutor(movement_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert sailor.location_id == dest.id
    assert "sailed" in result.message.lower()


def test_sail_requires_ship(movement_game_state):
    """Test that SAIL requires a ship"""
    # Create character without ship
    char = Character(name="Landlubber", player_id="player1")
    char.location_id = movement_game_state.locations[list(movement_game_state.locations.keys())[0]].id
    movement_game_state.add_character(char)

    dest = movement_game_state.get_location_by_name("Destination City")

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.SAIL,
        parameters={"destination": dest.name}
    )

    executor = CommandExecutor(movement_game_state)
    result = executor.execute_order(order)

    assert not result.success
    assert "ship" in result.message.lower()


def test_teleport_command(movement_game_state):
    """Test TELEPORT command"""
    mage = movement_game_state.get_character_by_name("Mage")
    dest = movement_game_state.get_location_by_name("Destination City")

    order = Order(
        character_id=mage.id,
        player_id=mage.player_id,
        order_type=OrderType.TELEPORT,
        parameters={"destination": dest.name}
    )

    executor = CommandExecutor(movement_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert mage.location_id == dest.id
    assert "teleported" in result.message.lower()


def test_teleport_requires_high_magic_skill(movement_game_state):
    """Test that TELEPORT requires high magic skill"""
    # Create character with low magic skill
    char = Character(name="Apprentice", player_id="player1")
    char.set_skill_level(SkillType.MAGIC, 3)
    char.location_id = movement_game_state.locations[list(movement_game_state.locations.keys())[0]].id
    movement_game_state.add_character(char)

    dest = movement_game_state.get_location_by_name("Destination City")

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.TELEPORT,
        parameters={"destination": dest.name}
    )

    executor = CommandExecutor(movement_game_state)
    result = executor.execute_order(order)

    assert not result.success
    assert "magic skill level 5+" in result.message


def test_teleport_magic_free_zone_fails(movement_game_state):
    """Test that TELEPORT fails to magic-free zones"""
    mage = movement_game_state.get_character_by_name("Mage")
    magic_free = movement_game_state.get_location_by_name("Magic Free Zone")

    order = Order(
        character_id=mage.id,
        player_id=mage.player_id,
        order_type=OrderType.TELEPORT,
        parameters={"destination": magic_free.name}
    )

    executor = CommandExecutor(movement_game_state)
    result = executor.execute_order(order)

    assert not result.success
    assert "magic-free zone" in result.message.lower()
