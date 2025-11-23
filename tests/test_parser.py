"""
Tests for command parser
"""

import pytest
from src.soe.parser import CommandParser
from src.soe.models import OrderType


def test_parser_name_command():
    """Test parsing NAME command"""
    parser = CommandParser()

    parsed = parser.parse("NAME John Captain")
    assert parsed is not None
    assert parsed.command_type == OrderType.NAME
    assert parsed.parameters["new_name"] == "John"
    assert parsed.parameters["title"] == "Captain"


def test_parser_promote_command():
    """Test parsing PROMOTE command"""
    parser = CommandParser()

    parsed = parser.parse("PROMOTE Jane Doe TO General")
    assert parsed is not None
    assert parsed.command_type == OrderType.PROMOTE
    assert parsed.character_name == "Jane Doe"
    assert parsed.parameters["new_title"] == "General"


def test_parser_go_command():
    """Test parsing GO command"""
    parser = CommandParser()

    parsed = parser.parse("GO TO Riverton", default_character="Hero")
    assert parsed is not None
    assert parsed.command_type == OrderType.GO
    assert parsed.parameters["destination"] == "Riverton"


def test_parser_halt_command():
    """Test parsing HALT command"""
    parser = CommandParser()

    parsed = parser.parse("HALT", default_character="Hero")
    assert parsed is not None
    assert parsed.command_type == OrderType.HALT


def test_parser_assign_command():
    """Test parsing ASSIGN command"""
    parser = CommandParser()

    parsed = parser.parse("ASSIGN 20 soldiers TO Captain Jack", default_character="General")
    assert parsed is not None
    assert parsed.command_type == OrderType.ASSIGN
    assert parsed.parameters["quantity"] == 20
    assert parsed.parameters["resource_type"] == "soldiers"
    assert parsed.parameters["target_name"] == "Captain Jack"


def test_parser_give_command():
    """Test parsing GIVE command"""
    parser = CommandParser()

    parsed = parser.parse("GIVE 100 gold TO Bill", default_character="Hero")
    assert parsed is not None
    assert parsed.command_type == OrderType.GIVE
    assert parsed.parameters["quantity"] == 100
    assert parsed.parameters["resource_type"] == "gold"
    assert parsed.parameters["target_name"] == "Bill"


def test_parser_get_command():
    """Test parsing GET command"""
    parser = CommandParser()

    parsed = parser.parse("GET 50 gold FROM Treasury", default_character="Hero")
    assert parsed is not None
    assert parsed.command_type == OrderType.GET
    assert parsed.parameters["quantity"] == 50
    assert parsed.parameters["resource_type"] == "gold"
    assert parsed.parameters["source_name"] == "Treasury"


def test_parser_have_command():
    """Test parsing HAVE command"""
    parser = CommandParser()

    parsed = parser.parse("HAVE Captain John GO TO Riverton")
    assert parsed is not None
    assert parsed.character_name == "Captain John"
    assert parsed.command_type == OrderType.GO
    assert parsed.parameters["destination"] == "Riverton"


def test_parser_case_insensitive():
    """Test that parsing is case insensitive"""
    parser = CommandParser()

    parsed1 = parser.parse("GO TO Riverton", default_character="Hero")
    parsed2 = parser.parse("go to Riverton", default_character="Hero")
    parsed3 = parser.parse("Go To Riverton", default_character="Hero")

    assert parsed1 is not None
    assert parsed2 is not None
    assert parsed3 is not None
    assert parsed1.command_type == parsed2.command_type == parsed3.command_type


def test_parser_normalization():
    """Test command text normalization"""
    parser = CommandParser()

    # Extra whitespace should be handled
    parsed = parser.parse("GO    TO    Riverton", default_character="Hero")
    assert parsed is not None
    assert parsed.parameters["destination"] == "Riverton"

    # Trailing period should be removed
    parsed = parser.parse("GO TO Riverton.", default_character="Hero")
    assert parsed is not None
    assert parsed.parameters["destination"] == "Riverton"
