#!/usr/bin/env python3
"""
Command-line interface for the Spoils of Empire PBEM engine.

Uses Typer for a clean, user-friendly CLI experience.
"""

import sys
from pathlib import Path
from typing import Optional
import yaml

try:
    import typer
except ImportError:
    print("Error: typer not installed. Please run: pip install typer")
    sys.exit(1)

from spoils_engine import models, config, storage, map_loader, parser, engine, reporting


app = typer.Typer(
    name="soe",
    help="Spoils of Empire PBEM Engine",
    add_completion=False
)


@app.command()
def init_game(
    game_id: str = typer.Argument(..., help="Unique ID for the game"),
    map_file: Optional[Path] = typer.Option(None, "--map", help="Path to map JSON file"),
    players_file: Optional[Path] = typer.Option(None, "--players", help="Path to players YAML file"),
):
    """
    Initialize a new game.

    Creates a new game directory with initial state.
    """
    game_dir = Path("games") / game_id

    if storage.game_exists(game_dir):
        typer.echo(f"Error: Game '{game_id}' already exists at {game_dir}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Initializing game '{game_id}'...")

    # Load or create map
    if map_file and map_file.exists():
        typer.echo(f"Loading map from {map_file}...")
        world_map = map_loader.load_map_from_json(map_file)
    else:
        typer.echo("No map specified, creating sample map...")
        world_map = map_loader.create_sample_map()

    # Initialize game state
    game_state = models.GameState(
        turn_number=0,
        world_map=world_map
    )

    # Load players
    if players_file and players_file.exists():
        typer.echo(f"Loading players from {players_file}...")
        with open(players_file, 'r') as f:
            players_data = yaml.safe_load(f)

        for i, player_data in enumerate(players_data.get('players', [])):
            player_id = player_data.get('id', f"player_{i+1}")
            player_name = player_data.get('name', f"Player {i+1}")
            start_city_id = player_data.get('start_city')

            # Create faction
            faction = models.Faction(
                id=player_id,
                name=player_name,
                treasury=config.STARTING_TREASURY,
                controlled_city_ids={start_city_id} if start_city_id else set()
            )
            game_state.factions[player_id] = faction

            # Create leader character
            leader_name = player_data.get('leader_name', f"{player_name} Leader")
            char_id = f"char_{player_id}_leader"
            leader = models.Character(
                id=char_id,
                name=leader_name,
                faction_id=player_id,
                location_city_id=start_city_id or list(world_map.cities.keys())[0],
                combat_skill=config.STARTING_COMBAT_SKILL,
                magic_skill=config.STARTING_MAGIC_SKILL,
                magic_power_current=config.STARTING_MAGIC_SKILL
            )
            game_state.characters[char_id] = leader

            typer.echo(f"  Created faction: {player_name} ({player_id})")
    else:
        typer.echo("No players file specified. Creating example factions...")

        # Create 2 example factions
        city_ids = list(world_map.cities.keys())

        for i in range(2):
            player_id = f"player_{i+1}"
            faction = models.Faction(
                id=player_id,
                name=f"Faction {i+1}",
                treasury=config.STARTING_TREASURY,
                controlled_city_ids={city_ids[i % len(city_ids)]}
            )
            game_state.factions[player_id] = faction

            # Create leader
            char_id = f"char_{player_id}_leader"
            leader = models.Character(
                id=char_id,
                name=f"Leader {i+1}",
                faction_id=player_id,
                location_city_id=city_ids[i % len(city_ids)],
                combat_skill=config.STARTING_COMBAT_SKILL,
                magic_skill=config.STARTING_MAGIC_SKILL,
                magic_power_current=config.STARTING_MAGIC_SKILL
            )
            game_state.characters[char_id] = leader

            typer.echo(f"  Created faction: Faction {i+1} ({player_id})")

    # Save game state
    storage.save_game_state(game_state, game_dir)

    typer.echo(f"\nGame '{game_id}' initialized successfully!")
    typer.echo(f"Game directory: {game_dir}")
    typer.echo(f"Factions: {len(game_state.factions)}")
    typer.echo(f"Cities: {len(game_state.world_map.cities)}")
    typer.echo("\nNext steps:")
    typer.echo(f"  1. Create order files in {game_dir}/orders/")
    typer.echo(f"  2. Run: soe process-turn {game_id} --turn 1 --seed 12345")


@app.command()
def show_state(
    game_id: str = typer.Argument(..., help="Game ID"),
):
    """
    Show current game state.

    Displays a summary of the game including factions, characters, and resources.
    """
    game_dir = Path("games") / game_id

    if not storage.game_exists(game_dir):
        typer.echo(f"Error: Game '{game_id}' not found at {game_dir}", err=True)
        raise typer.Exit(1)

    game_state = storage.load_game_state(game_dir)
    if not game_state:
        typer.echo(f"Error: Could not load game state from {game_dir}", err=True)
        raise typer.Exit(1)

    # Generate and display summary
    summary = reporting.generate_summary_report(game_state)
    typer.echo(summary)


