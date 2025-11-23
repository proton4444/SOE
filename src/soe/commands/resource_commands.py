"""
Resource management commands (ASSIGN, GIVE, GET, TAKE, etc.)
"""

from .base import Command, CommandResult
from ..models import Order, ResourceType
from ..utils import normalize_resource_type


class AssignCommand(Command):
    """
    ASSIGN command - Assign resources to a character.

    Syntax: ASSIGN <quantity> <resource_type> TO <character>
    Parameters:
        - resource_type: Type of resource (gold, soldiers, horses, etc.)
        - quantity: Amount to assign
        - target_name (optional): Name of target character (if different from order issuer)
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate ASSIGN command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        resource_type_str = order.get_parameter("resource_type")
        quantity = order.get_parameter("quantity")

        if not resource_type_str:
            return False, "Resource type not specified"
        if quantity is None or quantity <= 0:
            return False, "Invalid quantity"

        # Parse resource type
        try:
            resource_type = ResourceType[normalize_resource_type(resource_type_str)]
        except KeyError:
            return False, f"Unknown resource type: {resource_type_str}"

        # Check if character has enough resources
        inventory = self.game_state.get_character_inventory(character.id)
        if not inventory.has_enough(resource_type, quantity):
            return False, f"Insufficient {resource_type_str} (have {inventory.get(resource_type)}, need {quantity})"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute ASSIGN command"""
        character = self.game_state.get_character(order.character_id)
        resource_type_str = order.get_parameter("resource_type")
        quantity = order.get_parameter("quantity")
        target_name = order.get_parameter("target_name")

        resource_type = ResourceType[normalize_resource_type(resource_type_str)]

        # Get target character
        if target_name:
            target = self.game_state.get_character_by_name(target_name, character.player_id)
            if not target:
                return CommandResult(
                    success=False,
                    message=f"Character '{target_name}' not found"
                )
        else:
            target = character

        # Transfer resources
        source_inventory = self.game_state.get_character_inventory(character.id)
        target_inventory = self.game_state.get_character_inventory(target.id)

        if source_inventory.transfer_to(target_inventory, resource_type, quantity):
            character.update_timestamp()
            target.update_timestamp()

            if target.id == character.id:
                # This shouldn't happen, but handle it
                return CommandResult(
                    success=True,
                    message=f"{character.full_name} reorganized {quantity} {resource_type_str}"
                )
            else:
                return CommandResult(
                    success=True,
                    message=f"{character.full_name} assigned {quantity} {resource_type_str} to {target.full_name}"
                )
        else:
            return CommandResult(
                success=False,
                message=f"Failed to assign {resource_type_str}"
            )


class GiveCommand(Command):
    """
    GIVE command - Give resources to another character (possibly different player).

    Syntax: GIVE <quantity> <resource_type> TO <character>
    Parameters:
        - resource_type: Type of resource
        - quantity: Amount to give
        - target_name: Name of target character
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate GIVE command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        resource_type_str = order.get_parameter("resource_type")
        quantity = order.get_parameter("quantity")
        target_name = order.get_parameter("target_name")

        if not resource_type_str:
            return False, "Resource type not specified"
        if quantity is None or quantity <= 0:
            return False, "Invalid quantity"
        if not target_name:
            return False, "Target character not specified"

        # Parse resource type
        try:
            resource_type = ResourceType[normalize_resource_type(resource_type_str)]
        except KeyError:
            return False, f"Unknown resource type: {resource_type_str}"

        # Check if character has enough resources
        inventory = self.game_state.get_character_inventory(character.id)
        if not inventory.has_enough(resource_type, quantity):
            return False, f"Insufficient {resource_type_str}"

        # Check target exists
        target = self.game_state.get_character_by_name(target_name)
        if not target:
            return False, f"Character '{target_name}' not found"

        # Check if at same location
        if character.location_id != target.location_id:
            return False, f"{target.full_name} is not at the same location"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute GIVE command"""
        character = self.game_state.get_character(order.character_id)
        resource_type_str = order.get_parameter("resource_type")
        quantity = order.get_parameter("quantity")
        target_name = order.get_parameter("target_name")

        resource_type = ResourceType[normalize_resource_type(resource_type_str)]
        target = self.game_state.get_character_by_name(target_name)

        # Transfer resources
        source_inventory = self.game_state.get_character_inventory(character.id)
        target_inventory = self.game_state.get_character_inventory(target.id)

        if source_inventory.transfer_to(target_inventory, resource_type, quantity):
            character.update_timestamp()
            target.update_timestamp()
            return CommandResult(
                success=True,
                message=f"{character.full_name} gave {quantity} {resource_type_str} to {target.full_name}"
            )
        else:
            return CommandResult(
                success=False,
                message=f"Failed to give {resource_type_str}"
            )


class GetCommand(Command):
    """
    GET/OBTAIN command - Take resources from location or subordinate.

    Syntax: GET <quantity> <resource_type> FROM <source>
    Parameters:
        - resource_type: Type of resource
        - quantity: Amount to get
        - source_name (optional): Name of character or location to get from
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate GET command"""
        character = self.game_state.get_character(order.character_id)
        if not character:
            return False, "Character not found"

        resource_type_str = order.get_parameter("resource_type")
        quantity = order.get_parameter("quantity")

        if not resource_type_str:
            return False, "Resource type not specified"
        if quantity is None or quantity <= 0:
            return False, "Invalid quantity"

        # Parse resource type
        try:
            ResourceType[resource_type_str.upper()]
        except KeyError:
            return False, f"Unknown resource type: {resource_type_str}"

        return True, ""

    def execute(self, order: Order) -> CommandResult:
        """Execute GET command"""
        character = self.game_state.get_character(order.character_id)
        resource_type_str = order.get_parameter("resource_type")
        quantity = order.get_parameter("quantity")
        source_name = order.get_parameter("source_name")

        resource_type = ResourceType[normalize_resource_type(resource_type_str)]

        # Determine source
        if source_name:
            # Try to get from another character
            source_char = self.game_state.get_character_by_name(source_name, character.player_id)
            if source_char:
                source_inventory = self.game_state.get_character_inventory(source_char.id)
                source_desc = source_char.full_name
            else:
                # Try to get from location
                source_loc = self.game_state.get_location_by_name(source_name)
                if source_loc:
                    source_inventory = self.game_state.get_location_inventory(source_loc.id)
                    source_desc = source_loc.name
                else:
                    return CommandResult(
                        success=False,
                        message=f"Source '{source_name}' not found"
                    )
        else:
            # Get from current location
            if not character.location_id:
                return CommandResult(
                    success=False,
                    message=f"{character.full_name} is not at any location"
                )
            location = self.game_state.get_location(character.location_id)
            source_inventory = self.game_state.get_location_inventory(location.id)
            source_desc = location.name

        # Transfer resources
        target_inventory = self.game_state.get_character_inventory(character.id)

        if source_inventory.transfer_to(target_inventory, resource_type, quantity):
            character.update_timestamp()
            return CommandResult(
                success=True,
                message=f"{character.full_name} obtained {quantity} {resource_type_str} from {source_desc}"
            )
        else:
            return CommandResult(
                success=False,
                message=f"Insufficient {resource_type_str} at {source_desc}"
            )


class TakeCommand(Command):
    """
    TAKE command - Alias for GET command.
    """

    def validate(self, order: Order) -> tuple[bool, str]:
        """Validate TAKE command"""
        get_command = GetCommand(self.game_state)
        return get_command.validate(order)

    def execute(self, order: Order) -> CommandResult:
        """Execute TAKE command"""
        get_command = GetCommand(self.game_state)
        return get_command.execute(order)
