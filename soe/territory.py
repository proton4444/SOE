"""Sovereignty, occupation, and city administrative authority."""

from __future__ import annotations

from soe import groups
from soe.models import Character, GameState, LocationPosition, UnitType


def has_qualifying_garrison(
    game_state: GameState,
    character: Character,
    city_id: str,
) -> bool:
    """Whether this character's local group can establish or hold occupation."""
    if (character.is_dead or character.is_prisoner
            or character.location_city_id != city_id
            or character.location_position != LocationPosition.INSIDE):
        return False

    leader = groups.leader_of(character, game_state)
    group_ids = groups.member_ids(leader, game_state)
    return any(
        stack.count > 0
        and stack.unit_type == UnitType.SOLDIER
        and stack.faction_id == character.faction_id
        and stack.location_city_id == city_id
        and (not stack.owner_character_id
             or stack.owner_character_id in group_ids)
        for stack in game_state.unit_stacks.values()
    )


def has_competing_qualifying_garrison(
    game_state: GameState,
    city_id: str,
    faction_id: str,
) -> bool:
    """
    Whether some other faction keeps its own qualifying garrison inside.

    Establishment only. A city where two factions both stand armed is
    militarily unresolved, so neither may take administrative control of it
    until one is displaced -- by combat, capture or departure, not by being
    the larger force or the first to write SECURE. Nothing here counts
    soldiers, and an allied garrison blocks exactly as an enemy one does,
    because occupation is exclusive and faction-specific.

    Says nothing about occupations that already exist: those are reconciled
    by ``is_valid_occupation``, which a newcomer does not disturb.
    """
    return any(
        character.faction_id != faction_id
        and has_qualifying_garrison(game_state, character, city_id)
        for character in game_state.characters.values()
    )


def is_valid_occupation(
    game_state: GameState,
    faction_id: str,
    city_id: str,
) -> bool:
    """Whether an existing occupation entry still has a qualifying garrison."""
    faction = game_state.factions.get(faction_id)
    if not faction or city_id not in faction.secured_city_ids:
        return False
    return any(
        character.faction_id == faction_id
        and has_qualifying_garrison(game_state, character, city_id)
        for character in game_state.characters.values()
    )


def reconcile_occupations(game_state: GameState) -> set[tuple[str, str]]:
    """Remove stale occupations without creating replacement occupations."""
    removed: set[tuple[str, str]] = set()
    occupied_cities: set[str] = set()
    for faction in game_state.factions.values():
        for city_id in list(faction.secured_city_ids):
            if (city_id in occupied_cities
                    or not is_valid_occupation(game_state, faction.id, city_id)):
                faction.secured_city_ids.remove(city_id)
                removed.add((faction.id, city_id))
                continue
            occupied_cities.add(city_id)
    return removed


def occupying_faction_id(game_state: GameState, city_id: str) -> str | None:
    """Return the valid occupier, if any, in stable faction iteration order."""
    return next((
        faction.id for faction in game_state.factions.values()
        if is_valid_occupation(game_state, faction.id, city_id)
    ), None)


def sovereign_faction_id(game_state: GameState, city_id: str) -> str | None:
    """Return the city's enduring sovereign, if the configured map has one."""
    return next((
        faction.id for faction in game_state.factions.values()
        if city_id in faction.controlled_city_ids
    ), None)


def administrative_faction_id(game_state: GameState, city_id: str) -> str | None:
    """Faction entitled to recruit, tax, fortify, and administer this city."""
    return (occupying_faction_id(game_state, city_id)
            or sovereign_faction_id(game_state, city_id))


def administrative_snapshot(game_state: GameState) -> dict[str, str | None]:
    """Freeze city authority for a nominally simultaneous resolution phase."""
    return {
        city_id: administrative_faction_id(game_state, city_id)
        for city_id in game_state.world_map.cities
    }


# ============================================================================
# TELLING THE THREE APART FOR THE PLAYER
# ============================================================================

def authority_ids(game_state: GameState, city_id: str) -> dict[str, str | None]:
    """
    The three claims on a city, kept apart.

    They are separate things and a player who cannot see the difference finds
    out only when TAX, RECRUIT, FORTIFY, POST or SECURE fails:

    * ``sovereign``     -- the enduring claim, which nothing here takes away;
    * ``occupier``      -- a faction currently holding it with a garrison;
    * ``administrator`` -- whoever may exercise the rights today, which is the
      occupier if there is one and the sovereign otherwise.

    Returns faction ids, or None where nobody holds that claim. Says nothing
    about who is entitled to know: that is the caller's business.
    """
    sovereign = sovereign_faction_id(game_state, city_id)
    occupier = occupying_faction_id(game_state, city_id)
    return {
        "sovereign": sovereign,
        "occupier": occupier,
        "administrator": occupier or sovereign,
    }


def can_see_authority(game_state: GameState, city_id: str,
                      faction_id: str) -> bool:
    """
    Whether this faction may be told who holds a city.

    The same standing as the rest of the fogged view: a faction knows the
    towns it is sovereign over and the ones where it has someone -- a living
    character, a unit stack or a ship -- on the spot. No global occupation map
    is built, and nothing here rolls for a sighting.
    """
    faction = game_state.factions.get(faction_id)
    if faction and city_id in faction.controlled_city_ids:
        return True
    for character in game_state.characters.values():
        if (character.faction_id == faction_id
                and character.location_city_id == city_id
                and not character.is_dead and not character.is_prisoner):
            return True
    for stack in game_state.unit_stacks.values():
        if stack.faction_id == faction_id and stack.location_city_id == city_id:
            return True
    for ship in game_state.ships.values():
        if ship.faction_id == faction_id and ship.location_city_id == city_id:
            return True
    return False


def administration_denial(game_state: GameState, city_id: str,
                          faction_id: str) -> str:
    """
    Why this faction may not tax, recruit or fortify here, in players' terms.

    Only ever called about a city the faction is standing in or claims, and it
    names nothing beyond who administers the place -- which is what an order
    landing there is about to be refused by anyway.
    """
    held = authority_ids(game_state, city_id)
    administrator = held["administrator"]
    if administrator is None:
        return "no faction administers it"

    faction = game_state.factions.get(administrator)
    name = faction.name if faction else administrator
    if held["occupier"] == administrator:
        if held["sovereign"] == faction_id:
            return (f"{name} occupies it, which suspends your sovereign "
                    f"rights here until the occupation lapses")
        return f"{name} occupies it and administers it"
    return f"{name} is its sovereign and administers it"


def authority_names(game_state: GameState, city_id: str,
                    faction_id: str) -> dict[str, str] | None:
    """
    Authority as display strings for one faction, or None when it cannot see.

    Unoccupied reads as "none" rather than being left out, because "nobody is
    occupying this" is the very thing a sovereign needs to know to understand
    why their own orders work.
    """
    if not can_see_authority(game_state, city_id, faction_id):
        return None

    def name_of(fid: str | None) -> str:
        if not fid:
            return "none"
        faction = game_state.factions.get(fid)
        label = faction.name if faction else fid
        return f"{label} (you)" if fid == faction_id else label

    return {key: name_of(fid)
            for key, fid in authority_ids(game_state, city_id).items()}
