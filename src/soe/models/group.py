"""
Group model for Spoils of Empire
"""

from dataclasses import dataclass, field
from typing import Optional, List
import uuid


@dataclass
class Group:
    """
    Represents a group of characters traveling or acting together.

    Groups have a leader and can contain multiple characters and resources.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    leader_id: Optional[str] = None

    # Members
    member_ids: List[str] = field(default_factory=list)

    # Current location
    location_id: Optional[str] = None

    # Travel status
    is_traveling: bool = False
    destination_id: Optional[str] = None
    arrival_turn: Optional[int] = None

    # Group resources (separate from individual character resources)
    group_gold: int = 0

    def add_member(self, character_id: str):
        """Add a character to the group"""
        if character_id not in self.member_ids:
            self.member_ids.append(character_id)

    def remove_member(self, character_id: str):
        """Remove a character from the group"""
        if character_id in self.member_ids:
            self.member_ids.remove(character_id)
        # If leader is removed, clear leader
        if character_id == self.leader_id:
            self.leader_id = None

    def set_leader(self, character_id: str) -> bool:
        """
        Set the group leader.
        Returns True if successful.
        """
        if character_id in self.member_ids:
            self.leader_id = character_id
            return True
        return False

    def is_leader(self, character_id: str) -> bool:
        """Check if a character is the group leader"""
        return character_id == self.leader_id

    def get_member_count(self) -> int:
        """Get the number of members in the group"""
        return len(self.member_ids)

    def is_empty(self) -> bool:
        """Check if group has no members"""
        return len(self.member_ids) == 0

    def start_travel(self, destination_id: str, arrival_turn: int):
        """Start traveling to a destination"""
        self.is_traveling = True
        self.destination_id = destination_id
        self.arrival_turn = arrival_turn

    def arrive(self, new_location_id: str):
        """Arrive at destination"""
        self.is_traveling = False
        self.location_id = new_location_id
        self.destination_id = None
        self.arrival_turn = None
