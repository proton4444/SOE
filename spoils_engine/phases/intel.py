"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from typing import Dict, List

from spoils_engine.models import (
    GameState, LocationPosition, ItemType,
)
from spoils_engine.orders import (
    Order, ProbeOrder, SearchOrder, ScanOrder,
)
from spoils_engine import config, fog, groups, items
from spoils_engine.turn_log import TurnLog
from spoils_engine.phases.pathing import (
    find_route,
)


def process_probe(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                  turn_log: TurnLog, rng: random.Random):
    """
    Magically report on another player's character.

    rules.md: costs 25 power always; success chance = caster magic skill %;
    target resists with effective skill %; on resist the target is told an
    attempt was made but not by whom.
    """
    PROBE_COST = 25
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ProbeOrder) or order.warnings:
                continue
            caster = game_state.characters.get(order.actor_id)
            target = game_state.characters.get(order.target_id)
            if not caster or not target:
                turn_log.add("intel", player_id, "probe_failed",
                            "PROBE: caster or target missing", success=False)
                continue
            error = items.pay_for_spell(caster, PROBE_COST, "probe",
                                        order.wand_name, game_state)
            if error:
                turn_log.add("intel", player_id, "probe_failed",
                            f"{caster.name} cannot probe: {error}",
                            character_id=caster.id, success=False)
                continue
            # Base success: magic skill as a percentage. A wand casts at its
            # own skill level, since it supplies the skill as well as the power.
            wand = (items.find_item_by_name(order.wand_name, game_state)
                    if order.wand_name else None)
            cast_skill = wand.skill_level if wand else caster.magic_skill
            success_roll = rng.random() * 100.0
            if success_roll >= cast_skill:
                turn_log.add("intel", player_id, "probe_failed",
                            f"{caster.name} failed to probe {target.name} "
                            f"(magic skill {cast_skill})",
                            character_id=caster.id, success=False)
                continue

            resist = fog.effective_skill_level(target)
            if rng.random() * 100.0 < resist:
                turn_log.add("intel", player_id, "probe_resisted",
                            f"{caster.name}'s probe of {target.name} was resisted",
                            character_id=caster.id, success=False)
                # Target learns only that an attempt was made.
                turn_log.add("intel", target.faction_id, "probe_detected",
                            f"{target.name} felt a magical probe attempt",
                            character_id=target.id, success=True)
                continue

            city = game_state.world_map.cities.get(target.location_city_id)
            city_name = city.name if city else "unknown"
            pos = target.location_position.value
            soldiers = groups.group_soldier_count(target, game_state)
            report = (
                f"{caster.name} probed {target.name}: at {city_name} ({pos}), "
                f"combat {target.combat_skill}, magic {target.magic_skill}, "
                f"religion {target.religion_skill}, trading {target.trading_skill}, "
                f"health {target.health}, gold {target.gold:.0f}, "
                f"~{soldiers} soldiers in their group"
                f"{', lurking' if target.is_lurking else ''}"
            )
            turn_log.add("intel", player_id, "probe", report,
                        location=target.location_city_id, character_id=caster.id)


