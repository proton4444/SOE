"""
Natural language command parser

Parses English-like commands into structured Order objects.
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from ..models import Order, OrderType


@dataclass
class ParsedCommand:
    """Represents a parsed command"""
    command_type: OrderType
    character_name: Optional[str] = None
    parameters: Dict[str, Any] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class CommandParser:
    """
    Parses natural language commands into structured orders.

    Examples:
        - "NAME John Smith Captain"
        - "PROMOTE Jane Doe TO General"
        - "GO TO Riverton"
        - "GIVE 100 gold TO Bill"
        - "ASSIGN 20 soldiers TO Captain Jack"
    """

    def __init__(self):
        # Reserved words that should not be part of names
        self.reserved_words = {
            'to', 'from', 'and', 'then', 'the', 'a', 'an',
            'at', 'in', 'on', 'with', 'of', 'for',
            'have', 'has', 'go', 'move', 'travel', 'halt', 'stop',
            'assign', 'give', 'get', 'take', 'obtain',
            'name', 'promote', 'hire',
        }

    def parse(self, command_text: str, default_character: Optional[str] = None) -> Optional[ParsedCommand]:
        """
        Parse a command string into a ParsedCommand object.

        Args:
            command_text: The command string to parse
            default_character: Default character name if not specified in command

        Returns:
            ParsedCommand or None if parsing fails
        """
        # Normalize the command
        text = self._normalize(command_text)
        if not text:
            return None

        # Split into tokens
        tokens = self._tokenize(text)
        if not tokens:
            return None

        # Determine command type from first token
        command_word = tokens[0].upper()

        # Parse based on command type
        if command_word == "NAME":
            return self._parse_name(tokens)
        elif command_word == "PROMOTE":
            return self._parse_promote(tokens)
        elif command_word in ["GO", "MOVE", "TRAVEL"]:
            return self._parse_go(tokens, default_character)
        elif command_word in ["HALT", "STOP"]:
            return self._parse_halt(tokens, default_character)
        elif command_word == "ASSIGN":
            return self._parse_assign(tokens, default_character)
        elif command_word == "GIVE":
            return self._parse_give(tokens, default_character)
        elif command_word in ["GET", "OBTAIN"]:
            return self._parse_get(tokens, default_character)
        elif command_word == "TAKE":
            return self._parse_take(tokens, default_character)
        elif command_word == "HAVE":
            # "HAVE <character> <command>"
            return self._parse_have(tokens)
        else:
            return None

    def _normalize(self, text: str) -> str:
        """Normalize command text"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove trailing period
        text = text.rstrip('.')
        # Strip leading/trailing whitespace
        text = text.strip()
        return text

    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize command text, respecting quoted strings.
        """
        tokens = []
        current_token = []
        in_quotes = False

        for char in text:
            if char == '"':
                in_quotes = not in_quotes
            elif char in ' ,;:' and not in_quotes:
                if current_token:
                    tokens.append(''.join(current_token))
                    current_token = []
            else:
                current_token.append(char)

        if current_token:
            tokens.append(''.join(current_token))

        return tokens

    def _parse_name(self, tokens: List[str]) -> Optional[ParsedCommand]:
        """
        Parse NAME command.
        Syntax: NAME <character> <new_name> [title]
        """
        if len(tokens) < 3:
            return None

        # For now, assume: NAME <new_name> [title]
        # The character will be determined by context
        new_name = tokens[1]
        title = tokens[2] if len(tokens) > 2 else None

        return ParsedCommand(
            command_type=OrderType.NAME,
            parameters={
                "new_name": new_name,
                "title": title
            }
        )

    def _parse_promote(self, tokens: List[str]) -> Optional[ParsedCommand]:
        """
        Parse PROMOTE command.
        Syntax: PROMOTE <character> TO <title>
        """
        # Find "TO" keyword
        try:
            to_idx = [t.upper() for t in tokens].index("TO")
        except ValueError:
            return None

        if to_idx < 2 or to_idx >= len(tokens) - 1:
            return None

        # Character name is between PROMOTE and TO
        character_name = " ".join(tokens[1:to_idx])
        # Title is after TO
        new_title = " ".join(tokens[to_idx + 1:])

        return ParsedCommand(
            command_type=OrderType.PROMOTE,
            character_name=character_name,
            parameters={"new_title": new_title}
        )

    def _parse_go(self, tokens: List[str], default_character: Optional[str]) -> Optional[ParsedCommand]:
        """
        Parse GO/MOVE/TRAVEL command.
        Syntax: GO TO <location>
        """
        # Find "TO" keyword
        try:
            to_idx = [t.upper() for t in tokens].index("TO")
        except ValueError:
            # No "TO", assume everything after GO is destination
            destination = " ".join(tokens[1:])
            if not destination:
                return None
            return ParsedCommand(
                command_type=OrderType.GO,
                character_name=default_character,
                parameters={"destination": destination}
            )

        destination = " ".join(tokens[to_idx + 1:])
        if not destination:
            return None

        return ParsedCommand(
            command_type=OrderType.GO,
            character_name=default_character,
            parameters={"destination": destination}
        )

    def _parse_halt(self, tokens: List[str], default_character: Optional[str]) -> Optional[ParsedCommand]:
        """
        Parse HALT/STOP command.
        Syntax: HALT
        """
        return ParsedCommand(
            command_type=OrderType.HALT,
            character_name=default_character,
            parameters={}
        )

    def _parse_assign(self, tokens: List[str], default_character: Optional[str]) -> Optional[ParsedCommand]:
        """
        Parse ASSIGN command.
        Syntax: ASSIGN <quantity> <resource_type> TO <character>
        """
        if len(tokens) < 3:
            return None

        # Extract quantity and resource type
        try:
            quantity = int(tokens[1])
        except ValueError:
            return None

        resource_type = tokens[2]

        # Find "TO" keyword
        target_name = None
        try:
            to_idx = [t.upper() for t in tokens].index("TO")
            target_name = " ".join(tokens[to_idx + 1:])
        except ValueError:
            pass

        return ParsedCommand(
            command_type=OrderType.ASSIGN,
            character_name=default_character,
            parameters={
                "quantity": quantity,
                "resource_type": resource_type,
                "target_name": target_name
            }
        )

    def _parse_give(self, tokens: List[str], default_character: Optional[str]) -> Optional[ParsedCommand]:
        """
        Parse GIVE command.
        Syntax: GIVE <quantity> <resource_type> TO <character>
        """
        if len(tokens) < 3:
            return None

        try:
            quantity = int(tokens[1])
        except ValueError:
            return None

        resource_type = tokens[2]

        # Find "TO" keyword
        try:
            to_idx = [t.upper() for t in tokens].index("TO")
            target_name = " ".join(tokens[to_idx + 1:])
        except ValueError:
            return None

        return ParsedCommand(
            command_type=OrderType.GIVE,
            character_name=default_character,
            parameters={
                "quantity": quantity,
                "resource_type": resource_type,
                "target_name": target_name
            }
        )

    def _parse_get(self, tokens: List[str], default_character: Optional[str]) -> Optional[ParsedCommand]:
        """
        Parse GET/OBTAIN command.
        Syntax: GET <quantity> <resource_type> [FROM <source>]
        """
        if len(tokens) < 3:
            return None

        try:
            quantity = int(tokens[1])
        except ValueError:
            return None

        resource_type = tokens[2]

        # Find "FROM" keyword
        source_name = None
        try:
            from_idx = [t.upper() for t in tokens].index("FROM")
            source_name = " ".join(tokens[from_idx + 1:])
        except ValueError:
            pass

        return ParsedCommand(
            command_type=OrderType.GET,
            character_name=default_character,
            parameters={
                "quantity": quantity,
                "resource_type": resource_type,
                "source_name": source_name
            }
        )

    def _parse_take(self, tokens: List[str], default_character: Optional[str]) -> Optional[ParsedCommand]:
        """
        Parse TAKE command.
        Syntax: TAKE <quantity> <resource_type> [FROM <source>]
        """
        return self._parse_get(tokens, default_character)

    def _parse_have(self, tokens: List[str]) -> Optional[ParsedCommand]:
        """
        Parse HAVE command.
        Syntax: HAVE <character> <command>
        """
        if len(tokens) < 3:
            return None

        # Find where the actual command starts
        # Look for command keywords
        command_keywords = ["GO", "MOVE", "TRAVEL", "HALT", "STOP", "ASSIGN", "GIVE", "GET", "TAKE"]
        command_start_idx = None

        for i, token in enumerate(tokens[1:], 1):
            if token.upper() in command_keywords:
                command_start_idx = i
                break

        if command_start_idx is None:
            return None

        # Character name is between HAVE and command
        character_name = " ".join(tokens[1:command_start_idx])
        # Parse the rest as a sub-command
        sub_command_tokens = tokens[command_start_idx:]

        parsed = self.parse(" ".join(sub_command_tokens), default_character=character_name)
        if parsed:
            parsed.character_name = character_name
        return parsed

    def create_order(self, parsed: ParsedCommand, character_id: str, player_id: str) -> Order:
        """
        Create an Order from a ParsedCommand.
        """
        return Order(
            character_id=character_id,
            player_id=player_id,
            order_type=parsed.command_type,
            parameters=parsed.parameters
        )
