"""
Player reporting system.

Generates per-player human-readable reports from game state and turn logs.
"""

from typing import Dict
from collections import defaultdict

from soe.models import GameState, RoadQuality
from soe import items
from soe.turn_log import TurnLog


# Preferred ordering for turn-event sections. Phases not listed here are still
# reported -- they are appended alphabetically after these.
PHASE_ORDER = [
    # The queue runs before everything else, and its "still pending" lines are
    # what a player needs to see first to know what their characters are doing.
    "queue", "groups",
    "movement", "sail", "recruit", "buy_ship", "magic", "summon", "religion",
    "combat", "capture", "prisoner", "kill", "enslave", "interrogate",
    "status", "get", "transfer", "unload", "pay", "borrow", "repay",
    "income", "tax", "trade", "secure",
    "fortify", "diplomacy", "assign", "name", "promote", "collect", "mine",
    "build", "free", "study", "teach",
    "intel", "sighting",
    # Messages and reports last: they are what the player reads for news, and
    # they describe the world as it stands after everything above has resolved.
    "message", "report",
]


def _occupied_city_ids(game_state: GameState, faction_id: str) -> set[str]:
    """Cities where this faction has someone standing, plus the ones it holds."""
    faction = game_state.factions.get(faction_id)
    here = set(faction.controlled_city_ids) if faction else set()
    for char in game_state.characters.values():
        if char.faction_id == faction_id and not char.is_dead and not char.is_prisoner:
            here.add(char.location_city_id)
    for stack in game_state.unit_stacks.values():
        if stack.faction_id == faction_id:
            here.add(stack.location_city_id)
    for ship in game_state.ships.values():
        if ship.faction_id == faction_id:
            here.add(ship.location_city_id)
    here.discard(None)
    return here


def _geography_lines(game_state: GameState, faction_id: str) -> list[str]:
    """
    The routes leading out of every city this faction occupies.

    A player's people know the roads under their feet: where each one goes, its
    condition, how far it runs and what it costs to march. Without this the map
    is only discoverable by trial and error, which in a postal game means a
    wasted turn per guess.
    """
    from soe import config, map_loader

    world_map = game_state.world_map
    lines = ["=" * 70, "THE LIE OF THE LAND", "=" * 70]

    occupied = sorted(
        (cid for cid in _occupied_city_ids(game_state, faction_id)
         if cid in world_map.cities),
        key=lambda cid: world_map.cities[cid].name,
    )
    if not occupied:
        lines.append("Nowhere to survey: you hold no ground.")
        lines.append("")
        return lines

    for city_id in occupied:
        city = world_map.cities[city_id]
        land = map_loader.landmass_name(world_map, city_id)
        where = f" -- {land}" if land else ""
        lines.append(f"\n{city.name}{where}")
        if city.terrain:
            lines.append(f"  Terrain: {', '.join(sorted(city.terrain))}")

        routes = world_map.neighbors(city_id)
        if not routes:
            lines.append("  No road or sea lane leaves this place.")
            continue
        for neighbor, road in sorted(routes, key=lambda pair: pair[0].name):
            kind = "sea lane" if road.quality == RoadQuality.SEA else f"{road.quality.value} road"
            miles = f"{road.distance_miles:g} miles, " if road.distance_miles else ""
            cost = config.get_hop_cost(road)
            one_way = "" if road.bidirectional else " (one way -- no return)"
            lines.append(
                f"  -> {neighbor.name}: {kind}, {miles}{cost:.1f} mv{one_way}"
            )

    lines.append("")
    return lines


def _authority_lines(game_state: GameState, faction_id: str) -> list[str]:
    """
    Who holds each city this faction can see, in the game's three senses.

    Sovereignty, occupation and the right to administer are different things,
    and a player who cannot tell them apart discovers the difference only when
    a TAX, RECRUIT, FORTIFY, POST or SECURE order fails. Listed for the towns
    this faction is sovereign over or has someone standing in -- the same reach
    as the rest of the fogged view, so nothing foreign leaks.
    """
    from soe import territory

    lines = ["=" * 70, "TERRITORIAL AUTHORITY", "=" * 70]
    visible = sorted(
        (cid for cid in game_state.world_map.cities
         if territory.can_see_authority(game_state, cid, faction_id)),
        key=lambda cid: game_state.world_map.cities[cid].name,
    )
    if not visible:
        lines.append("You are sovereign nowhere and stand nowhere.")
        lines.append("")
        return lines

    for city_id in visible:
        held = territory.authority_names(game_state, city_id, faction_id)
        if not held:
            continue
        city = game_state.world_map.cities[city_id]
        lines.append(f"\n{city.name}")
        lines.append(f"  Sovereign: {held['sovereign']}")
        lines.append(f"  Occupier: {held['occupier']}")
        lines.append(f"  Administrator: {held['administrator']}")
        if territory.administrative_faction_id(game_state, city_id) != faction_id:
            lines.append(
                "  You may not tax, recruit, fortify, post or secure here "
                "while another faction administers it.")

    lines.append("")
    return lines


