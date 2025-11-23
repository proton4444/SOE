"""
Movement commands (GO, MOVE, TRAVEL, HALT, etc.)
"""

from .base import Command, CommandResult
from ..models import Order, OrderStatus


class GoCommand(Command):
    """
    GO/MOVE/TRAVEL command - Move a character to a new location.

    Syntax: GO TO <location> / MOVE TO <location> / TRAVEL TO <location>
    Parameters:
        - destination: Name or ID of destination location
        - travel_time (optional): Number of turns to reach destination
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate GO command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if not character.is_alive:
            return False, f"{character.full_name} is dead and cannot travel"

        destination = order.get_parameter("destination")
        if not destination:
            return False, "Destination not specified"

        # Get destination location
        dest_location = self.game_state.get_location_by_name(destination)
        if not dest_location:
            # Try by ID
            dest_location = self.game_state.get_location(destination)
        if not dest_location:
            return False, f"Location '{destination}' not found"

        # Check if already at destination
        if character.location_id == dest_location.id:
            return False, f"{character.full_name} is already at {dest_location.name}"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute GO command"""
        character = self.game_state.get_character(order.character_id)
        destination = order.get_parameter("destination")
        travel_time = order.get_parameter("travel_time", 1)  # Default 1 turn

        # Get current and destination locations
        current_location = None
        if character.location_id:
            current_location = self.game_state.get_location(character.location_id)

        dest_location = self.game_state.get_location_by_name(destination)
        if not dest_location:
            dest_location = self.game_state.get_location(destination)

        # Calculate travel time if not specified
        if current_location and dest_location:
            # Check if locations are connected
            distance = current_location.get_distance_to(dest_location.id)
            if distance:
                travel_time = max(1, distance // 10)  # 1 turn per 10 distance units

        # For now, instant travel (asynchronous travel would queue another order)
        # Remove from old location
        if current_location:
            current_location.remove_character(character.id)

        # Add to new location
        character.location_id = dest_location.id
        dest_location.add_character(character.id)
        character.update_timestamp()

        from_text = f" from {current_location.name}" if current_location else ""
        return CommandResult(
            success=True,
            message=f"{character.full_name} traveled{from_text} to {dest_location.name}"
        )


class HaltCommand(Command):
    """
    HALT/STOP command - Cancel all pending orders for a character.

    Syntax: HALT / STOP
    Parameters: None
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate HALT command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"
        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute HALT command"""
        character = self.game_state.get_character(order.character_id)

        # Get all pending orders for this character (except this HALT order)
        pending_orders = [
            o for o in self.game_state.get_character_orders(character.id, OrderStatus.PENDING)
            if o.id != order.id
        ]

        # Cancel all pending orders
        cancelled_count = 0
        for pending_order in pending_orders:
            pending_order.mark_cancelled("Cancelled by HALT command")
            cancelled_count += 1

        if cancelled_count == 0:
            message = f"{character.full_name} has no pending orders to cancel"
        elif cancelled_count == 1:
            message = f"{character.full_name} cancelled 1 pending order"
        else:
            message = f"{character.full_name} cancelled {cancelled_count} pending orders"

        return CommandResult(
            success=True,
            message=message,
            data={"cancelled_count": cancelled_count}
        )