def process_search(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog, rng: random.Random):
    """
    SEARCH/EXPLORE uninhabited ruins at the actor's current location.

    rules.md: must be *inside* a ruin; outside/near and inhabited cities find
    nothing. A successful dig turns up one of the enchantress's magical items,
    which lasts forever, and the chance scales with how long the dig ran.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SearchOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            if actor.location_position != LocationPosition.INSIDE:
                turn_log.add("intel", player_id, "search_failed",
                            f"{actor.name} must be inside the ruins to search "
                            f"(currently {actor.location_position.value})",
                            character_id=actor.id, location=city.id, success=False)
                continue
            if not city.is_ruin:
                turn_log.add("intel", player_id, "search_failed",
                            f"{actor.name} found nothing of value at {city.name} "
                            f"(not uninhabited ruins)",
                            character_id=actor.id, location=city.id, success=False)
                continue

            # Longer searches help a little, up to a ceiling: no amount of
            # digging guarantees a ruin still has anything left in it.
            days = max(1, order.duration_days)
            chance = min(config.RUIN_ITEM_MAX_CHANCE,
                        config.RUIN_ITEM_BASE_CHANCE
                        + config.RUIN_ITEM_CHANCE_PER_DAY * min(days, 30))
            if rng.random() < chance:
                kinds = sorted(config.RUIN_ITEM_WEIGHTS)
                kind = rng.choices(
                    kinds, weights=[config.RUIN_ITEM_WEIGHTS[k] for k in kinds]
                )[0]
                # Found items are permanent: expires_turn stays -1.
                found = items.make_item(game_state, rng, ItemType(kind),
                                        holder_id=actor.id)
                turn_log.add("intel", player_id, "search",
                            f"{actor.name} searched the ruins of {city.name} "
                            f"and found {items.describe(found, game_state)}",
                            character_id=actor.id, location=city.id)
            else:
                turn_log.add("intel", player_id, "search",
                            f"{actor.name} searched the ruins of {city.name} "
                            f"and found nothing",
                            character_id=actor.id, location=city.id)


def orb_scan_cost(from_city_id: str, to_city_id: str, game_state: GameState) -> int:
    """
    Power an orb spends to reach a location.

    rules.md prices a scan at "one point of power ... for each ten miles of
    distance between the user of the orb and the location being scanned".

    An orb is a crystal ball, not a courier: it does not follow roads, so the
    distance is measured over the whole map -- roads and sea lanes alike --
    rather than overland only. Without that, an island reachable only by sea
    could not be scanned at all. The map's own mileages are the best distance
    the engine has; where a leg carries none, the route's movement cost stands
    in and `ORB_POWER_PER_HOP` converts it. Returns -1 when no route exists.
    """
    if from_city_id == to_city_id:
        return 0
    route = find_route(from_city_id, to_city_id, game_state,
                       allow_land=True, allow_sea=True)
    if not route:
        return -1
    miles = route.miles(game_state)
    if miles is not None:
        return max(1, int(round(miles / 10)))
    return max(1, int(round(route.cost * config.ORB_POWER_PER_HOP)))


def process_scan(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                 turn_log: TurnLog):
    """
    SCAN a distant city with a magical orb.

    rules.md: the orb must be named in the order and held by the actor. It
    spends its own power — never the caster's, never a crystal's — at a rate
    set by the distance. The report is complete, unlike REPORT/QUERY: everyone
    of note is detected whether or not they are lurking. But an orb "will only
    tell you who is inside or outside a town or city. It cannot be used to scan
    people near the town", and it cannot see monsters.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ScanOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            if not order.orb_name:
                turn_log.add("intel", player_id, "scan_failed",
                            f"{actor.name} must name the orb to SCAN with "
                            f"(e.g. 'scan Kitesta using *Anomba*')",
                            character_id=actor.id, success=False)
                continue

            orb = items.find_item_by_name(order.orb_name, game_state)
            if not orb or orb.item_type != ItemType.ORB:
                turn_log.add("intel", player_id, "scan_failed",
                            f"{actor.name} has no magical orb called "
                            f"{order.orb_name}",
                            character_id=actor.id, success=False)
                continue
            if orb.holder_character_id != actor.id:
                turn_log.add("intel", player_id, "scan_failed",
                            f"{actor.name} does not possess {orb.name}",
                            character_id=actor.id, success=False)
                continue

            for city_id, city_name in zip(order.city_ids, order.city_names):
                cost = orb_scan_cost(actor.location_city_id, city_id, game_state)
                if cost < 0:
                    turn_log.add("intel", player_id, "scan_failed",
                                f"{orb.name} cannot reach {city_name}: no route "
                                f"from {actor.name}'s location",
                                character_id=actor.id, success=False)
                    continue
                if orb.power_current < cost:
                    turn_log.add("intel", player_id, "scan_failed",
                                f"{orb.name} has {orb.power_current} power, not "
                                f"the {cost} needed to reach {city_name}",
                                character_id=actor.id, success=False)
                    continue

                orb.power_current -= cost
                seen = [
                    c for c in game_state.characters.values()
                    if c.location_city_id == city_id and not c.is_dead
                    and c.location_position != LocationPosition.NEAR
                ]
                if seen:
                    who = ", ".join(
                        f"{c.name} ({c.location_position.value})"
                        for c in sorted(seen, key=lambda c: c.name)
                    )
                    detail = f"sees {who}"
                else:
                    detail = "sees nobody"
                turn_log.add("intel", player_id, "scan",
                            f"{actor.name} scans {city_name} with {orb.name} "
                            f"({cost} power): {detail}",
                            character_id=actor.id, location=city_id)

def process_sightings(game_state: GameState, turn_log: TurnLog, rng: random.Random):
    """
    End-of-turn fog of war: each faction's living characters try to notice
    others at the same city under the position and LURK rules.
    """
    for faction_id in sorted(game_state.factions.keys()):
        # Independent stream per faction so adding a player does not reshuffle
        # everyone else's sightings under the same turn seed.
        faction_rng = random.Random(rng.randint(0, 2**31 - 1))
        for sighting in fog.collect_sightings(game_state, faction_id, faction_rng):
            turn_log.add(
                "sighting",
                faction_id,
                "spotted",
                fog.format_sighting(sighting),
                location=sighting.city_id,
                character_id=sighting.observer_id,
            )