def generate_player_reports(game_state: GameState, turn_log: TurnLog,
                            orders_by_player: Dict[str, list]) -> Dict[str, str]:
    """
    Generate per-player text reports.

    Args:
        game_state: Current game state after turn processing
        turn_log: Log of events from turn processing
        orders_by_player: Original orders submitted (for warnings)

    Returns:
        Dict mapping player_id -> report text
    """
    reports = {}

    for faction_id, faction in game_state.factions.items():
        report_lines = []

        # Header
        report_lines.append("=" * 70)
        report_lines.append(f"SPOILS OF EMPIRE - Turn {game_state.turn_number}")
        report_lines.append(f"Faction: {faction.name} ({faction_id})")
        report_lines.append("=" * 70)
        report_lines.append("")

        # Treasury & Summary
        report_lines.append("=" * 70)
        report_lines.append("FACTION SUMMARY")
        report_lines.append("=" * 70)
        total_purse = sum(
            c.gold for c in game_state.characters.values() if c.faction_id == faction_id
        )
        report_lines.append(f"Character gold (total): {total_purse:,.1f}g")
        if faction.treasury:
            report_lines.append(f"Legacy treasury: {faction.treasury:,.1f}g")
        if faction.wage_debt:
            label = "Wage debt" if faction.wage_debt > 0 else "Wage surplus"
            report_lines.append(f"{label}: {abs(faction.wage_debt):,.1f}g")
        if faction.loan_balance:
            report_lines.append(f"Bank loan: {faction.loan_balance:,.1f}g")
        # "Controlled" meant sovereignty here and read as though it also meant
        # the right to tax and recruit, which an occupier can take away.
        report_lines.append(
            f"Cities you are sovereign over: {len(faction.controlled_city_ids)}")

        if faction.controlled_city_ids:
            city_names = []
            for city_id in faction.controlled_city_ids:
                city = game_state.world_map.cities.get(city_id)
                if city:
                    city_names.append(city.name)
            report_lines.append(f"  {', '.join(city_names)}")

        report_lines.append("")

        # Characters
        report_lines.append("=" * 70)
        report_lines.append("YOUR CHARACTERS")
        report_lines.append("=" * 70)

        faction_chars = [c for c in game_state.characters.values() if c.faction_id == faction_id]

        if not faction_chars:
            report_lines.append("No characters.")
        else:
            for char in faction_chars:
                city = game_state.world_map.cities.get(char.location_city_id)
                city_name = city.name if city else "Unknown"

                flags = []
                if char.is_leader:
                    flags.append("leader")
                if char.is_noncom:
                    flags.append("noncom")
                if char.is_lurking:
                    flags.append("lurking")
                if char.is_prisoner:
                    flags.append("prisoner")
                flag_s = f" [{', '.join(flags)}]" if flags else ""
                pos = getattr(char, "location_position", None)
                pos_s = f" ({pos.value})" if pos and pos.value != "inside" else ""
                report_lines.append(f"\n{char.name} (ID: {char.id}){flag_s}")
                report_lines.append(f"  Location: {city_name}{pos_s}")
                report_lines.append(f"  Gold: {char.gold:,.1f}g")
                report_lines.append(f"  Combat Skill: {char.combat_skill}")
                report_lines.append(f"  Magic Skill: {char.magic_skill} (Power: {char.magic_power_current}/{char.max_magic_power})")
                report_lines.append(f"  Movement Points: {char.movement_points}")

                # the design shows magical items on the status report, with the
                # days remaining for anything conjured.
                held = items.items_held_by(char.id, game_state)
                if held:
                    report_lines.append("  Magical items:")
                    for item in held:
                        report_lines.append(f"    {items.describe(item, game_state)}")

        report_lines.append("")

        # Unit Stacks
        report_lines.append("=" * 70)
        report_lines.append("YOUR UNITS")
        report_lines.append("=" * 70)

        faction_stacks = [s for s in game_state.unit_stacks.values() if s.faction_id == faction_id]

        if not faction_stacks:
            report_lines.append("No units.")
        else:
            # Group by location
            stacks_by_city = defaultdict(list)
            for stack in faction_stacks:
                stacks_by_city[stack.location_city_id].append(stack)

            for city_id, stacks in stacks_by_city.items():
                city = game_state.world_map.cities.get(city_id)
                city_name = city.name if city else "Unknown"
                report_lines.append(f"\nAt {city_name}:")

                for stack in stacks:
                    report_lines.append(f"  {stack.count} {stack.unit_type.value}{'s' if stack.count > 1 else ''}")

        report_lines.append("")

        # Ships
        report_lines.append("=" * 70)
        report_lines.append("YOUR SHIPS")
        report_lines.append("=" * 70)

        faction_ships = [s for s in game_state.ships.values() if s.faction_id == faction_id]

        if not faction_ships:
            report_lines.append("No ships.")
        else:
            # Group by location
            ships_by_city = defaultdict(list)
            for ship in faction_ships:
                ships_by_city[ship.location_city_id].append(ship)

            for city_id, ships in ships_by_city.items():
                city = game_state.world_map.cities.get(city_id)
                city_name = city.name if city else "Unknown"
                report_lines.append(f"\nAt {city_name}:")
                report_lines.append(f"  {len(ships)} {ships[0].ship_type.value}{'s' if len(ships) > 1 else ''}")

        report_lines.append("")

        # Elite troop units
        report_lines.append("=" * 70)
        report_lines.append("YOUR ELITE TROOPS")
        report_lines.append("=" * 70)

        faction_elites = [u for u in game_state.elite_units.values() if u.faction_id == faction_id]

        if not faction_elites:
            report_lines.append("No elite troops.")
        else:
            for unit in faction_elites:
                city = game_state.world_map.cities.get(unit.location_city_id)
                city_name = city.name if city else "Unknown"
                leader = game_state.characters.get(unit.leader_character_id)
                leader_s = f", leader: {leader.name}" if leader else ""
                report_lines.append(f"\n{unit.name} (level {unit.combat_level}, {unit.size} soldiers){leader_s}")
                report_lines.append(f"  Location: {city_name}")

        report_lines.append("")

        # Who holds what, before the roads out of it
        report_lines.extend(_authority_lines(game_state, faction_id))

        # The lie of the land where this faction actually stands
        report_lines.extend(_geography_lines(game_state, faction_id))

        # Turn Events
        report_lines.append("=" * 70)
        report_lines.append("TURN EVENTS")
        report_lines.append("=" * 70)

        player_events = turn_log.get_player_events(faction_id)

        if not player_events:
            report_lines.append("No significant events this turn.")
        else:
            # Group by phase
            events_by_phase = defaultdict(list)
            for event in player_events:
                events_by_phase[event.phase].append(event)

            # Render every phase the engine emitted. PHASE_ORDER fixes the
            # sequence of the familiar ones; anything else follows in a stable
            # order. Listing phases explicitly used to silently drop tax,
            # trade, construction, religion and most other results from the
            # player's report.
            ordered = [p for p in PHASE_ORDER if p in events_by_phase]
            ordered += sorted(p for p in events_by_phase if p not in PHASE_ORDER)

            for phase in ordered:
                phase_name = phase.replace("_", " ").title()
                report_lines.append(f"\n{phase_name}:")

                for event in events_by_phase[phase]:
                    status = "✓" if event.success else "✗"
                    report_lines.append(f"  {status} {event.description}")

        report_lines.append("")

        # Warnings
        report_lines.append("=" * 70)
        report_lines.append("WARNINGS & ERRORS")
        report_lines.append("=" * 70)

        warnings_found = False

        # Collect warnings from orders
        if faction_id in orders_by_player:
            for order in orders_by_player[faction_id]:
                if order.warnings and not order.silent:
                    warnings_found = True
                    report_lines.append(f"\nOrder: '{order.original_text[:60]}...'")
                    for warning in order.warnings:
                        report_lines.append(f"  ⚠ {warning}")

        if not warnings_found:
            report_lines.append("No warnings.")

        report_lines.append("")
        report_lines.append("=" * 70)
        report_lines.append(f"End of Turn {game_state.turn_number} Report")
        report_lines.append("=" * 70)

        reports[faction_id] = "\n".join(report_lines)

    return reports


