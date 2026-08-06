"""
Groups and group leaders.

`rules.md` builds the whole command language on groups: "when you give a command
to a named character, the command will apply to that character plus to any other
characters (named or unnamed) assigned to him". A character is either assigned to
somebody (`Character.group_leader_id`) or leads their own group, and unnamed
units are assigned the same way through `UnitStack.owner_character_id`.

Three rules from `rules.md` drive everything here:

* Giving a character a direct order (the HAVE form) makes them a group leader,
  detaching them from whoever led them before.
* A group travels together. Moving the leader moves the members and the units
  assigned to them.
* ASSIGN and JOIN are the same operation from opposite ends -- ASSIGN is given
  to the character doing the assigning, JOIN to the one being assigned.

Membership is a tree, so every walk here is cycle-guarded. A cycle should be
impossible (`attach` refuses to make one) but a corrupt save must not hang the
turn processor.
"""

from typing import List, Optional

from spoils_engine.models import Character, GameState, LocationPosition, UnitStack

# A group nested deeper than this is either a cycle or a mistake; either way,
# stop walking rather than looping.
_MAX_DEPTH = 64


# ============================================================================
# READING THE TREE
# ============================================================================

def leader_of(character: Character, game_state: GameState) -> Character:
    """
    The character at the top of this one's chain of command.

    Returns `character` itself when they lead their own group.
    """
    seen = {character.id}
    current = character

    for _ in range(_MAX_DEPTH):
        if not current.group_leader_id:
            return current
        parent = game_state.characters.get(current.group_leader_id)
        if parent is None or parent.id in seen:
            return current
        seen.add(parent.id)
        current = parent

    return current


def is_group_leader(character: Character) -> bool:
    """True when this character answers to nobody in their own faction."""
    return not character.group_leader_id


def direct_members(leader_id: str, game_state: GameState) -> List[Character]:
    """Characters assigned straight to this one, in a stable order."""
    return [c for c in game_state.characters.values()
            if c.group_leader_id == leader_id and c.id != leader_id]


def group_members(leader_id: str, game_state: GameState) -> List[Character]:
    """
    Everyone under this character, at any depth, excluding the character.

    `rules.md`: "If a person who is assigned has other people or items assigned
    to him, then they will remain assigned to him" -- so a subordinate brings
    their own subordinates along.
    """
    found: List[Character] = []
    seen = {leader_id}
    frontier = [leader_id]

    for _ in range(_MAX_DEPTH):
        if not frontier:
            break
        next_frontier = []
        for parent_id in frontier:
            for member in direct_members(parent_id, game_state):
                if member.id in seen:
                    continue
                seen.add(member.id)
                found.append(member)
                next_frontier.append(member.id)
        frontier = next_frontier

    return found


def owned_stacks(character_id: str, game_state: GameState) -> List[UnitStack]:
    """Unit stacks assigned to this character."""
    return [s for s in game_state.unit_stacks.values()
            if s.owner_character_id == character_id]


def group_soldier_count(leader: Character, game_state: GameState,
                        unit_type=None) -> int:
    """
    Units in this character's group, counting their subordinates' units too.

    Unowned stacks at the leader's location count as well: recruits sit in the
    faction pool until somebody is given them, and `rules.md` still treats them
    as being with whoever is standing there.
    """
    members = [leader] + group_members(leader.id, game_state)
    member_ids = {m.id for m in members}
    total = 0

    for stack in game_state.unit_stacks.values():
        if unit_type is not None and stack.unit_type != unit_type:
            continue
        if stack.owner_character_id in member_ids:
            total += stack.count
        elif (not stack.owner_character_id
              and stack.faction_id == leader.faction_id
              and stack.location_city_id == leader.location_city_id):
            total += stack.count

    return total


# ============================================================================
# CHANGING THE TREE
# ============================================================================

def detach(character: Character) -> bool:
    """
    Make this character a group leader. True if that changed anything.

    This is what UNLOAD does explicitly and what any direct order does
    implicitly.
    """
    if not character.group_leader_id:
        return False
    character.group_leader_id = ""
    return True


def attach(character: Character, leader: Character,
           game_state: GameState) -> Optional[str]:
    """
    Assign `character` (and their group) to `leader`.

    Returns None on success, or the reason it was refused. A character cannot
    join their own group -- that would make the chain of command a circle, and
    every walk over it non-terminating.
    """
    if character.id == leader.id:
        return "cannot be assigned to themselves"

    if leader.location_city_id != character.location_city_id:
        return "they are not in the same place"

    if any(member.id == leader.id for member in group_members(character.id, game_state)):
        return f"{leader.name} is already part of their group"

    character.group_leader_id = leader.id
    return None


def move_group(leader: Character, destination_city_id: str,
               game_state: GameState,
               position: Optional[LocationPosition] = None) -> List[Character]:
    """
    Move everyone travelling with this character, and their units.

    Only members standing where the leader started come along; anyone the
    leader had already sent elsewhere stays where they are. When `position`
    is given (inside/outside/near), the whole travelling party adopts it —
    a group arrives together at the same band of the city. Returns the
    members that moved, not counting the leader.
    """
    origin = leader.location_city_id
    travelling = [m for m in group_members(leader.id, game_state)
                  if m.location_city_id == origin and not m.is_dead
                  and not m.is_prisoner]

    for member in travelling:
        member.location_city_id = destination_city_id
        if position is not None:
            member.location_position = position

    for owner in [leader] + travelling:
        for stack in owned_stacks(owner.id, game_state):
            if stack.location_city_id == origin:
                stack.location_city_id = destination_city_id

    return travelling


def describe_escort(travelled: List[Character], leader: Character,
                    game_state: GameState) -> str:
    """A short " with X and Y" clause for movement reports, or "" for nobody."""
    if not travelled:
        return ""
    names = ", ".join(m.name for m in travelled[:3])
    if len(travelled) > 3:
        names += f" and {len(travelled) - 3} more"
    return f" with {names}"
