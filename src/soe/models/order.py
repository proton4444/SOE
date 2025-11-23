"""
Order model for Spoils of Empire
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class OrderStatus(Enum):
    """Status of an order"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OrderType(Enum):
    """Types of orders that can be issued"""
    # Movement
    GO = "go"
    TRAVEL = "travel"
    FLY = "fly"
    SAIL = "sail"

    # Character management
    NAME = "name"
    PROMOTE = "promote"
    HIRE = "hire"

    # Resource management
    ASSIGN = "assign"
    GIVE = "give"
    GET = "get"
    TAKE = "take"

    # Combat
    ATTACK = "attack"
    FORTIFY = "fortify"

    # Other
    HALT = "halt"
    WAIT = "wait"
    SAY = "say"


@dataclass
class Order:
    """
    Represents a command/order issued to a character.

    Orders are queued and executed based on game time.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    player_id: str = ""
    order_type: OrderType = OrderType.HALT

    # Order parameters (flexible storage for different order types)
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Execution status
    status: OrderStatus = OrderStatus.PENDING

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_turn: Optional[int] = None
    execution_turn: Optional[int] = None
    completion_turn: Optional[int] = None

    # Result
    result_message: Optional[str] = None
    success: bool = False

    def mark_in_progress(self, current_turn: int):
        """Mark order as in progress"""
        self.status = OrderStatus.IN_PROGRESS
        self.execution_turn = current_turn

    def mark_completed(self, current_turn: int, success: bool = True, message: str = ""):
        """Mark order as completed"""
        self.status = OrderStatus.COMPLETED
        self.completion_turn = current_turn
        self.success = success
        self.result_message = message

    def mark_cancelled(self, message: str = "Order cancelled"):
        """Mark order as cancelled"""
        self.status = OrderStatus.CANCELLED
        self.result_message = message

    def mark_failed(self, message: str = "Order failed"):
        """Mark order as failed"""
        self.status = OrderStatus.FAILED
        self.success = False
        self.result_message = message

    def is_executable(self, current_turn: int) -> bool:
        """Check if order can be executed this turn"""
        if self.status != OrderStatus.PENDING:
            return False
        if self.scheduled_turn is not None and current_turn < self.scheduled_turn:
            return False
        return True

    def get_parameter(self, key: str, default: Any = None) -> Any:
        """Get an order parameter"""
        return self.parameters.get(key, default)

    def set_parameter(self, key: str, value: Any):
        """Set an order parameter"""
        self.parameters[key] = value
