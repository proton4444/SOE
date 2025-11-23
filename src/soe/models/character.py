"""
Character model for Spoils of Empire
"""

from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime
import uuid


class CharacterType(Enum):
    """Types of characters in the game"""
    LEADER = "leader"
    FOLLOWER = "follower"
    PRISONER = "prisoner"
    SLAVE = "slave"


class SkillType(Enum):
    """Types of skills characters can have"""
    COMBAT = "combat"
    MAGIC = "magic"
    STEALTH = "stealth"
    DIPLOMACY = "diplomacy"
    TRADE = "trade"
    CONSTRUCTION = "construction"
    MINING = "mining"
    SAILING = "sailing"


@dataclass
class Skill:
    """Represents a character skill with level"""
    skill_type: SkillType
    level: int = 0
    experience: int = 0

    def increase_level(self, amount: int = 1):
        """Increase skill level"""
        self.level += amount

    def add_experience(self, amount: int):
        """Add experience and level up if needed"""
        self.experience += amount
        # Simple leveling: every 100 exp = 1 level
        while self.experience >= 100:
            self.experience -= 100
            self.level += 1


@dataclass
class Character:
    """
    Represents a character in the game.

    Characters can be leaders (controlled by players) or followers
    (hired NPCs, soldiers, etc.)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    title: Optional[str] = None
    player_id: Optional[str] = None
    character_type: CharacterType = CharacterType.FOLLOWER

    # Stats
    health: int = 100
    max_health: int = 100
    is_alive: bool = True

    # Skills
    skills: Dict[SkillType, Skill] = field(default_factory=dict)

    # Location
    location_id: Optional[str] = None

    # Group membership
    group_id: Optional[str] = None
    is_group_leader: bool = False

    # Combat status
    is_combatant: bool = True

    # Resources carried
    gold: int = 0

    # Followers (if this is a leader)
    follower_ids: List[str] = field(default_factory=list)

    # Status
    is_lurking: bool = False
    is_fortified: bool = False

    # Relations
    allies: List[str] = field(default_factory=list)
    enemies: List[str] = field(default_factory=list)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialize skills if not provided"""
        if not self.skills:
            for skill_type in SkillType:
                self.skills[skill_type] = Skill(skill_type=skill_type)

    @property
    def full_name(self) -> str:
        """Get full name with title"""
        if self.title:
            return f"{self.title} {self.name}"
        return self.name

    def get_skill_level(self, skill_type: SkillType) -> int:
        """Get the level of a specific skill"""
        if skill_type in self.skills:
            return self.skills[skill_type].level
        return 0

    def set_skill_level(self, skill_type: SkillType, level: int):
        """Set a skill to a specific level"""
        if skill_type not in self.skills:
            self.skills[skill_type] = Skill(skill_type=skill_type)
        self.skills[skill_type].level = level

    def take_damage(self, amount: int) -> bool:
        """
        Apply damage to character.
        Returns True if character died.
        """
        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.is_alive = False
            return True
        return False

    def heal(self, amount: int):
        """Heal character"""
        self.health = min(self.health + amount, self.max_health)

    def add_follower(self, follower_id: str):
        """Add a follower to this character"""
        if follower_id not in self.follower_ids:
            self.follower_ids.append(follower_id)

    def remove_follower(self, follower_id: str):
        """Remove a follower from this character"""
        if follower_id in self.follower_ids:
            self.follower_ids.remove(follower_id)

    def add_ally(self, character_id: str):
        """Add an ally"""
        if character_id not in self.allies:
            self.allies.append(character_id)
        if character_id in self.enemies:
            self.enemies.remove(character_id)

    def add_enemy(self, character_id: str):
        """Add an enemy"""
        if character_id not in self.enemies:
            self.enemies.append(character_id)
        if character_id in self.allies:
            self.allies.remove(character_id)

    def set_neutral(self, character_id: str):
        """Set neutral relationship"""
        if character_id in self.allies:
            self.allies.remove(character_id)
        if character_id in self.enemies:
            self.enemies.remove(character_id)

    def update_timestamp(self):
        """Update the updated_at timestamp"""
        self.updated_at = datetime.now()