@app.command()
def process_turn(
    game_id: str = typer.Argument(..., help="Game ID"),
    turn: int = typer.Option(..., "--turn", "-t", help="Turn number to process"),
    seed: int = typer.Option(..., "--seed", "-s", help="Random seed for determinism"),
    force: bool = typer.Option(False, "--force", help="Process even if the turn number is out of sequence"),
):
    """
    Process a game turn.

    Reads order files, processes them, and generates reports.
    """
    game_dir = Path("games") / game_id

    if not storage.game_exists(game_dir):
        typer.echo(f"Error: Game '{game_id}' not found", err=True)
        raise typer.Exit(1)

    typer.echo(f"Processing turn {turn} for game '{game_id}'...")

    # Load game state
    game_state = storage.load_game_state(game_dir)
    if not game_state:
        typer.echo(f"Error: Could not load game state", err=True)
        raise typer.Exit(1)

    # Turns must run in sequence. Re-running an already-processed turn applies
    # its orders a second time to the state they already produced.
    expected_turn = game_state.turn_number + 1
    if turn != expected_turn and not force:
        typer.echo(
            f"Error: game '{game_id}' is at turn {game_state.turn_number}, so the next "
            f"turn to process is {expected_turn}, not {turn}.\n"
            f"       Re-run with --force only if you intend to process out of sequence.",
            err=True,
        )
        raise typer.Exit(1)

    # Read order files
    orders_dir = game_dir / "orders"
    orders_by_player = {}

    if orders_dir.exists():
        for faction_id in game_state.factions.keys():
            order_file = orders_dir / f"{faction_id}_turn{turn}.txt"
            if order_file.exists():
                typer.echo(f"  Reading orders for {faction_id}...")
                with open(order_file, 'r') as f:
                    raw_orders = f.read()

                parsed_orders = parser.parse_orders(raw_orders, game_state, faction_id)
                orders_by_player[faction_id] = parsed_orders
                typer.echo(f"    Parsed {len(parsed_orders)} orders")
            else:
                typer.echo(f"  No orders found for {faction_id} (file: {order_file})")
                orders_by_player[faction_id] = []
    else:
        typer.echo(f"  Orders directory not found: {orders_dir}")
        typer.echo(f"  Processing turn with no orders...")

    # Run turn
    typer.echo(f"\nProcessing turn with seed {seed}...")
    game_state, turn_log = engine.run_turn(game_state, orders_by_player, seed)

    # Save updated state
    storage.save_game_state(game_state, game_dir)
    typer.echo(f"  Game state saved")

    # Generate reports
    typer.echo(f"\nGenerating reports...")
    reports_dir = game_dir / "reports"
    reports_dir.mkdir(exist_ok=True)

    reports = reporting.generate_player_reports(game_state, turn_log, orders_by_player)

    for player_id, report in reports.items():
        report_file = reports_dir / f"{player_id}_turn{turn}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        typer.echo(f"  Report for {player_id}: {report_file}")

    typer.echo(f"\nTurn {turn} processed successfully!")
    typer.echo(f"Current turn: {game_state.turn_number}")


@app.command()
def example_setup():
    """
    Create an example game setup with sample maps and orders.

    This creates a complete example game for testing and demonstration.
    """
    typer.echo("Creating example game setup...")

    # Create maps directory
    maps_dir = Path("maps")
    maps_dir.mkdir(exist_ok=True)

    # Create sample map
    map_file = maps_dir / "sample_map.json"
    if not map_file.exists():
        world_map = map_loader.create_sample_map()
        map_loader.save_map_to_json(world_map, map_file)
        typer.echo(f"  Created sample map: {map_file}")

    # Create examples directory
    examples_dir = Path("examples")
    examples_dir.mkdir(exist_ok=True)

    # Create players.yaml
    players_file = examples_dir / "players.yaml"
    if not players_file.exists():
        players_data = {
            'players': [
                {
                    'id': 'player_1',
                    'name': 'The Golden Empire',
                    'leader_name': 'Emperor Marcus',
                    'start_city': 'madegi_doy'
                },
                {
                    'id': 'player_2',
                    'name': 'The Silver Horde',
                    'leader_name': 'Khan Tengri',
                    'start_city': 'albatross_city'
                }
            ]
        }
        with open(players_file, 'w') as f:
            yaml.dump(players_data, f, default_flow_style=False)
        typer.echo(f"  Created players file: {players_file}")

    # Create example order files
    order1_file = examples_dir / "orders_player1_turn1.txt"
    if not order1_file.exists():
        with open(order1_file, 'w') as f:
            f.write("""# Example orders for Player 1, Turn 1

# Recruit some soldiers in our starting city
Recruit 20 soldiers in Madegi Doy.

# Move our leader to explore
Have Emperor Marcus go to Kitesta.

# Try to recruit more units
Have Emperor Marcus recruit 10 soldiers in Kitesta.
""")
        typer.echo(f"  Created example orders: {order1_file}")

    order2_file = examples_dir / "orders_player2_turn1.txt"
    if not order2_file.exists():
        with open(order2_file, 'w') as f:
            f.write("""# Example orders for Player 2, Turn 1

# Build up our forces
Recruit 30 soldiers in Albatross City.

# Buy a ship since we're at a port
Buy 1 galley in Albatross City.

# Scout with our leader
Have Khan Tengri go to Madegi Doy.
""")
        typer.echo(f"  Created example orders: {order2_file}")

    typer.echo("\nExample setup complete!")
    typer.echo("\nTo create and run the example game:")
    typer.echo("  1. soe init-game example --map maps/sample_map.json --players examples/players.yaml")
    typer.echo("  2. mkdir -p games/example/orders")
    typer.echo("  3. cp examples/orders_player1_turn1.txt games/example/orders/")
    typer.echo("  4. cp examples/orders_player2_turn1.txt games/example/orders/")
    typer.echo("  5. soe process-turn example --turn 1 --seed 42")
    typer.echo("  6. cat games/example/reports/player_1_turn1.txt")


if __name__ == "__main__":
    app()
