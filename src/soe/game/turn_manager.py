"""
Turn management and order execution
"""

from typing import List, Optional
from ..models import Order, OrderStatus
from .game_state import GameState


class TurnManager:
    """
    Manages game turn processing and order execution.
    """

    def __init__(self, game_state: GameState):
        self.game_state = game_state

    def process_turn(self) -> List[str]:
        """
        Process one game turn.
        Returns a list of messages describing what happened.
        """
        messages = []
        messages.append(f"=== Turn {self.game_state.current_turn} (Week {self.game_state.game_week}, Day {self.game_state.game_day}) ===")

        # Get all executable orders for this turn
        executable_orders = self.get_executable_orders()

        if not executable_orders:
            messages.append("No orders to process this turn.")
        else:
            messages.append(f"Processing {len(executable_orders)} order(s)...")

            # Execute orders
            for order in executable_orders:
                result = self.execute_order(order)
                if result:
                    messages.append(result)

        # Advance the turn
        self.game_state.advance_turn()

        return messages

    def get_executable_orders(self) -> List[Order]:
        """Get all orders that can be executed this turn"""
        pending_orders = self.game_state.get_pending_orders()
        return [
            order for order in pending_orders
            if order.is_executable(self.game_state.current_turn)
        ]

    def execute_order(self, order: Order) -> Optional[str]:
        """
        Execute a single order.
        Returns a message describing the result.
        """
        from ..commands import CommandExecutor

        # Mark as in progress
        order.mark_in_progress(self.game_state.current_turn)

        # Get the character
        character = self.game_state.get_character(order.character_id)
        if not character:
            order.mark_failed(f"Character {order.character_id} not found")
            return f"Failed to execute order: Character not found"

        # Execute the order using CommandExecutor
        executor = CommandExecutor(self.game_state)
        try:
            result = executor.execute_order(order)
            if result.success:
                order.mark_completed(
                    self.game_state.current_turn,
                    success=True,
                    message=result.message
                )
                return f"{character.full_name}: {result.message}"
            else:
                order.mark_failed(result.message)
                return f"{character.full_name}: Failed - {result.message}"
        except Exception as e:
            order.mark_failed(str(e))
            return f"{character.full_name}: Error - {str(e)}"

    def queue_order(self, order: Order, scheduled_turn: Optional[int] = None):
        """
        Queue an order for execution.
        If scheduled_turn is None, order will execute on next available turn.
        """
        if scheduled_turn is None:
            scheduled_turn = self.game_state.current_turn + 1
        order.scheduled_turn = scheduled_turn
        self.game_state.add_order(order)

    def cancel_orders_for_character(self, character_id: str) -> int:
        """
        Cancel all pending orders for a character.
        Returns the number of orders cancelled.
        """
        return self.game_state.cancel_character_orders(character_id)
