"""
Base command classes and executor
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..models import Order, OrderType
from ..game.game_state import GameState


@dataclass
class CommandResult:
    """Result of command execution"""
    success: bool
    message: str
    data: Optional[dict] = None


class Command(ABC):
    """
    Base class for all game commands.
    """

    def __init__(self, game_state: GameState):
        self.game_state = game_state

    @abstractmethod
    def execute(self, order: Order) -> CommandResult:
        """
        Execute the command.
        Returns CommandResult indicating success/failure.
        """
        pass

    @abstractmethod
    def validate(self, order: Order) -> tuple[bool, str]:
        """
        Validate that the order can be executed.
        Returns (is_valid, error_message).
        """
        pass


class CommandExecutor:
    """
    Executes orders by dispatching to appropriate command handlers.
    """

    def __init__(self, game_state: GameState):
        self.game_state = game_state
        self._command_map = self._initialize_commands()

    def _initialize_commands(self) -> dict[OrderType, Command]:
        """Initialize the command registry"""
        from .character_commands import NameCommand, PromoteCommand
        from .movement_commands import GoCommand, HaltCommand, FlyCommand, SailCommand, TeleportCommand
        from .resource_commands import AssignCommand, GiveCommand, GetCommand, TakeCommand
        from .combat_commands import (
            AttackCommand, CaptureCommand, EnslaveCommand, KillCommand,
            FortifyCommand, UnfortifyCommand, SecureCommand,
            CombatantCommand, NoncomCommand, LurkCommand, UnlurkCommand
        )

        return {
            # Character management
            OrderType.NAME: NameCommand(self.game_state),
            OrderType.PROMOTE: PromoteCommand(self.game_state),

            # Movement
            OrderType.GO: GoCommand(self.game_state),
            OrderType.TRAVEL: GoCommand(self.game_state),
            OrderType.FLY: FlyCommand(self.game_state),
            OrderType.SAIL: SailCommand(self.game_state),
            OrderType.TELEPORT: TeleportCommand(self.game_state),
            OrderType.HALT: HaltCommand(self.game_state),

            # Resources
            OrderType.ASSIGN: AssignCommand(self.game_state),
            OrderType.GIVE: GiveCommand(self.game_state),
            OrderType.GET: GetCommand(self.game_state),
            OrderType.TAKE: TakeCommand(self.game_state),

            # Combat
            OrderType.ATTACK: AttackCommand(self.game_state),
            OrderType.CAPTURE: CaptureCommand(self.game_state),
            OrderType.ENSLAVE: EnslaveCommand(self.game_state),
            OrderType.KILL: KillCommand(self.game_state),
            OrderType.EXECUTE: KillCommand(self.game_state),  # EXECUTE uses KILL handler
            OrderType.FORTIFY: FortifyCommand(self.game_state),
            OrderType.UNFORTIFY: UnfortifyCommand(self.game_state),
            OrderType.SECURE: SecureCommand(self.game_state),

            # Status
            OrderType.COMBATANT: CombatantCommand(self.game_state),
            OrderType.NONCOM: NoncomCommand(self.game_state),
            OrderType.LURK: LurkCommand(self.game_state),
            OrderType.UNLURK: UnlurkCommand(self.game_state),
        }

    def execute_order(self, order: Order) -> CommandResult:
        """
        Execute an order by delegating to the appropriate command handler.
        """
        # Get command handler
        command = self._command_map.get(order.order_type)
        if not command:
            return CommandResult(
                success=False,
                message=f"Unknown command type: {order.order_type}"
            )

        # Validate before executing
        is_valid, error_msg = command.validate(order)
        if not is_valid:
            return CommandResult(success=False, message=error_msg)

        # Execute
        try:
            result = command.execute(order)
            return result
        except Exception as e:
            return CommandResult(
                success=False,
                message=f"Command execution error: {str(e)}"
            )
