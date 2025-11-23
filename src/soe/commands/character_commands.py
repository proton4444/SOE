"""
Character management commands (NAME, PROMOTE, etc.)
"""

from .base import Command, CommandResult
from ..models import Order


class NameCommand(Command):
    """
    NAME command - Name or rename a character.

    Syntax: NAME <character> <new_name>
    Parameters:
        - new_name: The new name for the character
        - title (optional): Title to include with name
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate NAME command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        new_name = order.get_parameter("new_name")
        if not new_name:
            return False, "New name not specified"

        # Check if name is already in use by another character of same player
        existing = self.game_state.get_character_by_name(new_name, character.player_id)
        if existing and existing.id != character.id:
            return False, f"You already have a character named '{new_name}'"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute NAME command"""
        character = self.game_state.get_character(order.character_id)
        new_name = order.get_parameter("new_name")
        title = order.get_parameter("title")

        old_full_name = character.full_name

        # Update name and title
        character.name = new_name
        if title is not None:
            character.title = title

        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{old_full_name} is now known as {character.full_name}"
        )


class PromoteCommand(Command):
    """
    PROMOTE command - Change a character's title.

    Syntax: PROMOTE <character> TO <title>
    Parameters:
        - new_title: The new title for the character
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate PROMOTE command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        new_title = order.get_parameter("new_title")
        if not new_title:
            return False, "New title not specified"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute PROMOTE command"""
        character = self.game_state.get_character(order.character_id)
        new_title = order.get_parameter("new_title")

        old_full_name = character.full_name
        character.title = new_title
        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{old_full_name} has been promoted to {character.full_name}"
        )
