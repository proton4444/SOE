"""
Encumbrance: how much a character and their group weigh.

rules.md Appendix B gives every item an encumbrance, and several rules are
priced directly off the total for a group:

    FLY         power = 1/5 of the group's encumbrance, rounded up  (rules.md)
    TELEPORT    power = the group's encumbrance, rounded up
    BUY PASSAGE fare  = the group's encumbrance, in gold

Appendix B also fixes the substance weights: a unit of every substance is worth
one gold, so the heavy ones are the cheap ones. One horse carries 5000 gold, or
500 silver, or 5 iron.

Not everything in Appendix B is modelled yet. Horses, wagons, armour, weapons,
catapults, battering rams and siege towers are not tracked as things a group
carries, so they weigh nothing here. Everything the engine *does* track --
people, soldiers, mined substances and purses -- is weighed exactly as the
appendix says.
"""

from __future__ import annotations

import math

from spoils_engine.models import Character, GameState


# rules.md Appendix B, "Item Characteristics". Encumbrance per single unit.
PERSON_ENCUMBRANCE = 1.0  # "Character ... 1"; a slave is likewise 1

SUBSTANCE_ENCUMBRANCE: dict[str, float] = {
    "stone": 1.0,
    "wood": 1.0,
    "iron": 1.0 / 5,
    "copper": 1.0 / 50,
    "silver": 1.0 / 500,
    "gold": 1.0 / 5000,
    "gems": 1.0 / 25_000,
    "gem": 1.0 / 25_000,  # tolerate the singular
}

# Appendix B values for things the engine does not yet track as cargo. Kept
# here so the numbers are recorded in one place when they are wired up.
UNMODELLED_ENCUMBRANCE: dict[str, float] = {
    "horse": 2.0,          # *** no encumbrance on land; 2 when flown/teleported
    "wagon": 10.0,         # *** on land only the wagons exceeding the horses count
    "armor": 1.0 / 5,
    "weapon": 1.0 / 5,
    "catapult": 4.0,
    "battering_ram": 10.0,
    "siege_tower": 20.0,
}


def resource_encumbrance(resources: dict[str, int], gold: float = 0.0) -> float:
    """Weight of a pile of substances, plus a purse of loose gold."""
    total = gold * SUBSTANCE_ENCUMBRANCE["gold"]
    for name, quantity in (resources or {}).items():
        if not quantity:
            continue
        total += SUBSTANCE_ENCUMBRANCE.get(str(name).lower(), 0.0) * quantity
    return total


def character_encumbrance(character: Character, game_state: GameState) -> float:
    """
    One character's own weight: themselves, their unnamed units, and their goods.

    Does not follow the group tree -- use `group_encumbrance` for that.
    """
    total = PERSON_ENCUMBRANCE
    total += resource_encumbrance(character.resources, character.gold)
    for stack in game_state.unit_stacks.values():
        if stack.owner_character_id == character.id:
            total += PERSON_ENCUMBRANCE * stack.count
    return total


def group_encumbrance(leader: Character, game_state: GameState) -> float:
    """
    Total weight a spell must lift: the leader, everyone under them, and cargo.

    This is the airborne/teleport reading of encumbrance. rules.md: summoned
    creatures "have zero encumbrance and no extra magical power is needed to
    teleport them", so they are simply not counted.
    """
    from spoils_engine import groups

    total = character_encumbrance(leader, game_state)
    for member in groups.group_members(leader.id, game_state):
        if member.id == leader.id:
            continue
        total += character_encumbrance(member, game_state)
    return total


def fly_power_cost(leader: Character, game_state: GameState) -> int:
    """rules.md: "one-fifth (1/5) of the total encumbrance of the group (rounded up)"."""
    return max(1, math.ceil(group_encumbrance(leader, game_state) / 5))


def teleport_power_cost(target: Character, game_state: GameState) -> int:
    """
    rules.md: "equal to the total encumbrance of the group (rounded up)".

    Distance does not enter into it: "The TELEPORT command has no limit on
    distance. As long as the spell-caster has sufficient power to handle the
    encumbrance, he may teleport to anywhere on the planet."
    """
    return max(1, math.ceil(group_encumbrance(target, game_state)))
