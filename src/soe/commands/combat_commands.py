"""
Combat and military commands for Spoils of Empire
"""

from .base import Command, CommandResult
from ..models import Order, CharacterType
import random


class AttackCommand(Command):
    """
    ATTACK command - Attack another character or location.

    Syntax: ATTACK <target>
    Parameters:
        - target_name: Name of character to attack
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate ATTACK command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if not character.is_alive:
            return False, f"{character.full_name} is dead"

        if not character.is_combatant:
            return False, f"{character.full_name} is a non-combatant"

        target_name = order.get_parameter("target_name")
        if not target_name:
            return False, "Target not specified"

        # Get target character
        target = self.game_state.get_character_by_name(target_name)
        if not target:
            return False, f"Target '{target_name}' not found"

        if not target.is_alive:
            return False, f"{target.full_name} is already dead"

        # Check if at same location
        if character.location_id != target.location_id:
            return False, f"{target.full_name} is not at the same location"

        # Can't attack yourself
        if character.id == target.id:
            return False, "Cannot attack yourself"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute ATTACK command"""
        character = self.game_state.get_character(order.character_id)
        target_name = order.get_parameter("target_name")
        target = self.game_state.get_character_by_name(target_name)

        # Calculate combat strength
        attacker_strength = self._calculate_strength(character)
        defender_strength = self._calculate_strength(target)

        # Add fortification bonus
        if target.is_fortified:
            defender_strength *= 1.5

        # Combat resolution
        attacker_advantage = attacker_strength / (attacker_strength + defender_strength)
        hit_roll = random.random()

        if hit_roll < attacker_advantage:
            # Hit! Calculate damage
            base_damage = int(20 * attacker_advantage)
            damage = max(10, base_damage)

            target_died = target.take_damage(damage)
            target.update_timestamp()

            if target_died:
                return CommandResult(
                    success=True,
                    message=f"{character.full_name} attacked {target.full_name} and killed them! ({damage} damage)"
                )
            else:
                return CommandResult(
                    success=True,
                    message=f"{character.full_name} attacked {target.full_name} and dealt {damage} damage ({target.health}/{target.max_health} HP remaining)"
                )
        else:
            # Miss or defended
            return CommandResult(
                success=True,
                message=f"{character.full_name} attacked {target.full_name} but the attack was defended!"
            )

    def _calculate_strength(self, character) -> float:
        """Calculate combat strength of a character"""
        from ..models import SkillType, ResourceType

        base_strength = 10.0

        # Add combat skill
        combat_skill = character.get_skill_level(SkillType.COMBAT)
        base_strength += combat_skill * 5

        # Add soldier count from inventory
        inv = self.game_state.get_character_inventory(character.id)
        soldiers = inv.get(ResourceType.SOLDIER)
        base_strength += soldiers * 2

        # Health modifier
        health_modifier = character.health / character.max_health
        base_strength *= health_modifier

        return max(1.0, base_strength)


class CaptureCommand(Command):
    """
    CAPTURE command - Attempt to capture an enemy character.

    Syntax: CAPTURE <target>
    Parameters:
        - target_name: Name of character to capture
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate CAPTURE command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        target_name = order.get_parameter("target_name")
        if not target_name:
            return False, "Target not specified"

        target = self.game_state.get_character_by_name(target_name)
        if not target:
            return False, f"Target '{target_name}' not found"

        if not target.is_alive:
            return False, f"{target.full_name} is dead"

        if character.location_id != target.location_id:
            return False, f"{target.full_name} is not at the same location"

        if target.character_type == CharacterType.PRISONER:
            return False, f"{target.full_name} is already a prisoner"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute CAPTURE command"""
        character = self.game_state.get_character(order.character_id)
        target_name = order.get_parameter("target_name")
        target = self.game_state.get_character_by_name(target_name)

        # Check if target is weak enough to capture
        if target.health > target.max_health * 0.3:
            return CommandResult(
                success=False,
                message=f"{target.full_name} is too strong to capture (must be below 30% health)"
            )

        # Attempt capture
        capture_chance = 0.7 if target.health <= target.max_health * 0.2 else 0.4

        if random.random() < capture_chance:
            # Successful capture
            target.character_type = CharacterType.PRISONER
            target.update_timestamp()

            return CommandResult(
                success=True,
                message=f"{character.full_name} captured {target.full_name}!"
            )
        else:
            return CommandResult(
                success=False,
                message=f"{character.full_name} failed to capture {target.full_name}"
            )


