"""
Map loading utilities for reading map data from JSON files.

Maps define the world geography: cities, roads, and sea lanes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from spoils_engine.config import population_band_for
from spoils_engine.models import WorldMap, City, Road, PopulationBand, RoadQuality


class MapValidationError(ValueError):
    """Raised when a map file fails structural or graph validation."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        message = "Map validation failed:\n  - " + "\n  - ".join(self.errors)
        super().__init__(message)


def load_map_from_json(map_file: Path, *, strict: bool = True) -> WorldMap:
    """
    Load a WorldMap from a JSON file.

    Expected JSON format:
    {
      "cities": [
        {
          "id": "madegi_doy",
          "name": "Madegi Doy",
          "population_band": "10k-99k",
          "population": 55000,
          "terrain": ["coastal", "plains"],
          "region": "Kyupaa",
          "is_port": true,
          "is_magic_free": false,
          "is_ruin": false,
          "grid_ref": "A6",
          "resource_richness": {"wood": 1.0},
          "fortification_level": 0,
          "x": 0.08,
          "y": 0.72
        },
        ...
      ],
      "roads": [
        {
          "id": "road_1",
          "from": "madegi_doy",
          "to": "kitesta",
          "quality": "good",
          "distance_miles": 103,
          "bidirectional": true
        },
        ...
      ]
    }

    A city's exact `population` is optional; when given it is authoritative
    and the band is derived from it (unless the map also sets
    `population_band`, which is then kept). `distance_miles` on a road is
    optional too; the engine falls back to a quality-only movement cost when
    a route has no miles.

    When ``strict`` is True (default), structural/graph errors raise
    ``MapValidationError``. Warnings (e.g. sea lane to a non-port) are never
    fatal; call ``validate_map_warnings`` to inspect them.

    Args:
        map_file: Path to JSON map file
        strict: If True, raise on validation errors

    Returns:
        WorldMap instance
    """
    map_file = Path(map_file)
    with open(map_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    world_map = WorldMap()
    load_errors: list[str] = []

    for i, city_data in enumerate(data.get("cities") or []):
        if not isinstance(city_data, dict):
            load_errors.append(f"cities[{i}]: expected object")
            continue
        city_id = city_data.get("id")
        name = city_data.get("name")
        if not city_id:
            load_errors.append(f"cities[{i}]: missing id")
            continue
        if not name:
            load_errors.append(f"city '{city_id}': missing name")
            continue
        if city_id in world_map.cities:
            load_errors.append(f"duplicate city id '{city_id}'")
            continue

        population = city_data.get("population")
        band = city_data.get("population_band")
        if population is not None and band is None:
            try:
                band = population_band_for(int(population)).value
            except (TypeError, ValueError):
                load_errors.append(f"city '{city_id}': invalid population {population!r}")
                continue
        if band is None:
            load_errors.append(
                f"city '{city_id}': need population_band or population"
            )
            continue
        try:
            pop_band = PopulationBand(band)
        except ValueError:
            load_errors.append(
                f"city '{city_id}': invalid population_band {band!r}"
            )
            continue

        richness_raw = city_data.get("resource_richness") or {}
        if not isinstance(richness_raw, dict):
            load_errors.append(f"city '{city_id}': resource_richness must be an object")
            continue
        try:
            resource_richness = {str(k): float(v) for k, v in richness_raw.items()}
        except (TypeError, ValueError):
            load_errors.append(f"city '{city_id}': invalid resource_richness values")
            continue

        fort = city_data.get("fortification_level", 0) or 0
        try:
            fortification_level = int(fort)
        except (TypeError, ValueError):
            load_errors.append(f"city '{city_id}': invalid fortification_level")
            continue

        x = city_data.get("x")
        y = city_data.get("y")
        try:
            x = float(x) if x is not None else None
            y = float(y) if y is not None else None
        except (TypeError, ValueError):
            load_errors.append(f"city '{city_id}': x/y must be numbers")
            continue

        if population is not None:
            try:
                population = int(population)
            except (TypeError, ValueError):
                load_errors.append(f"city '{city_id}': invalid population")
                continue

        city = City(
            id=str(city_id),
            name=str(name),
            population_band=pop_band,
            terrain=set(city_data.get("terrain") or []),
            region=city_data.get("region"),
            is_port=bool(city_data.get("is_port", False)),
            is_magic_free=bool(city_data.get("is_magic_free", False)),
            is_ruin=bool(city_data.get("is_ruin", False)),
            grid_ref=city_data.get("grid_ref"),
            population=population,
            fortification_level=fortification_level,
            resource_richness=resource_richness,
            x=x,
            y=y,
        )
        world_map.cities[city.id] = city

    for i, road_data in enumerate(data.get("roads") or []):
        if not isinstance(road_data, dict):
            load_errors.append(f"roads[{i}]: expected object")
            continue
        road_id = road_data.get("id")
        if not road_id:
            load_errors.append(f"roads[{i}]: missing id")
            continue
        if road_id in world_map.roads:
            load_errors.append(f"duplicate road id '{road_id}'")
            continue
        from_id = road_data.get("from")
        to_id = road_data.get("to")
        quality_raw = road_data.get("quality")
        if not from_id or not to_id:
            load_errors.append(f"road '{road_id}': missing from/to")
            continue
        try:
            quality = RoadQuality(quality_raw)
        except ValueError:
            load_errors.append(
                f"road '{road_id}': invalid quality {quality_raw!r}"
            )
            continue

        miles = road_data.get("distance_miles")
        if miles is not None:
            try:
                miles = float(miles)
            except (TypeError, ValueError):
                load_errors.append(f"road '{road_id}': invalid distance_miles")
                continue

        road = Road(
            id=str(road_id),
            from_city_id=str(from_id),
            to_city_id=str(to_id),
            quality=quality,
            bidirectional=bool(road_data.get("bidirectional", True)),
            distance_miles=miles,
        )
        world_map.roads[road.id] = road

    graph_errors = validate_map(world_map)
    all_errors = load_errors + graph_errors
    if all_errors and strict:
        raise MapValidationError(all_errors)
    return world_map


def validate_map(world_map: WorldMap) -> list[str]:
    """
    Structural/graph checks that must pass for a playable map.

    Returns a list of error messages; empty means the map is usable.
    Soft issues (sea lanes touching non-ports) are not included — use
    ``validate_map_warnings`` for those.
    """
    errors: list[str] = []

    if not world_map.cities:
        errors.append("map has no cities")
        return errors

    city_ids = set(world_map.cities.keys())
    for road in world_map.roads.values():
        if road.from_city_id not in city_ids:
            errors.append(
                f"road '{road.id}': from city '{road.from_city_id}' does not exist"
            )
        if road.to_city_id not in city_ids:
            errors.append(
                f"road '{road.id}': to city '{road.to_city_id}' does not exist"
            )
        if road.distance_miles is not None and road.distance_miles < 0:
            errors.append(f"road '{road.id}': distance_miles must be >= 0")

    for city in world_map.cities.values():
        if not city.name or not str(city.name).strip():
            errors.append(f"city '{city.id}': empty name")
        if city.x is not None and not (0.0 <= city.x <= 1.0):
            errors.append(f"city '{city.id}': x should be in 0..1 (got {city.x})")
        if city.y is not None and not (0.0 <= city.y <= 1.0):
            errors.append(f"city '{city.id}': y should be in 0..1 (got {city.y})")
        if city.fortification_level < 0 or city.fortification_level > 100:
            errors.append(
                f"city '{city.id}': fortification_level must be 0..100 "
                f"(got {city.fortification_level})"
            )

    return errors


# ============================================================================
# CONNECTIVITY
# ============================================================================
#
# Movement resolves over the roads graph (see phases/pathing.py), and land and
# sea are disjoint networks there: a marching army may not cross a sea lane and
# a ship may not sail up a road. The helpers below expose that same geography
# to map authors and to game setup, so an unreachable start city is caught
# before a turn is resolved rather than as a "No path found" order failure.
#
# Membership here is symmetric -- a one-way road still puts both ends on the
# same landmass, even though only one direction is traversable. Directed
# one-way routes are flagged as an authoring warning instead.


def _adjacency(world_map: WorldMap, *, land_only: bool) -> dict[str, set[str]]:
    """Symmetric neighbour sets over the route graph."""
    adjacency: dict[str, set[str]] = {cid: set() for cid in world_map.cities}
    for road in world_map.roads.values():
        if land_only and road.quality == RoadQuality.SEA:
            continue
        start, end = road.from_city_id, road.to_city_id
        if start not in adjacency or end not in adjacency:
            continue  # dangling endpoint: validate_map reports it as an error
        adjacency[start].add(end)
        adjacency[end].add(start)
    return adjacency


def _components(adjacency: dict[str, set[str]], order: list[str]) -> list[set[str]]:
    """Connected components, largest first; ties broken by map order."""
    seen: set[str] = set()
    components: list[set[str]] = []
    for city_id in order:
        if city_id in seen:
            continue
        component = {city_id}
        frontier = [city_id]
        seen.add(city_id)
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    component.add(neighbor)
                    frontier.append(neighbor)
        components.append(component)
    components.sort(key=lambda c: (-len(c), order.index(min(c, key=order.index))))
    return components


def land_components(world_map: WorldMap) -> list[set[str]]:
    """
    The map's landmasses: city sets joined by land roads, sea lanes excluded.

    Largest first. A one-city component is an island with a single settlement.
    """
    order = list(world_map.cities.keys())
    return _components(_adjacency(world_map, land_only=True), order)


def landmass_index(world_map: WorldMap) -> dict[str, int]:
    """
    city_id -> landmass number, 1 for the largest. Stable for a given map.

    Lets the engine and the turn reports talk about which body of land a city
    sits on without trusting the hand-written `region` label.
    """
    index: dict[str, int] = {}
    for number, mass in enumerate(land_components(world_map), start=1):
        for city_id in mass:
            index[city_id] = number
    return index


def landmass_name(world_map: WorldMap, city_id: str) -> Optional[str]:
    """
    The best available name for the land a city sits on.

    Prefers the author's `region` when every city sharing that label is on the
    same landmass; otherwise falls back to a generated name, so a mislabelled
    map never puts a wrong place name in a player's report.
    """
    city = world_map.cities.get(city_id)
    if city is None:
        return None
    index = landmass_index(world_map)
    number = index.get(city_id)
    if city.region:
        same_label = [
            other.id for other in world_map.cities.values()
            if other.region == city.region
        ]
        if all(index.get(other) == number for other in same_label):
            return city.region
    masses = land_components(world_map)
    if number is None:
        return None
    size = len(masses[number - 1])
    kind = "Island" if size == 1 else "Landmass"
    return f"{kind} {number}"


def isolated_cities(world_map: WorldMap) -> list[str]:
    """Cities with no road and no sea lane at all -- nobody can ever reach them."""
    adjacency = _adjacency(world_map, land_only=False)
    return [cid for cid in world_map.cities if not adjacency[cid]]


def mutually_reachable_cities(world_map: WorldMap) -> list[str]:
    """
    The largest set of cities that can all reach each other, in map order.

    Uses the whole route network (roads and sea lanes), because a landlocked
    faction can still build ships at a port. Game setup draws start cities from
    this pool so no player begins marooned from the rest of the game.
    """
    order = list(world_map.cities.keys())
    if not order:
        return []
    components = _components(_adjacency(world_map, land_only=False), order)
    largest = components[0]

    # Within the component, keep only cities in mutual reach of the anchor:
    # with one-way roads a component can be entered without being escapable.
    anchor = min(largest, key=order.index)
    forward = _directed_reach(world_map, anchor, reverse=False)
    backward = _directed_reach(world_map, anchor, reverse=True)
    pool = largest & forward & backward
    return [cid for cid in order if cid in pool]


def _directed_reach(world_map: WorldMap, start_city_id: str, *, reverse: bool) -> set[str]:
    """Cities reachable from (or reaching) a start, honouring one-way roads."""
    adjacency: dict[str, set[str]] = {cid: set() for cid in world_map.cities}
    for road in world_map.roads.values():
        start, end = road.from_city_id, road.to_city_id
        if start not in adjacency or end not in adjacency:
            continue
        if reverse:
            adjacency[end].add(start)
            if road.bidirectional:
                adjacency[start].add(end)
        else:
            adjacency[start].add(end)
            if road.bidirectional:
                adjacency[end].add(start)

    seen = {start_city_id}
    frontier = [start_city_id]
    while frontier:
        for neighbor in adjacency[frontier.pop()]:
            if neighbor not in seen:
                seen.add(neighbor)
                frontier.append(neighbor)
    return seen


def validate_map_warnings(world_map: WorldMap) -> list[str]:
    """Non-fatal authoring hints (sea lanes without ports, missing miles, etc.)."""
    warnings: list[str] = []
    for road in world_map.roads.values():
        if not road.bidirectional:
            warnings.append(
                f"road '{road.id}': one-way ('{road.from_city_id}' -> "
                f"'{road.to_city_id}'); the return trip is not traversable"
            )
        if road.quality != RoadQuality.SEA:
            continue
        for end_id, label in (
            (road.from_city_id, "from"),
            (road.to_city_id, "to"),
        ):
            city = world_map.cities.get(end_id)
            if city is not None and not city.is_port:
                warnings.append(
                    f"road '{road.id}': sea lane {label} city "
                    f"'{end_id}' is not a port"
                )
        if road.distance_miles is None:
            warnings.append(f"road '{road.id}': sea lane has no distance_miles")

    for city_id in isolated_cities(world_map):
        warnings.append(
            f"city '{city_id}': no road or sea lane -- unreachable, and anyone "
            f"starting there is stranded"
        )

    # `region` is the author's word for a body of land; the road graph is the
    # truth. Where they disagree the label is a trap for anyone reading the map.
    index = landmass_index(world_map)
    by_region: dict[str, set[int]] = {}
    for city in world_map.cities.values():
        if city.region:
            by_region.setdefault(city.region, set()).add(index.get(city.id, 0))
    for region, numbers in sorted(by_region.items()):
        if len(numbers) > 1:
            warnings.append(
                f"region '{region}': spans {len(numbers)} landmasses that no "
                f"land road joins -- the label claims one body of land"
            )

    # A landmass with no sea lane off it is sealed: its cities can never trade
    # blows with the rest of the map, whatever ships get built.
    masses = land_components(world_map)
    if len(masses) > 1:
        stranded = set(isolated_cities(world_map))
        for mass in masses:
            if mass <= stranded:
                continue  # already reported, one line per city, above
            has_sea_link = any(
                road.quality == RoadQuality.SEA
                and (road.from_city_id in mass) != (road.to_city_id in mass)
                for road in world_map.roads.values()
            )
            if not has_sea_link:
                sample = ", ".join(sorted(mass)[:4])
                more = "" if len(mass) <= 4 else f", +{len(mass) - 4} more"
                warnings.append(
                    f"landmass ({sample}{more}): no sea lane connects it to the "
                    f"rest of the map"
                )
    return warnings


def create_sample_map() -> WorldMap:
    """
    Create a small sample map for testing and demos.

    This map has 5 cities connected by roads and sea lanes,
    suitable for 2-3 player games.
    """
    world_map = WorldMap()

    # Layout and mileages stay in step with maps/sample_map.json: west→east
    # letters, north→south numbers, hop costs tuned so neighbors are walkable.
    cities_data = [
        {
            "id": "madegi_doy",
            "name": "Madegi Doy",
            "population_band": PopulationBand.LARGE,
            "population": 1_200_000,
            "terrain": {"coastal", "plains"},
            "region": "Main Continent",
            "is_port": True,
            "grid_ref": "B8",
            "x": 0.12,
            "y": 0.78,
        },
        {
            "id": "kitesta",
            "name": "Kitesta",
            "population_band": PopulationBand.MEDIUM,
            "population": 420_000,
            "terrain": {"plains", "river"},
            "region": "Main Continent",
            "is_port": False,
            "grid_ref": "F5",
            "x": 0.48,
            "y": 0.48,
        },
        {
            "id": "riverton",
            "name": "Riverton",
            "population_band": PopulationBand.SMALL,
            "population": 45_000,
            "terrain": {"forest", "river"},
            "region": "Main Continent",
            "is_port": False,
            "grid_ref": "H3",
            "resource_richness": {"wood": 1.0},
            "x": 0.70,
            "y": 0.28,
        },
        {
            "id": "albatross_city",
            "name": "Albatross City",
            "population_band": PopulationBand.MEDIUM,
            "population": 280_000,
            "terrain": {"coastal", "mountains"},
            "region": "Northern Island",
            "is_port": True,
            "grid_ref": "K2",
            "x": 0.88,
            "y": 0.12,
        },
        {
            "id": "peshandi",
            "name": "Peshandi",
            "population_band": PopulationBand.TINY,
            "population": 6_800,
            "terrain": {"desert"},
            "region": "Main Continent",
            "is_port": False,
            "is_magic_free": True,
            "grid_ref": "D2",
            "x": 0.28,
            "y": 0.16,
        },
        {
            "id": "hakkaba",
            "name": "Hakkaba",
            "population_band": PopulationBand.TINY,
            "population": 0,
            "terrain": {"mountains"},
            "region": "Main Continent",
            "is_ruin": True,
            "grid_ref": "G6",
            "x": 0.55,
            "y": 0.55,
        },
    ]

    for city_data in cities_data:
        city = City(**city_data)
        world_map.cities[city.id] = city

    roads_data = [
        {
            "id": "road_1",
            "from_city_id": "madegi_doy",
            "to_city_id": "kitesta",
            "quality": RoadQuality.EXCELLENT,
            "bidirectional": True,
            "distance_miles": 94,
        },
        {
            "id": "road_2",
            "from_city_id": "kitesta",
            "to_city_id": "riverton",
            "quality": RoadQuality.FAIR,
            "bidirectional": True,
            "distance_miles": 59,
        },
        {
            "id": "road_3",
            "from_city_id": "riverton",
            "to_city_id": "peshandi",
            "quality": RoadQuality.POOR,
            "bidirectional": True,
            "distance_miles": 102,
        },
        {
            "id": "road_4",
            "from_city_id": "peshandi",
            "to_city_id": "madegi_doy",
            "quality": RoadQuality.FAIR,
            "bidirectional": True,
            "distance_miles": 92,
        },
        {
            "id": "road_5",
            "from_city_id": "kitesta",
            "to_city_id": "hakkaba",
            "quality": RoadQuality.POOR,
            "bidirectional": True,
            "distance_miles": 20,
        },
        {
            "id": "sea_1",
            "from_city_id": "madegi_doy",
            "to_city_id": "albatross_city",
            "quality": RoadQuality.SEA,
            "bidirectional": True,
            "distance_miles": 201,
        },
    ]

    for road_data in roads_data:
        road = Road(**road_data)
        world_map.roads[road.id] = road

    return world_map


def save_map_to_json(world_map: WorldMap, map_file: Path) -> None:
    """
    Save a WorldMap to a JSON file.

    Preserves presentation coordinates, ruin flags, resource richness and
    starting fortification when set.
    """
    data = {"cities": [], "roads": []}

    for city in world_map.cities.values():
        entry = {
            "id": city.id,
            "name": city.name,
            "population_band": city.population_band.value,
            "population": city.population,
            "terrain": sorted(city.terrain),
            "region": city.region,
            "is_port": city.is_port,
            "is_magic_free": city.is_magic_free,
            "is_ruin": city.is_ruin,
            "grid_ref": city.grid_ref,
            "fortification_level": city.fortification_level,
            "resource_richness": dict(city.resource_richness),
        }
        if city.x is not None:
            entry["x"] = city.x
        if city.y is not None:
            entry["y"] = city.y
        data["cities"].append(entry)

    for road in world_map.roads.values():
        data["roads"].append({
            "id": road.id,
            "from": road.from_city_id,
            "to": road.to_city_id,
            "quality": road.quality.value,
            "bidirectional": road.bidirectional,
            "distance_miles": road.distance_miles,
        })

    map_file = Path(map_file)
    map_file.parent.mkdir(parents=True, exist_ok=True)
    with open(map_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
