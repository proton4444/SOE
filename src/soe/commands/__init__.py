"""
Command execution system for Spoils of Empire
"""

from .base import Command, CommandResult, CommandExecutor
from .character_commands import NameCommand, PromoteCommand
from .movement_commands import GoCommand, HaltCommand
from .resource_commands import AssignCommand, GiveCommand, GetCommand, TakeCommand

__all__ = [
    "Command",
    "CommandResult",
    "CommandExecutor",
    "NameCommand",
    "PromoteCommand",
    "GoCommand",
    "HaltCommand",
    "AssignCommand",
    "GiveCommand",
    "GetCommand",
    "TakeCommand",
]