def generate_summary_report(game_state: GameState) -> str:
    """
    Generate a summary report showing the overall game state.

    This is useful for the GM or for debugging.

    Args:
        game_state: Current game state

    Returns:
        Summary report text
    """
    lines = []

    lines.append("=" * 70)
    lines.append(f"GAME STATE SUMMARY - Turn {game_state.turn_number}")
    lines.append("=" * 70)
    lines.append("")

    # Factions
    lines.append("FACTIONS:")
    for faction in game_state.factions.values():
        lines.append(f"  {faction.name} ({faction.id})")
        lines.append(f"    Treasury: {faction.treasury:,.1f}g")
        lines.append(f"    Cities: {len(faction.controlled_city_ids)}")
        lines.append(f"    Characters: {len([c for c in game_state.characters.values() if c.faction_id == faction.id])}")
        lines.append(f"    Units: {sum(s.count for s in game_state.unit_stacks.values() if s.faction_id == faction.id)}")
        lines.append(f"    Ships: {len([s for s in game_state.ships.values() if s.faction_id == faction.id])}")
        lines.append("")

    # Map Info
    lines.append("WORLD:")
    lines.append(f"  Cities: {len(game_state.world_map.cities)}")
    lines.append(f"  Roads/Sea Lanes: {len(game_state.world_map.roads)}")
    lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)
