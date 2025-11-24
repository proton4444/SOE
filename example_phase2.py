#!/usr/bin/env python
"""
Phase 2 Demo: Combat & Advanced Movement for Spoils of Empire
"""

from src.soe.models import Character, Location, ResourceType, CharacterType, SkillType, LocationType
from src.soe.game import GameState, TurnManager
from src.soe.parser import CommandParser


def main():
    print("=" * 70)
    print("Spoils of Empire - Phase 2 Demo: Combat & Advanced Movement")
    print("=" * 70)
    print()

    # Create game state
    game = GameState(game_id="phase2-demo")
    parser = CommandParser()
    turn_manager = TurnManager(game)

    # Create locations
    castle = Location(name="Castle Blackstone", location_type=LocationType.CASTLE)
    battlefield = Location(name="Battlefield")
    port = Location(name="Port City")
    island = Location(name="Mystic Island")

    castle.add_connection(battlefield.id, 50)
    battlefield.add_connection(port.id, 100)

    game.add_location(castle)
    game.add_location(battlefield)
    game.add_location(port)
    game.add_location(island)

    print(f"📍 Created locations: {castle.name}, {battlefield.name}, {port.name}, {island.name}")
    print()

    # Create player 1's champion
    hero = Character(
        name="Marcus",
        title="Lord",
        player_id="player1",
        character_type=CharacterType.LEADER,
        location_id=castle.id
    )
    hero.set_skill_level(SkillType.COMBAT, 7)
    hero.set_skill_level(SkillType.MAGIC, 6)
    game.add_character(hero)

    hero_inv = game.get_character_inventory(hero.id)
    hero_inv.add(ResourceType.GOLD, 5000)
    hero_inv.add(ResourceType.SOLDIER, 100)
    hero_inv.add(ResourceType.SHIP, 1)

    print(f"👤 {hero.full_name} (Player 1)")
    print(f"   Location: {castle.name}")
    print(f"   Combat Skill: {hero.get_skill_level(SkillType.COMBAT)}")
    print(f"   Magic Skill: {hero.get_skill_level(SkillType.MAGIC)}")
    print(f"   Army: {hero_inv.get(ResourceType.SOLDIER)} soldiers")
    print()

    # Create enemy commander
    enemy = Character(
        name="Vargoth",
        title="Warlord",
        player_id="player2",
        character_type=CharacterType.LEADER,
        location_id=battlefield.id
    )
    enemy.set_skill_level(SkillType.COMBAT, 5)
    game.add_character(enemy)

    enemy_inv = game.get_character_inventory(enemy.id)
    enemy_inv.add(ResourceType.SOLDIER, 50)

    print(f"👤 {enemy.full_name} (Player 2 - Enemy)")
    print(f"   Location: {battlefield.name}")
    print(f"   Combat Skill: {enemy.get_skill_level(SkillType.COMBAT)}")
    print(f"   Army: {enemy_inv.get(ResourceType.SOLDIER)} soldiers")
    print()

    # Scenario: Military Campaign
    print("=" * 70)
    print("SCENARIO: MILITARY CAMPAIGN")
    print("=" * 70)
    print()

    commands = [
        # Phase 1: Preparation
        (f"FORTIFY", hero.id, "🛡️  PHASE 1: PREPARATION"),

        # Phase 2: Move to battlefield
        (f"GO TO {battlefield.name}", hero.id, "⚔️  PHASE 2: MARCH TO BATTLE"),

        # Phase 3: Combat
        (f"ATTACK {enemy.full_name}", hero.id, "💥 PHASE 3: ENGAGEMENT"),
        (f"ATTACK {enemy.full_name}", hero.id, None),  # Second attack

        # Phase 4: Capture weakened enemy
        (f"CAPTURE {enemy.full_name}", hero.id, "🔗 PHASE 4: CAPTURE"),

        # Phase 5: Advanced movement - Fly to port
        (f"UNFORTIFY", hero.id, "🚁 PHASE 5: ADVANCED MOVEMENT"),
        (f"FLY TO {port.name}", hero.id, None),

        # Phase 6: Sail to island
        (f"SAIL TO {island.name}", hero.id, "⛵ PHASE 6: NAVAL EXPEDITION"),

        # Phase 7: Secure the island
        (f"SECURE", hero.id, "🏴 PHASE 7: CONQUEST"),

        # Phase 8: Use magic to return
        (f"TELEPORT TO {castle.name}", hero.id, "✨ PHASE 8: MAGICAL RETURN"),
    ]

    for cmd_text, char_id, phase_label in commands:
        if phase_label:
            print()
            print(phase_label)
            print("-" * 70)

        print(f"📝 Command: {cmd_text}")

        # Parse command
        char = game.get_character(char_id)
        parsed = parser.parse(cmd_text, default_character=char.name if char else None)

        if not parsed:
            print("   ❌ Failed to parse command")
            continue

        # Resolve character
        if parsed.character_name:
            char = game.get_character_by_name(parsed.character_name, char.player_id if char else None)

        if not char:
            print(f"   ❌ Character not found")
            continue

        # Create and execute order
        order = parser.create_order(parsed, char.id, char.player_id)
        game.add_order(order)

        result = turn_manager.execute_order(order)
        if result:
            # Refresh character from state
            char = game.get_character(char.id)
            if "attacked" in result.lower():
                enemy_char = game.get_character_by_name("Vargoth")
                if enemy_char:
                    print(f"   ✅ {result}")
                    print(f"   💔 {enemy_char.full_name}'s health: {enemy_char.health}/{enemy_char.max_health} HP")
            elif "captured" in result.lower():
                enemy_char = game.get_character_by_name("Vargoth")
                if enemy_char:
                    print(f"   ✅ {result}")
                    print(f"   ⛓️  {enemy_char.full_name} is now a {enemy_char.character_type.value}")
            else:
                print(f"   ✅ {result}")

    # Show final state
    print()
    print("=" * 70)
    print("CAMPAIGN RESULTS")
    print("=" * 70)
    print()

    hero = game.get_character_by_name("Marcus")
    hero_loc = game.get_location(hero.location_id)
    hero_inv = game.get_character_inventory(hero.id)

    print(f"👤 {hero.full_name}")
    print(f"   Location: {hero_loc.name if hero_loc else 'Unknown'}")
    print(f"   Health: {hero.health}/{hero.max_health} HP")
    print(f"   Status: {'🛡️ Fortified' if hero.is_fortified else 'Normal'}")
    print(f"   Army: {hero_inv.get(ResourceType.SOLDIER)} soldiers")
    print()

    enemy = game.get_character_by_name("Vargoth")
    if enemy:
        enemy_loc = game.get_location(enemy.location_id)
        print(f"👤 {enemy.full_name}")
        print(f"   Status: {enemy.character_type.value.upper()}")
        print(f"   Health: {enemy.health}/{enemy.max_health} HP")
        print(f"   Location: {enemy_loc.name if enemy_loc else 'Unknown'}")
        print(f"   Alive: {'Yes' if enemy.is_alive else 'No'}")
        print()

    island_loc = game.get_location_by_name("Mystic Island")
    if island_loc:
        print(f"🏝️  {island_loc.name}")
        print(f"   Owner: {'Lord Marcus' if island_loc.owner_id == hero.player_id else 'Unclaimed'}")
        print()

    print("=" * 70)
    print("Phase 2 Demo Complete!")
    print()
    print("Commands Demonstrated:")
    print("  ✅ FORTIFY/UNFORTIFY - Defensive positioning")
    print("  ✅ ATTACK - Combat engagement")
    print("  ✅ CAPTURE - Taking prisoners")
    print("  ✅ FLY - Magical flight")
    print("  ✅ SAIL - Naval travel")
    print("  ✅ TELEPORT - Instant magical transport")
    print("  ✅ SECURE - Taking control of locations")
    print("=" * 70)


if __name__ == "__main__":
    main()
