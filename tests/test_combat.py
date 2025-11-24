"""
Tests for combat commands
"""

import pytest
from src.soe.models import (
    Character, Location, Order, OrderType,
    ResourceType, SkillType, CharacterType
)
from src.soe.game import GameState
from src.soe.commands import CommandExecutor


@pytest.fixture
def combat_game_state():
    """Create a test game state for combat"""
    state = GameState(game_id="combat-test")

    # Create test location
    arena = Location(name="Arena")
    state.add_location(arena)

    # Create attacker
    attacker = Character(name="Warrior", player_id="player1", location_id=arena.id)
    attacker.set_skill_level(SkillType.COMBAT, 5)
    state.add_character(attacker)

    # Give attacker soldiers
    inv = state.get_character_inventory(attacker.id)
    inv.add(ResourceType.SOLDIER, 10)

    # Create target
    target = Character(name="Enemy", player_id="player2", location_id=arena.id)
    state.add_character(target)

    return state


def test_attack_command(combat_game_state):
    """Test ATTACK command"""
    attacker = combat_game_state.get_character_by_name("Warrior")
    target = combat_game_state.get_character_by_name("Enemy")

    order = Order(
        character_id=attacker.id,
        player_id=attacker.player_id,
        order_type=OrderType.ATTACK,
        parameters={"target_name": target.name}
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    # Target should have taken damage (health < 100) or be dead
    assert target.health < 100 or not target.is_alive


def test_attack_noncombatant_fails(combat_game_state):
    """Test that non-combatants cannot attack"""
    attacker = combat_game_state.get_character_by_name("Warrior")
    target = combat_game_state.get_character_by_name("Enemy")

    # Make attacker non-combatant
    attacker.is_combatant = False

    order = Order(
        character_id=attacker.id,
        player_id=attacker.player_id,
        order_type=OrderType.ATTACK,
        parameters={"target_name": target.name}
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert not result.success
    assert "non-combatant" in result.message


def test_capture_command(combat_game_state):
    """Test CAPTURE command"""
    attacker = combat_game_state.get_character_by_name("Warrior")
    target = combat_game_state.get_character_by_name("Enemy")

    # Weaken target first
    target.health = 20

    order = Order(
        character_id=attacker.id,
        player_id=attacker.player_id,
        order_type=OrderType.CAPTURE,
        parameters={"target_name": target.name}
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    # Capture might succeed or fail based on random chance
    # If successful, target should be prisoner
    if result.success:
        assert target.character_type == CharacterType.PRISONER


def test_capture_healthy_target_fails(combat_game_state):
    """Test that healthy targets cannot be captured"""
    attacker = combat_game_state.get_character_by_name("Warrior")
    target = combat_game_state.get_character_by_name("Enemy")

    # Target at full health
    assert target.health == 100

    order = Order(
        character_id=attacker.id,
        player_id=attacker.player_id,
        order_type=OrderType.CAPTURE,
        parameters={"target_name": target.name}
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert not result.success
    assert "too strong" in result.message.lower()


def test_enslave_command(combat_game_state):
    """Test ENSLAVE command"""
    attacker = combat_game_state.get_character_by_name("Warrior")
    target = combat_game_state.get_character_by_name("Enemy")

    # Make target a prisoner first
    target.character_type = CharacterType.PRISONER

    order = Order(
        character_id=attacker.id,
        player_id=attacker.player_id,
        order_type=OrderType.ENSLAVE,
        parameters={"target_name": target.name}
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert target.character_type == CharacterType.SLAVE
    assert target.player_id == attacker.player_id


def test_kill_command(combat_game_state):
    """Test KILL/EXECUTE command"""
    attacker = combat_game_state.get_character_by_name("Warrior")
    target = combat_game_state.get_character_by_name("Enemy")

    # Target must be prisoner or slave
    target.character_type = CharacterType.PRISONER

    order = Order(
        character_id=attacker.id,
        player_id=attacker.player_id,
        order_type=OrderType.KILL,
        parameters={"target_name": target.name}
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert not target.is_alive
    assert target.health == 0


def test_fortify_command(combat_game_state):
    """Test FORTIFY command"""
    char = combat_game_state.get_character_by_name("Warrior")

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.FORTIFY
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert char.is_fortified


def test_unfortify_command(combat_game_state):
    """Test UNFORTIFY command"""
    char = combat_game_state.get_character_by_name("Warrior")
    char.is_fortified = True

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.UNFORTIFY
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert not char.is_fortified


def test_secure_command(combat_game_state):
    """Test SECURE command"""
    char = combat_game_state.get_character_by_name("Warrior")
    location = combat_game_state.get_location(char.location_id)

    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.SECURE
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert location.owner_id == char.player_id


def test_combatant_noncom_commands(combat_game_state):
    """Test COMBATANT and NONCOM commands"""
    char = combat_game_state.get_character_by_name("Warrior")

    # Set to non-combatant
    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.NONCOM
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert not char.is_combatant

    # Set back to combatant
    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.COMBATANT
    )

    result = executor.execute_order(order)

    assert result.success
    assert char.is_combatant


def test_lurk_unlurk_commands(combat_game_state):
    """Test LURK and UNLURK commands"""
    char = combat_game_state.get_character_by_name("Warrior")

    # Lurk
    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.LURK
    )

    executor = CommandExecutor(combat_game_state)
    result = executor.execute_order(order)

    assert result.success
    assert char.is_lurking

    # Unlurk
    order = Order(
        character_id=char.id,
        player_id=char.player_id,
        order_type=OrderType.UNLURK
    )

    result = executor.execute_order(order)

    assert result.success
    assert not char.is_lurking
