"""
Command execution system for Spoils of Empire
"""

from .base import Command, CommandResult, CommandExecutor
from .character_commands import NameCommand, PromoteCommand
from .movement_commands import GoCommand, HaltCommand, FlyCommand, SailCommand, TeleportCommand
from .resource_commands import AssignCommand, GiveCommand, GetCommand, TakeCommand
from .combat_commands import (
    AttackCommand, CaptureCommand, EnslaveCommand, KillCommand,
    FortifyCommand, UnfortifyCommand, SecureCommand,
    CombatantCommand, NoncomCommand, LurkCommand, UnlurkCommand
)

__all__ = [
    "Command",
    "CommandResult",
    "CommandExecutor",
    "NameCommand",
    "PromoteCommand",
    "GoCommand",
    "HaltCommand",
    "FlyCommand",
    "SailCommand",
    "TeleportCommand",
    "AssignCommand",
    "GiveCommand",
    "GetCommand",
    "TakeCommand",
    "AttackCommand",
    "CaptureCommand",
    "EnslaveCommand",
    "KillCommand",
    "FortifyCommand",
    "UnfortifyCommand",
    "SecureCommand",
    "CombatantCommand",
    "NoncomCommand",
    "LurkCommand",
    "UnlurkCommand",
]