class EnslaveCommand(Command):
    """
    ENSLAVE command - Enslave a prisoner.

    Syntax: ENSLAVE <target>
    Parameters:
        - target_name: Name of prisoner to enslave
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate ENSLAVE command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        target_name = order.get_parameter("target_name")
        if not target_name:
            return False, "Target not specified"

        target = self.game_state.get_character_by_name(target_name)
        if not target:
            return False, f"Target '{target_name}' not found"

        if target.character_type != CharacterType.PRISONER:
            return False, f"{target.full_name} is not a prisoner"

        if character.location_id != target.location_id:
            return False, f"{target.full_name} is not at the same location"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute ENSLAVE command"""
        character = self.game_state.get_character(order.character_id)
        target_name = order.get_parameter("target_name")
        target = self.game_state.get_character_by_name(target_name)

        # Enslave the prisoner
        target.character_type = CharacterType.SLAVE
        target.player_id = character.player_id  # Slave belongs to captor
        target.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} enslaved {target.full_name}"
        )


class KillCommand(Command):
    """
    KILL/EXECUTE command - Kill a character.

    Syntax: KILL <target> / EXECUTE <target>
    Parameters:
        - target_name: Name of character to kill
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate KILL command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        target_name = order.get_parameter("target_name")
        if not target_name:
            return False, "Target not specified"

        target = self.game_state.get_character_by_name(target_name)
        if not target:
            return False, f"Target '{target_name}' not found"

        if not target.is_alive:
            return False, f"{target.full_name} is already dead"

        if character.location_id != target.location_id:
            return False, f"{target.full_name} is not at the same location"

        # Must be prisoner or slave to execute
        if target.character_type not in [CharacterType.PRISONER, CharacterType.SLAVE]:
            return False, f"Can only execute prisoners or slaves (use ATTACK for combat)"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute KILL command"""
        character = self.game_state.get_character(order.character_id)
        target_name = order.get_parameter("target_name")
        target = self.game_state.get_character_by_name(target_name)

        # Kill the target
        target.is_alive = False
        target.health = 0
        target.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} executed {target.full_name}"
        )


class FortifyCommand(Command):
    """
    FORTIFY command - Fortify current position for defensive bonus.

    Syntax: FORTIFY
    Parameters: None
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate FORTIFY command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if character.is_fortified:
            return False, f"{character.full_name} is already fortified"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute FORTIFY command"""
        character = self.game_state.get_character(order.character_id)

        character.is_fortified = True
        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} has fortified their position"
        )


class UnfortifyCommand(Command):
    """
    UNFORTIFY command - Remove fortification.

    Syntax: UNFORTIFY
    Parameters: None
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate UNFORTIFY command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if not character.is_fortified:
            return False, f"{character.full_name} is not fortified"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute UNFORTIFY command"""
        character = self.game_state.get_character(order.character_id)

        character.is_fortified = False
        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} is no longer fortified"
        )


class SecureCommand(Command):
    """
    SECURE command - Secure a location (take control).

    Syntax: SECURE <location>
    Parameters:
        - location_name (optional): Location to secure (defaults to current)
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate SECURE command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if not character.location_id:
            return False, f"{character.full_name} is not at any location"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute SECURE command"""
        character = self.game_state.get_character(order.character_id)
        location = self.game_state.get_location(character.location_id)

        old_owner = location.owner_id
        location.owner_id = character.player_id

        if old_owner:
            return CommandResult(
                success=True,
                message=f"{character.full_name} secured {location.name} from its previous owner"
            )
        else:
            return CommandResult(
                success=True,
                message=f"{character.full_name} secured {location.name}"
            )


class CombatantCommand(Command):
    """
    COMBATANT command - Set character as combatant.

    Syntax: COMBATANT
    Parameters: None
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate COMBATANT command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if character.is_combatant:
            return False, f"{character.full_name} is already a combatant"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute COMBATANT command"""
        character = self.game_state.get_character(order.character_id)

        character.is_combatant = True
        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} is now a combatant"
        )


class NoncomCommand(Command):
    """
    NONCOM command - Set character as non-combatant.

    Syntax: NONCOM
    Parameters: None
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate NONCOM command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if not character.is_combatant:
            return False, f"{character.full_name} is already a non-combatant"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute NONCOM command"""
        character = self.game_state.get_character(order.character_id)

        character.is_combatant = False
        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} is now a non-combatant"
        )


class LurkCommand(Command):
    """
    LURK command - Hide character from casual observation.

    Syntax: LURK
    Parameters: None
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate LURK command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if character.is_lurking:
            return False, f"{character.full_name} is already lurking"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute LURK command"""
        character = self.game_state.get_character(order.character_id)

        character.is_lurking = True
        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} is now lurking"
        )


class UnlurkCommand(Command):
    """
    UNLURK command - Stop lurking.

    Syntax: UNLURK
    Parameters: None
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate UNLURK command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        if not character.is_lurking:
            return False, f"{character.full_name} is not lurking"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute UNLURK command"""
        character = self.game_state.get_character(order.character_id)

        character.is_lurking = False
        character.update_timestamp()

        return CommandResult(
            success=True,
            message=f"{character.full_name} is no longer lurking"
        )
