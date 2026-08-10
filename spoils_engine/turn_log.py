"""Turn event log used by the engine and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from collections import defaultdict, deque


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
    silent: bool = False


@dataclass
class TurnLog:
    """Log of all events during a turn."""
    events: List[TurnEvent] = field(default_factory=list)
    _silence: dict = field(default_factory=lambda: defaultdict(deque), repr=False)

    def register_orders(self, orders_by_player) -> None:
        """Register per-phase silence in the same order handlers will emit."""
        phase_overrides = {
            "MOVE": "movement", "PASSAGE": "passage", "BUY_SHIP": "buy_ship",
            "AWAIT": "queue", "SAY": "message", "TELL": "message",
        }
        for player_id, orders in orders_by_player.items():
            for order in orders:
                actor_id = getattr(order, "actor_id", "") or getattr(order, "donor_id", "")
                phase = phase_overrides.get(order.order_type(), order.order_type().lower())
                self._silence[(player_id, actor_id, phase)].append(bool(order.silent))

    def add(self, phase: str, player_id: str, event_type: str, description: str,
            location: str = "", character_id: str = "", success: bool = True):
        """Add an event to the log."""
        flags = self._silence.get((player_id, character_id, phase))
        silent = flags.popleft() if flags else False
        self.events.append(TurnEvent(
            phase=phase,
            player_id=player_id,
            event_type=event_type,
            description=description,
            location_city_id=location,
            character_id=character_id,
            success=success,
            silent=silent,
        ))

    def get_player_events(self, player_id: str) -> List[TurnEvent]:
        """Get all events for a specific player."""
        return [e for e in self.events if e.player_id == player_id and not e.silent]

