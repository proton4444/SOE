"""
Fog of war: who can see whom.

the design ties visibility to position (inside / outside / near a city) and to
stealth (LURK). A character that is inside a location sees many of the people
also inside and everyone outside; they do not see people near. Outside sees
only outside. Near sees near (rarely) and outside, never inside.

LURK multiplies the chance of detection by 1/4. Group size works against
stealth: a large retinue is harder to hide in a crowd.

This module answers pure questions ("would A notice B?") and is called from
the end-of-turn sightings phase and from reports. Magical reconnaissance
(PROBE, SCAN once orbs exist) bypasses these rules and is handled by the
engine phases that cast those spells.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Set, Tuple

from soe.models import (
    Character,
    City,
    GameState,
    LocationPosition,
    PopulationBand,
)


# Base chance that a non-lurking person is noticed by someone who can see their
# position band. Larger cities make blending in easier.
_BASE_NOTICE: dict[PopulationBand, float] = {
    PopulationBand.TINY: 0.90,
    PopulationBand.SMALL: 0.70,
    PopulationBand.MEDIUM: 0.50,
    PopulationBand.LARGE: 0.30,
}

# Design: people near a location have "very slim" chance of being seen by
# other people also near the same location.
_NEAR_VS_NEAR_FACTOR = 0.10

# Design: "the chance of detection of a lurking individual or group will be
# reduced by a factor of 4."
_LURK_FACTOR = 0.25

# Each named person in the target's group (beyond the first) and every 20
# soldiers adds this much to the notice chance before the LURK factor.
_GROUP_SIZE_PENALTY = 0.05
_SOLDIERS_PER_PENALTY = 20


# ============================================================================
# POSITION MATRIX
# ============================================================================

def can_see_position(observer: LocationPosition,
                     target: LocationPosition) -> bool:
    """
    Whether someone at `observer` can ever notice someone at `target`.

    Design (paraphrased):
      inside  -> inside, outside       (not near)
      outside -> outside               (not inside, not near; securer exception later)
      near    -> near, outside         (not inside)
    """
    if observer == LocationPosition.INSIDE:
        return target in (LocationPosition.INSIDE, LocationPosition.OUTSIDE)
    if observer == LocationPosition.OUTSIDE:
        return target == LocationPosition.OUTSIDE
    if observer == LocationPosition.NEAR:
        return target in (LocationPosition.NEAR, LocationPosition.OUTSIDE)
    return False


def parse_position_prefix(text: str) -> Tuple[LocationPosition, str]:
    """
    Strip a leading "inside"/"outside"/"near" from a place phrase.

    "outside Highfell" -> (OUTSIDE, "Highfell")
    "Ashford"           -> (INSIDE, "Ashford")
    """
    cleaned = (text or "").strip()
    lower = cleaned.lower()
    for word, pos in (
        ("outside", LocationPosition.OUTSIDE),
        ("near", LocationPosition.NEAR),
        ("inside", LocationPosition.INSIDE),
    ):
        if lower.startswith(word + " "):
            return pos, cleaned[len(word):].strip()
        if lower == word:
            return pos, ""
    return LocationPosition.INSIDE, cleaned


# ============================================================================
# DETECTION ODDS
# ============================================================================

def group_size_for_stealth(character: Character, game_state: GameState) -> int:
    """
    How many bodies travel with this character for LURK difficulty.

    Named members of their group count as one each; soldiers under the group
    count toward bulk. Uses the groups module when available so subordinates'
    units are included.
    """
    from soe import groups

    members = [character] + groups.group_members(character.id, game_state)
    named = sum(1 for m in members if not m.is_dead and not m.is_prisoner)
    soldiers = groups.group_soldier_count(character, game_state)
    # Cap soldiers so a 500-man army does not push the chance above 1.0 via
    # size alone before the LURK factor is applied.
    return named + min(soldiers, 200) // _SOLDIERS_PER_PENALTY


def notice_chance(observer: Character, target: Character, city: City,
                  game_state: GameState) -> float:
    """
    Probability that `observer` notices `target` this turn, 0..1.

    Returns 0 when the position matrix forbids any contact, or when the two
    are not co-located / not alive / same faction.
    """
    if observer.id == target.id:
        return 0.0
    if observer.faction_id == target.faction_id:
        return 0.0
    if observer.is_dead or target.is_dead:
        return 0.0
    if observer.is_prisoner:
        return 0.0  # Prisoners do not scout for their captors here.
    if observer.location_city_id != target.location_city_id:
        return 0.0
    if not can_see_position(observer.location_position, target.location_position):
        return 0.0

    base = _BASE_NOTICE.get(city.population_band, 0.50)

    # Inside-to-inside is "many of the people", not all. Outside-to-outside and
    # inside-to-outside are complete for non-lurkers (rules: "all the people
    # that are outside"). Model that as base for same-band-inside, 1.0 for the
    # clear-sight pairs, then apply LURK and size.
    clear_sight = (
        observer.location_position == LocationPosition.INSIDE
        and target.location_position == LocationPosition.OUTSIDE
    ) or (
        observer.location_position == LocationPosition.OUTSIDE
        and target.location_position == LocationPosition.OUTSIDE
    ) or (
        observer.location_position == LocationPosition.NEAR
        and target.location_position == LocationPosition.OUTSIDE
    )
    chance = 1.0 if clear_sight else base

    if (observer.location_position == LocationPosition.NEAR
            and target.location_position == LocationPosition.NEAR):
        chance = base * _NEAR_VS_NEAR_FACTOR

    size = group_size_for_stealth(target, game_state)
    if size > 1:
        chance = min(1.0, chance + (size - 1) * _GROUP_SIZE_PENALTY)

    # A securer of the city is always visible to people outside (rules).
    if _is_securer(target, city, game_state) and observer.location_position == LocationPosition.OUTSIDE:
        chance = 1.0

    if target.is_lurking:
        chance *= _LURK_FACTOR

    return max(0.0, min(1.0, chance))


def _is_securer(character: Character, city: City, game_state: GameState) -> bool:
    """True when this character's faction holds the city as secured."""
    faction = game_state.factions.get(character.faction_id)
    if not faction:
        return False
    return city.id in faction.secured_city_ids


