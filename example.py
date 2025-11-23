#!/usr/bin/env python
"""
Example demonstration of Spoils of Empire Phase 1 implementation
"""

from src.soe.models import Character, Location, ResourceType, CharacterType
from src.soe.game import GameState, TurnManager
from src.soe.parser import CommandParser


def main():
    print("=" * 60)
    print("Spoils of Empire - Phase 1 Demo")
    print("=" * 60)
    print()

    # Create game state
    game = GameState(game_id="demo-game")
    parser = CommandParser()
    turn_manager = TurnManager(game)

    # Create locations
    capital = Location(name="Capital City")
    riverton = Location(name="Riverton")
    capital.add_connection(riverton.id, 100)
    game.add_location(capital)
    game.add_location(riverton)

    print(f"📍 Created locations: {capital.name}, {riverton.name}")
    print()

    # Create a player character
    hero = Character(
        name="Marcus",
        title="Captain",
        player_id="player1",
        character_type=CharacterType.LEADER,
        location_id=capital.id
    )
    game.add_character(hero)

    # Give the hero some resources
    hero_inv = game.get_character_inventory(hero.id)
    hero_inv.add(ResourceType.GOLD, 1000)
    hero_inv.add(ResourceType.SOLDIER, 50)
    hero_inv.add(ResourceType.HORSE, 10)

    print(f"👤 Created character: {hero.full_name}")
    print(f"   Location: {capital.name}")
    print(f"   Resources:")
    print(f"     - Gold: {hero_inv.get(ResourceType.GOLD)}")
    print(f"     - Soldiers: {hero_inv.get(ResourceType.SOLDIER)}")
    print(f"     - Horses: {hero_inv.get(ResourceType.HORSE)}")
    print()

    # Create a subordinate
    lieutenant = Character(
        name="Julia",
        title="Lieutenant",
        player_id="player1",
        location_id=capital.id
    )
    game.add_character(lieutenant)
    print(f"👤 Created character: {lieutenant.full_name}")
    print()

    # Parse and execute commands
    print("=" * 60)
    print("Executing Commands")
    print("=" * 60)
    print()

    commands = [
        ("PROMOTE Marcus TO General", hero.id),
        ("ASSIGN 20 soldiers TO Lieutenant Julia", hero.id),
        ("ASSIGN 5 horses TO Lieutenant Julia", hero.id),
        ("HAVE Lieutenant Julia GO TO Riverton", None),
        ("GIVE 200 gold TO Lieutenant Julia", hero.id),
    ]

    for cmd_text, char_id in commands:
        print(f"📝 Command: {cmd_text}")

        # Parse the command
        if char_id:
            default_char = game.get_character(char_id)
            parsed = parser.parse(cmd_text, default_character=default_char.name if default_char else None)
        else:
            parsed = parser.parse(cmd_text)

        if not parsed:
            print("   ❌ Failed to parse command")
            print()
            continue

        # Resolve character
        if parsed.character_name:
            char = game.get_character_by_name(parsed.character_name, "player1")
        elif char_id:
            char = game.get_character(char_id)
        else:
            print("   ❌ No character specified")
            print()
            continue

        if not char:
            print(f"   ❌ Character not found: {parsed.character_name}")
            print()
            continue

        # Create and execute order
        order = parser.create_order(parsed, char.id, "player1")
        game.add_order(order)

        result = turn_manager.execute_order(order)
        if result:
            print(f"   ✅ {result}")
        print()

    # Show final state
    print("=" * 60)
    print("Final State")
    print("=" * 60)
    print()

    for char in [hero, lieutenant]:
        # Refresh from game state
        char = game.get_character(char.id)
        inv = game.get_character_inventory(char.id)
        loc = game.get_location(char.location_id)

        print(f"👤 {char.full_name}")
        print(f"   Location: {loc.name if loc else 'Unknown'}")
        print(f"   Resources:")
        print(f"     - Gold: {inv.get(ResourceType.GOLD)}")
        print(f"     - Soldiers: {inv.get(ResourceType.SOLDIER)}")
        print(f"     - Horses: {inv.get(ResourceType.HORSE)}")
        print()

    print("=" * 60)
    print("Phase 1 Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
