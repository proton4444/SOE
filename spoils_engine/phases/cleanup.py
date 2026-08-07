"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations


from spoils_engine.models import (
    GameState,
)
from spoils_engine import config


def cleanup_turn(game_state: GameState):
    """Perform end-of-turn cleanup."""
    # Reset movement points
    for char in game_state.characters.values():
        char.movement_points = config.CHARACTER_MOVEMENT_POINTS_PER_TURN

    # Restore magic and religious power
    for char in game_state.characters.values():
        char.magic_power_current = char.max_magic_power
        char.religious_power_current = char.max_religious_power

    # Natural healing: 1 point per day, weekly turn = 7 points
    for char in game_state.characters.values():
        if not char.is_dead and char.health < 100:
            char.health = min(100, char.health + 7)

    # Increment turn
    game_state.turn_number += 1

