"""Turn event log used by the engine and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TurnEvent:
    """A single event that occurred during turn processing."""
    phase: str
    player_id: str
    event_type: str
    description: str
    location_city_id: str = ""
    character_id: str = ""
    success: bool = True


@dataclass
class TurnLog:
    """Log of all events during a turn."""
    events: List[TurnEvent] = field(default_factory=list)

    def add(self, phase: str, player_id: str, event_type: str, description: str,
            location: str = "", character_id: str = "", success: bool = True):
        """Add an event to the log."""
        self.events.append(TurnEvent(
            phase=phase,
            player_id=player_id,
            event_type=event_type,
            description=description,
            location_city_id=location,
            character_id=character_id,
            success=success
        ))

    def get_player_events(self, player_id: str) -> List[TurnEvent]:
        """Get all events for a specific player."""
        return [e for e in self.events if e.player_id == player_id]