def detects(observer: Character, target: Character, city: City,
            game_state: GameState, rng: random.Random) -> bool:
    """Roll whether observer notices target this turn."""
    chance = notice_chance(observer, target, city, game_state)
    if chance <= 0.0:
        return False
    if chance >= 1.0:
        return True
    return rng.random() < chance


# ============================================================================
# SIGHTINGS
# ============================================================================

@dataclass(frozen=True)
class Sighting:
    """One detected character (and optional unit count) at a city."""
    observer_id: str
    observer_name: str
    target_id: str
    target_name: str
    target_faction_id: str
    city_id: str
    city_name: str
    position: LocationPosition
    is_lurking: bool
    title: str = ""
    soldiers: int = 0


def effective_skill_level(character: Character) -> float:
    """
    Design: effective skill = sqrt(sum of squares of all skill levels).

    Used by PROBE resistance and similar opposed magic checks.
    """
    skills = (
        character.combat_skill,
        character.magic_skill,
        character.religion_skill,
        character.trading_skill,
    )
    return math.sqrt(sum(s * s for s in skills if s > 0))


def collect_sightings(game_state: GameState, faction_id: str,
                      rng: random.Random) -> List[Sighting]:
    """
    Characters of other factions that this faction's people notice this turn.

    At most one Sighting per target: the first observer who spots them wins the
    credit line. Soldiers with the target's group are summarised on that line.
    """
    from soe import groups

    observers = [
        c for c in game_state.characters.values()
        if c.faction_id == faction_id and not c.is_dead and not c.is_prisoner
    ]
    if not observers:
        return []

    others = [
        c for c in game_state.characters.values()
        if c.faction_id != faction_id and not c.is_dead
    ]

    seen_targets: Set[str] = set()
    sightings: List[Sighting] = []

    # Stable order so the same seed always credits the same observer first.
    observers.sort(key=lambda c: c.id)
    others.sort(key=lambda c: c.id)

    for target in others:
        if target.id in seen_targets:
            continue
        city = game_state.world_map.cities.get(target.location_city_id)
        if not city:
            continue
        for observer in observers:
            if detects(observer, target, city, game_state, rng):
                soldiers = groups.group_soldier_count(target, game_state)
                sightings.append(Sighting(
                    observer_id=observer.id,
                    observer_name=observer.name,
                    target_id=target.id,
                    target_name=target.name,
                    target_faction_id=target.faction_id,
                    city_id=city.id,
                    city_name=city.name,
                    position=target.location_position,
                    is_lurking=target.is_lurking,
                    title=target.title or "",
                    soldiers=soldiers,
                ))
                seen_targets.add(target.id)
                break

    return sightings


def format_sighting(s: Sighting) -> str:
    """One turn-report line for a detected character."""
    title = f"{s.title} " if s.title else ""
    pos = s.position.value
    lurk = ", lurking" if s.is_lurking else ""
    troops = f" with ~{s.soldiers} soldiers" if s.soldiers else ""
    return (
        f"{s.observer_name} spotted {title}{s.target_name} "
        f"{pos} {s.city_name}{troops}{lurk}"
    )
