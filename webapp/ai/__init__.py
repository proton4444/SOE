"""AI player management for the war-room dashboard."""

from webapp.ai.registry import (
    AgentProfile,
    AgentRegistry,
    AgentRegistryError,
    default_registry,
)

__all__ = [
    "AgentProfile",
    "AgentRegistry",
    "AgentRegistryError",
    "default_registry",
]
