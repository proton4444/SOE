"""
Tests for data models
"""

import pytest
from src.soe.models import (
    Character, CharacterType, SkillType,
    Location, LocationType,
    ResourceType, ResourceInventory,
    Group, Order, OrderType, OrderStatus
)


def test_character_creation():
    """Test creating a character"""
    char = Character(name="John", title="Captain")
    assert char.name == "John"
    assert char.title == "Captain"
    assert char.full_name == "Captain John"
    assert char.is_alive
    assert char.health == 100


def test_character_skills():
    """Test character skill system"""
    char = Character(name="Mage")
    assert char.get_skill_level(SkillType.MAGIC) == 0

    char.set_skill_level(SkillType.MAGIC, 5)
    assert char.get_skill_level(SkillType.MAGIC) == 5


def test_character_damage():
    """Test character taking damage"""
    char = Character(name="Warrior", health=100)
    assert not char.take_damage(50)
    assert char.health == 50
    assert char.is_alive

    assert char.take_damage(60)  # Fatal damage
    assert char.health == 0
    assert not char.is_alive


def test_character_relationships():
    """Test character ally/enemy relationships"""
    char = Character(name="Hero")
    ally_id = "ally-1"
    enemy_id = "enemy-1"

    char.add_ally(ally_id)
    assert ally_id in char.allies
    assert ally_id not in char.enemies

    char.add_enemy(enemy_id)
    assert enemy_id in char.enemies
    assert enemy_id not in char.allies

    # Making an ally into an enemy should remove from allies
    char.add_enemy(ally_id)
    assert ally_id not in char.allies
    assert ally_id in char.enemies


def test_location_creation():
    """Test creating a location"""
    loc = Location(name="Riverton", location_type=LocationType.CITY)
    assert loc.name == "Riverton"
    assert loc.location_type == LocationType.CITY
    assert len(loc.character_ids) == 0


def test_location_connections():
    """Test location connections"""
    loc1 = Location(name="City A")
    loc2 = Location(name="City B")

    loc1.add_connection(loc2.id, 100)
    assert loc1.is_connected_to(loc2.id)
    assert loc1.get_distance_to(loc2.id) == 100


def test_resource_inventory():
    """Test resource inventory management"""
    inv = ResourceInventory()

    # Initial state
    assert inv.get(ResourceType.GOLD) == 0

    # Add resources
    inv.add(ResourceType.GOLD, 100)
    assert inv.get(ResourceType.GOLD) == 100

    # Remove resources
    assert inv.remove(ResourceType.GOLD, 30)
    assert inv.get(ResourceType.GOLD) == 70

    # Can't remove more than available
    assert not inv.remove(ResourceType.GOLD, 100)
    assert inv.get(ResourceType.GOLD) == 70


def test_resource_transfer():
    """Test transferring resources between inventories"""
    inv1 = ResourceInventory()
    inv2 = ResourceInventory()

    inv1.add(ResourceType.GOLD, 100)

    # Transfer from inv1 to inv2
    assert inv1.transfer_to(inv2, ResourceType.GOLD, 40)
    assert inv1.get(ResourceType.GOLD) == 60
    assert inv2.get(ResourceType.GOLD) == 40

    # Can't transfer more than available
    assert not inv1.transfer_to(inv2, ResourceType.GOLD, 100)
    assert inv1.get(ResourceType.GOLD) == 60


def test_group_management():
    """Test group management"""
    group = Group(name="Alpha Squad")

    char1_id = "char-1"
    char2_id = "char-2"

    # Add members
    group.add_member(char1_id)
    group.add_member(char2_id)
    assert group.get_member_count() == 2

    # Set leader
    assert group.set_leader(char1_id)
    assert group.is_leader(char1_id)
    assert not group.is_leader(char2_id)

    # Remove member
    group.remove_member(char2_id)
    assert group.get_member_count() == 1


def test_order_lifecycle():
    """Test order status transitions"""
    order = Order(
        character_id="char-1",
        player_id="player-1",
        order_type=OrderType.GO
    )

    assert order.status == OrderStatus.PENDING

    order.mark_in_progress(1)
    assert order.status == OrderStatus.IN_PROGRESS
    assert order.execution_turn == 1

    order.mark_completed(2, success=True, message="Arrived")
    assert order.status == OrderStatus.COMPLETED
    assert order.success
    assert order.result_message == "Arrived"


def test_order_parameters():
    """Test order parameter management"""
    order = Order(
        character_id="char-1",
        player_id="player-1",
        order_type=OrderType.GIVE
    )

    order.set_parameter("quantity", 100)
    order.set_parameter("resource_type", "gold")

    assert order.get_parameter("quantity") == 100
    assert order.get_parameter("resource_type") == "gold"
    assert order.get_parameter("nonexistent") is None
    assert order.get_parameter("nonexistent", "default") == "default"
