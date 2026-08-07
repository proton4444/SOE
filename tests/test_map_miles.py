"""
Tests for map data matching the original SOE map index: exact population,
grid references, magic-free flags and route mileages, and the miles-based
pricing of movement, TELEPORT and orb SCAN.
"""

import json
from pathlib import Path
import random
import sys

import pytest

from spoils_engine import config, engine, models
from spoils_engine.map_loader import (
    MapValidationError,
    create_sample_map,
    isolated_cities,
    land_components,
    landmass_index,
    landmass_name,
    mutually_reachable_cities,
    load_map_from_json,
    save_map_to_json,
    validate_map,
    validate_map_warnings,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def miles_state():
    """Three cities on roads with mileages, one magic-free, one with an exact
    population, and one island reached only by sea."""
    gs = models.GameState()
    gs.world_map.cities["town"] = models.City(
        id="town", name="Agnok", population_band=models.PopulationBand.SMALL,
        population=59_000, terrain={"plains"}, grid_ref="A6", is_magic_free=True)
    gs.world_map.cities["city"] = models.City(
        id="city", name="Kitesta", population_band=models.PopulationBand.MEDIUM,
        population=420_000, terrain={"plains", "river"}, grid_ref="F5")
    gs.world_map.cities["ruin"] = models.City(
        id="ruin", name="Ruin", population_band=models.PopulationBand.TINY)
    gs.world_map.cities["isle"] = models.City(
        id="isle", name="Albatross City", population_band=models.PopulationBand.MEDIUM, is_port=True)
    gs.world_map.roads["r1"] = models.Road(
        id="r1", from_city_id="town", to_city_id="city",
        quality=models.RoadQuality.GOOD, distance_miles=103)
    gs.world_map.roads["r2"] = models.Road(
        id="r2", from_city_id="city", to_city_id="ruin",
        quality=models.RoadQuality.POOR, distance_miles=97)
    gs.world_map.roads["s1"] = models.Road(
        id="s1", from_city_id="town", to_city_id="isle",
        quality=models.RoadQuality.SEA, distance_miles=342)
    return gs


# ============================================================================
# MAP FILE FORMAT
# ============================================================================

def test_loader_reads_map_index_fields(tmp_path: Path):
    """The JSON map carries exact population, grid ref, magic-free and miles,
    exactly like the original SOE map index."""
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({
        "cities": [
            {"id": "a", "name": "Agnok", "population": 59000,
             "terrain": ["plains"], "is_magic_free": True, "grid_ref": "A6"},
            {"id": "b", "name": "Krijiya", "population": 19000,
             "terrain": ["forest"], "grid_ref": "G10"},
        ],
        "roads": [
            {"id": "r", "from": "a", "to": "b", "quality": "fair",
             "distance_miles": 51},
        ],
    }))
    wm = load_map_from_json(map_file)
    agnok = wm.cities["a"]
    assert agnok.population == 59000
    assert agnok.is_magic_free is True
    assert agnok.grid_ref == "A6"
    assert agnok.population_band == models.PopulationBand.MEDIUM  # derived
    assert wm.roads["r"].distance_miles == 51
    assert wm.cities["b"].population_band == models.PopulationBand.MEDIUM


def test_loader_keeps_explicit_band(tmp_path: Path):
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({
        "cities": [{"id": "a", "name": "Agnok", "population": 59000,
                    "population_band": "100k+", "terrain": []}],
        "roads": [],
    }))
    wm = load_map_from_json(map_file)
    assert wm.cities["a"].population_band == models.PopulationBand.LARGE
    assert wm.cities["a"].population == 59000


def test_loader_accepts_legacy_band_names(tmp_path: Path):
    """Saves written before the bands were retiered still load.

    Each old band maps to the band its old midpoint falls in, so a city
    keeps the size it was written with.
    """
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({
        "cities": [
            {"id": "a", "name": "A", "population_band": "< 10k", "terrain": []},
            {"id": "b", "name": "B", "population_band": "10k-99k", "terrain": []},
            {"id": "c", "name": "C", "population_band": "100k-999k", "terrain": []},
            {"id": "d", "name": "D", "population_band": "1M+", "terrain": []},
        ],
        "roads": [],
    }))
    wm = load_map_from_json(map_file)
    assert wm.cities["a"].population_band == models.PopulationBand.SMALL
    assert wm.cities["b"].population_band == models.PopulationBand.MEDIUM
    assert wm.cities["c"].population_band == models.PopulationBand.LARGE
    assert wm.cities["d"].population_band == models.PopulationBand.LARGE


def test_save_round_trips_new_fields(tmp_path: Path):
    """save_map_to_json must not drop the map-index fields."""
    wm = models.WorldMap()
    wm.cities["a"] = models.City(
        id="a", name="Agnok", population=59000,
        population_band=models.PopulationBand.SMALL,
        terrain={"plains"}, is_magic_free=True, grid_ref="A6",
        is_ruin=True, resource_richness={"iron": 2.0},
        fortification_level=15, x=0.25, y=0.75)
    wm.roads["r"] = models.Road(
        id="r", from_city_id="a", to_city_id="a",
        quality=models.RoadQuality.FAIR, distance_miles=51)
    out = tmp_path / "out.json"
    save_map_to_json(wm, out)
    again = load_map_from_json(out)
    assert again.cities["a"].population == 59000
    assert again.cities["a"].is_magic_free is True
    assert again.cities["a"].grid_ref == "A6"
    assert again.cities["a"].is_ruin is True
    assert again.cities["a"].resource_richness == {"iron": 2.0}
    assert again.cities["a"].fortification_level == 15
    assert again.cities["a"].x == pytest.approx(0.25)
    assert again.cities["a"].y == pytest.approx(0.75)
    assert again.roads["r"].distance_miles == 51


def test_loader_reads_ruin_and_resources(tmp_path: Path):
    map_file = tmp_path / "map.json"
    map_file.write_text(json.dumps({
        "cities": [
            {"id": "ruin", "name": "Hakkaba", "population": 0,
             "population_band": "< 10k", "is_ruin": True,
             "resource_richness": {"gems": 1.5}, "fortification_level": 5,
             "x": 0.1, "y": 0.2},
        ],
        "roads": [],
    }))
    wm = load_map_from_json(map_file)
    city = wm.cities["ruin"]
    assert city.is_ruin is True
    assert city.resource_richness == {"gems": 1.5}
    assert city.fortification_level == 5
    assert city.x == pytest.approx(0.1)
    assert city.y == pytest.approx(0.2)


def test_validate_rejects_missing_band_and_bad_roads(tmp_path: Path):
    map_file = tmp_path / "bad.json"
    map_file.write_text(json.dumps({
        "cities": [
            {"id": "a", "name": "A", "terrain": []},
            {"id": "b", "name": "B", "population": 1000},
        ],
        "roads": [
            {"id": "r1", "from": "a", "to": "missing", "quality": "good"},
            {"id": "r2", "from": "b", "to": "b", "quality": "fair",
             "distance_miles": -3},
        ],
    }))
    with pytest.raises(MapValidationError) as exc:
        load_map_from_json(map_file)
    joined = "\n".join(exc.value.errors)
    assert "need population_band or population" in joined
    assert "does not exist" in joined
    assert "distance_miles must be >= 0" in joined


def test_validate_rejects_empty_map():
    assert "map has no cities" in validate_map(models.WorldMap())


def test_validate_rejects_duplicate_ids(tmp_path: Path):
    map_file = tmp_path / "dup.json"
    map_file.write_text(json.dumps({
        "cities": [
            {"id": "a", "name": "A", "population": 100},
            {"id": "a", "name": "Again", "population": 200},
        ],
        "roads": [],
    }))
    with pytest.raises(MapValidationError) as exc:
        load_map_from_json(map_file)
    assert any("duplicate city id" in e for e in exc.value.errors)


def test_sea_lane_non_port_is_warning_not_error(tmp_path: Path):
    map_file = tmp_path / "sea.json"
    map_file.write_text(json.dumps({
        "cities": [
            {"id": "a", "name": "A", "population": 1000, "is_port": False},
            {"id": "b", "name": "B", "population": 1000, "is_port": True},
        ],
        "roads": [
            {"id": "s", "from": "a", "to": "b", "quality": "sea",
             "distance_miles": 50},
        ],
    }))
    wm = load_map_from_json(map_file)  # strict: should pass
    warnings = validate_map_warnings(wm)
    assert any("not a port" in w for w in warnings)


def test_sample_map_validates():
    wm = create_sample_map()
    assert validate_map(wm) == []
    assert validate_map_warnings(wm) == []
    assert wm.cities["hakkaba"].is_ruin is True
    assert wm.roads["road_1"].quality == models.RoadQuality.EXCELLENT


def test_sample_map_json_on_disk_validates():
    path = Path(__file__).resolve().parent.parent / "maps" / "sample_map.json"
    if not path.exists():
        pytest.skip("sample_map.json not present")
    wm = load_map_from_json(path)
    assert len(wm.cities) >= 6
    assert wm.cities["riverton"].resource_richness.get("wood") == 1.0
    assert wm.cities["hakkaba"].is_ruin is True
    assert wm.cities["peshandi"].is_magic_free is True
    # Neighbours should be walkable in one turn (10 MP).
    assert config.get_hop_cost(wm.roads["road_1"]) <= 10
    assert config.get_hop_cost(wm.roads["road_2"]) <= 10
    assert config.get_hop_cost(wm.roads["road_5"]) <= 10
    # Grid letters increase west→east with x.
    ordered = sorted(wm.cities.values(), key=lambda c: c.x or 0)
    letters = [c.grid_ref[0] for c in ordered if c.grid_ref]
    assert letters == sorted(letters)


def test_world_map_uses_every_population_band():
    """The bands are the gamemaster's tiers, so none of them is dead.

    Pitched at real-world city sizes they were: the world's largest town
    is 134,000, which left the top band empty and put 128 of the 154 towns
    in the bottom one.
    """
    path = Path(__file__).resolve().parent.parent / "maps" / "soe_world.json"
    if not path.exists():
        pytest.skip("soe_world.json not present")
    wm = load_map_from_json(path)
    counts = {band: 0 for band in models.PopulationBand}
    for city in wm.cities.values():
        assert city.population_band == config.population_band_for(city.population)
        counts[city.population_band] += 1
    assert all(counts.values()), f"unused population band: {counts}"
    assert max(counts.values()) < len(wm.cities) * 0.6, counts


def test_world_map_towns_all_belong_to_a_region():
    """Every town takes the name of the landmass it stands on."""
    path = Path(__file__).resolve().parent.parent / "maps" / "soe_world.json"
    if not path.exists():
        pytest.skip("soe_world.json not present")
    wm = load_map_from_json(path)
    unnamed = [c.name for c in wm.cities.values() if not c.region]
    assert unnamed == []
    regions = {c.region for c in wm.cities.values()}
    assert "Slamoniya" in regions and "Kyupaa" in regions
    # One name per landmass the raster labels, and no name invented since.
    # assign_regions pulls in the map extras, so skip where they are absent.
    sys.path.insert(0, str(path.parent.parent / "scripts"))
    try:
        labels = pytest.importorskip("assign_regions").LABELS
    finally:
        sys.path.pop(0)
    assert regions == {name for name, _box, _certain in labels}


def test_sample_map_miles_scale_with_layout():
    """Longer routes should draw longer (roughly proportional miles/px)."""
    from webapp import mapview

    path = Path(__file__).resolve().parent.parent / "maps" / "sample_map.json"
    if not path.exists():
        pytest.skip("sample_map.json not present")
    data = mapview.load_raw_map("sample_map.json")
    pos = mapview.positions("sample_map.json")
    ratios = []
    for r in data["roads"]:
        miles = r.get("distance_miles")
        if not miles:
            continue
        a, b = pos[r["from"]], pos[r["to"]]
        px = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
        ratios.append(miles / px)
    # All mi/px ratios within ~2× of each other (schematic but not inverted).
    assert max(ratios) / min(ratios) < 2.0


def test_mapview_tooltips_include_hop_and_resources():
    from webapp import mapview

    path = Path(__file__).resolve().parent.parent / "maps" / "sample_map.json"
    if not path.exists():
        pytest.skip("sample_map.json not present")
    svg = mapview.render_svg("sample_map.json")
    assert "mv" in svg
    assert "wood" in svg or "resources: wood" in svg
    assert "Hakkaba" in svg
    assert "excellent" in svg
    # No blur filters (they soft-focus the whole map when scaled).
    assert "feGaussianBlur" not in svg
    assert 'shape-rendering="geometricPrecision"' in svg
    # Sparse sample keeps permanent labels for every city.
    assert "soe-map-sparse" in svg
    assert "city-name-always" in svg


def test_soe_world_map_names_every_city():
    """Full gazetteer map: every town has a permanent name; no mile-label soup."""
    import re

    from webapp import mapview

    path = Path(__file__).resolve().parent.parent / "maps" / "soe_world.json"
    if not path.exists():
        pytest.skip("soe_world.json not present")
    data = mapview.load_raw_map("soe_world.json")
    cities = data["cities"]
    pos = mapview.positions("soe_world.json")
    plan = mapview._plan_city_labels(cities, pos)
    # Every city with a position gets an always-on name.
    for c in cities:
        cid = c["id"]
        if cid not in pos:
            continue
        assert plan[cid].name_mode == "always", cid
        assert plan[cid].display_name or c.get("name")

    svg = mapview.render_svg("soe_world.json")
    assert "soe-map-very-dense" in svg or "soe-map-dense" in svg
    always = len(re.findall(r'class="[^"]*city-name-always', svg))
    assert always >= len(cities)  # one permanent name text per city (+ CSS noise ok)
    # Road mile/mv text is tooltip-only on dense maps (not painted as <text>).
    mile_texts = re.findall(r"<text[^>]*>[^<]*\bmi\b[^<]*</text>", svg)
    assert len(mile_texts) < 20
    assert "Madegi Doy" in svg or "Madegi" in svg
    assert "Every town is named" in svg


def test_soe_world_uses_geography_coastlines_not_road_hulls():
    """Web map land matches the poster: 15 traced coastlines, region names."""
    from webapp import mapview

    world = Path(__file__).resolve().parent.parent / "maps" / "soe_world.json"
    geo = Path(__file__).resolve().parent.parent / "maps" / "soe_geography.json"
    if not world.exists() or not geo.exists():
        pytest.skip("soe_world / soe_geography not present")

    stats = mapview.map_stats("soe_world.json")
    assert stats["layout"].has_geography
    assert stats["landmasses"] == 15
    names = {m["name"] for m in stats["masses"]}
    # Distinct bodies — not one merged slab of road components.
    for region in ("Olighotsi", "Slamoniya", "Kyupaa", "Boriagris"):
        assert region in names
    assert all(m.get("source") == "geography" for m in stats["masses"])
    assert "15 landmasses" in stats["title"]

    svg = mapview.render_svg("soe_world.json")
    assert "soe-map-geo" in svg
    # Full 1300×1000 field aspect fits in the viewBox (no east clipping).
    assert 'viewBox="0 0 1372 1110"' in svg or "1372" in svg
    pos = mapview.positions("soe_world.json")
    layout = stats["layout"]
    # Eastern town stays inside the frame (was cut off under 1400×880).
    assert "al_katib" in pos
    assert 0 < pos["al_katib"][0] < layout.width
    assert 0 < pos["al_katib"][1] < layout.height


def test_sample_map_landmasses_split_by_sea():
    """Sea lanes do not join land; Albatross is its own island confine."""
    from webapp import mapview

    path = Path(__file__).resolve().parent.parent / "maps" / "sample_map.json"
    if not path.exists():
        pytest.skip("sample_map.json not present")
    stats = mapview.map_stats("sample_map.json")
    assert stats["landmasses"] == 2
    assert stats["islands"] >= 1
    masses = {m["name"]: m for m in stats["masses"]}
    assert "Northern Island" in masses or any(
        "albatross" in " ".join(m["city_ids"]).lower() for m in stats["masses"]
    )
    island = next(m for m in stats["masses"] if "albatross_city" in m["city_ids"])
    assert island["kind"] == "island"
    assert len(island["city_ids"]) == 1
    continent = next(m for m in stats["masses"] if "madegi_doy" in m["city_ids"])
    assert "kitesta" in continent["city_ids"]
    assert "albatross_city" not in continent["city_ids"]
    assert len(continent["hull"]) >= 3
    html = mapview.islands_html("sample_map.json")
    assert "Main Continent" in html or "continent" in html
    assert "Albatross" in html or "Northern Island" in html


def test_independents_fall_back_on_custom_map_cities():
    from webapp.service import _resolve_city_id

    cities = ["alpha", "beta"]
    assert _resolve_city_id("albatross_city", cities) == "alpha"
    assert _resolve_city_id("beta", cities) == "beta"
    assert _resolve_city_id(None, cities) == "alpha"
    # Prefer first match from a list (sample island → full-map fallback).
    assert _resolve_city_id(["albatross_city", "kitesta"], cities) == "alpha"
    assert _resolve_city_id(
        ["albatross_city", "kitesta"], ["kitesta", "madegi_doy"]
    ) == "kitesta"


# ============================================================================
# MILES-BASED PRICING
# ============================================================================

def test_hop_cost_scales_with_miles(miles_state):
    """A 103-mile good road costs 10.3 movement points (multiplier 1.0)."""
    assert config.get_hop_cost(miles_state.world_map.roads["r1"]) == pytest.approx(10.3)
    poor = config.get_hop_cost(miles_state.world_map.roads["r2"])
    assert poor == pytest.approx(19.4)  # 2.0 x 97/10


def test_hop_cost_falls_back_without_miles():
    road = models.Road(id="r", from_city_id="a", to_city_id="b",
                       quality=models.RoadQuality.GOOD)
    assert config.get_hop_cost(road) == 1.0


def test_routing_uses_miles(miles_state):
    """town -> ruin goes town->city->ruin (10.3 + 19.4 = 29.7), not a
    hypothetical longer direct route."""
    path, cost = engine.find_shortest_path("town", "ruin", miles_state)
    assert path == ["town", "city", "ruin"]
    assert cost == pytest.approx(29.7)
    assert engine.route_miles(path, miles_state) == pytest.approx(200)


def test_orb_scan_cost_uses_miles(miles_state):
    """rules.md: one power per ten miles."""
    assert engine.orb_scan_cost("town", "city", miles_state) == 10
    assert engine.orb_scan_cost("town", "ruin", miles_state) == 20
    assert engine.orb_scan_cost("town", "town", miles_state) == 0


def test_orb_scan_cost_falls_back_without_miles():
    gs = models.GameState()
    gs.world_map.cities["a"] = models.City(id="a", name="A", population_band=models.PopulationBand.TINY)
    gs.world_map.cities["b"] = models.City(id="b", name="B", population_band=models.PopulationBand.TINY)
    gs.world_map.roads["r"] = models.Road(id="r", from_city_id="a", to_city_id="b",
                                          quality=models.RoadQuality.GOOD)
    assert engine.orb_scan_cost("a", "b", gs) == config.ORB_POWER_PER_HOP


def test_teleport_costs_encumbrance_and_ignores_distance(miles_state):
    """
    rules.md: the power is "equal to the total encumbrance of the group", and
    "TELEPORT ... has no limit on distance ... anywhere on the planet."

    So the island reachable only by sea costs exactly what the near ruin costs:
    one point for a lone character with nothing on him.
    """
    from spoils_engine.orders import TeleportOrder

    gs = miles_state
    wizard = models.Character(id="w", name="Merlin", faction_id="p",
                              location_city_id="town", magic_skill=100,
                              magic_power_current=200)
    gs.characters["w"] = wizard
    target = models.Character(id="t", name="Joe", faction_id="p",
                              location_city_id="town")
    gs.characters["t"] = target

    engine.process_magic({"p": [TeleportOrder(player_id="p", actor_id="w",
                                              target_character_id="t",
                                              destination_city_id="isle")]},
                         gs, engine.TurnLog(), random.Random(1))

    assert target.location_city_id == "isle"  # no overland route exists
    assert wizard.magic_power_current == 200 - 1


def test_teleport_power_grows_with_the_group_not_the_journey(miles_state):
    """A heavy group is what costs power: 20 soldiers and their leader weigh 21."""
    from spoils_engine.orders import TeleportOrder

    gs = miles_state
    wizard = models.Character(id="w", name="Merlin", faction_id="p",
                              location_city_id="town", magic_skill=100,
                              magic_power_current=200)
    gs.characters["w"] = wizard
    target = models.Character(id="t", name="Joe", faction_id="p",
                              location_city_id="town")
    gs.characters["t"] = target
    gs.unit_stacks["s"] = models.UnitStack(
        id="s", faction_id="p", location_city_id="town",
        unit_type=models.UnitType.SOLDIER, count=20, owner_character_id="t")

    engine.process_magic({"p": [TeleportOrder(player_id="p", actor_id="w",
                                              target_character_id="t",
                                              destination_city_id="city")]},
                         gs, engine.TurnLog(), random.Random(1))

    assert wizard.magic_power_current == 200 - 21


def test_magic_free_city_stays_draining(miles_state):
    assert miles_state.world_map.cities["town"].is_magic_free is True
    assert miles_state.world_map.cities["city"].is_magic_free is False


def test_chained_recruit_fails_when_move_failed(miles_state):
    """A recruit order behind a failed move (town -> city is 103 miles, 10.3
    points > 10) must not recruit from afar."""
    gs = miles_state
    gs.factions["p"] = models.Faction(id="p", name="Empire")
    actor = models.Character(id="a", name="Marcus", faction_id="p",
                             location_city_id="town")
    gs.characters["a"] = actor

    from spoils_engine.orders import MoveOrder, RecruitOrder
    move = MoveOrder(player_id="p", actor_id="a", destination_city_id="city")
    recruit = RecruitOrder(player_id="p", actor_id="a", city_id="city",
                           unit_type="soldier", count=10)
    gs, log = engine.run_turn(gs, {"p": [move, recruit]}, 42)

    assert actor.location_city_id == "town"  # never moved
    assert not gs.unit_stacks  # nothing recruited at the far city
    failed = [e for e in log.events if e.event_type == "recruit_failed"]
    assert failed and "is not in" in failed[0].description


# ============================================================================
# CONNECTIVITY
# ============================================================================

def _write_map(tmp_path: Path, cities, roads) -> Path:
    map_file = tmp_path / "conn.json"
    map_file.write_text(json.dumps({"cities": cities, "roads": roads}))
    return map_file


def test_land_components_separate_the_island_from_the_continent():
    wm = create_sample_map()
    masses = land_components(wm)

    assert [len(m) for m in masses] == [5, 1]  # largest first
    assert masses[1] == {"albatross_city"}  # sea lane does not join land
    assert "madegi_doy" in masses[0]

    # The sea lane still puts every city in mutual reach, so all six are
    # eligible starts and map order is preserved.
    assert mutually_reachable_cities(wm) == list(wm.cities.keys())


def test_isolated_city_is_warned_and_is_never_an_eligible_start(tmp_path: Path):
    map_file = _write_map(
        tmp_path,
        cities=[
            {"id": "a", "name": "A", "population": 1000},
            {"id": "b", "name": "B", "population": 1000},
            {"id": "lost", "name": "Lost", "population": 1000},
        ],
        roads=[{"id": "r", "from": "a", "to": "b", "quality": "good",
                "distance_miles": 10}],
    )
    wm = load_map_from_json(map_file)

    assert validate_map(wm) == []  # structurally fine, just bad geography
    assert isolated_cities(wm) == ["lost"]
    assert any("unreachable" in w and "lost" in w for w in validate_map_warnings(wm))
    assert mutually_reachable_cities(wm) == ["a", "b"]


def test_sealed_landmass_is_warned(tmp_path: Path):
    """Two continents, no sea lane between them: neither can ever reach the other."""
    map_file = _write_map(
        tmp_path,
        cities=[
            {"id": "a", "name": "A", "population": 1000},
            {"id": "b", "name": "B", "population": 1000},
            {"id": "x", "name": "X", "population": 1000},
            {"id": "y", "name": "Y", "population": 1000},
        ],
        roads=[
            {"id": "r1", "from": "a", "to": "b", "quality": "good", "distance_miles": 10},
            {"id": "r2", "from": "x", "to": "y", "quality": "good", "distance_miles": 10},
        ],
    )
    wm = load_map_from_json(map_file)
    warnings = validate_map_warnings(wm)

    sealed = [w for w in warnings if "no sea lane connects it" in w]
    assert len(sealed) == 2  # both halves are sealed off
    assert mutually_reachable_cities(wm) == ["a", "b"]  # starts stay on one side


def test_one_way_road_is_warned_and_dead_ends_are_not_start_cities(tmp_path: Path):
    """You can march into 'trap' but never out, so nobody may start there."""
    map_file = _write_map(
        tmp_path,
        cities=[
            {"id": "a", "name": "A", "population": 1000},
            {"id": "b", "name": "B", "population": 1000},
            {"id": "trap", "name": "Trap", "population": 1000},
        ],
        roads=[
            {"id": "r1", "from": "a", "to": "b", "quality": "good", "distance_miles": 10},
            {"id": "r2", "from": "b", "to": "trap", "quality": "good",
             "distance_miles": 10, "bidirectional": False},
        ],
    )
    wm = load_map_from_json(map_file)

    assert any("one-way" in w for w in validate_map_warnings(wm))
    # 'trap' shares the landmass, but is not in mutual reach of the others.
    assert land_components(wm) == [{"a", "b", "trap"}]
    assert mutually_reachable_cities(wm) == ["a", "b"]


def test_route_miles_bills_the_network_the_path_was_found_on(tmp_path: Path):
    """
    Two ports joined by both a short road and a long sea lane. A voyage must be
    billed the sea mileage, a march the road's -- not whichever was listed first.
    """
    map_file = _write_map(
        tmp_path,
        cities=[
            {"id": "a", "name": "A", "population": 50000, "is_port": True},
            {"id": "b", "name": "B", "population": 50000, "is_port": True},
        ],
        roads=[
            {"id": "land", "from": "a", "to": "b", "quality": "good",
             "distance_miles": 40},
            {"id": "sea", "from": "a", "to": "b", "quality": "sea",
             "distance_miles": 260},
        ],
    )
    gs = models.GameState(world_map=load_map_from_json(map_file))

    assert engine.route_miles(["a", "b"], gs) == 40                 # land default
    assert engine.route_miles(["a", "b"], gs, sea_only=True) == 260  # the voyage


def test_route_miles_will_not_bill_a_one_way_road_backwards(tmp_path: Path):
    map_file = _write_map(
        tmp_path,
        cities=[
            {"id": "a", "name": "A", "population": 1000},
            {"id": "b", "name": "B", "population": 1000},
        ],
        roads=[{"id": "r", "from": "a", "to": "b", "quality": "good",
                "distance_miles": 30, "bidirectional": False}],
    )
    gs = models.GameState(world_map=load_map_from_json(map_file))

    assert engine.route_miles(["a", "b"], gs) == 30
    assert engine.route_miles(["b", "a"], gs) is None  # no such journey


def test_landmass_name_prefers_the_author_label_when_it_holds_up():
    wm = create_sample_map()
    assert landmass_name(wm, "madegi_doy") == "Main Continent"
    assert landmass_name(wm, "albatross_city") == "Northern Island"
    assert landmass_index(wm)["albatross_city"] != landmass_index(wm)["madegi_doy"]


def test_region_label_that_the_roads_contradict_is_warned_and_not_trusted(tmp_path: Path):
    """'Twin Shores' claims one body of land, but no road joins the two halves."""
    map_file = _write_map(
        tmp_path,
        cities=[
            {"id": "a", "name": "A", "region": "Twin Shores", "population": 1000,
             "is_port": True},
            {"id": "b", "name": "B", "region": "Twin Shores", "population": 1000,
             "is_port": True},
        ],
        roads=[{"id": "s", "from": "a", "to": "b", "quality": "sea",
                "distance_miles": 80}],
    )
    wm = load_map_from_json(map_file)

    assert any("Twin Shores" in w and "landmasses" in w
               for w in validate_map_warnings(wm))
    # The report falls back to a generated name rather than repeat the lie.
    assert landmass_name(wm, "a") == "Island 1"
    assert landmass_name(wm, "b") == "Island 2"


def test_turn_report_tells_a_player_the_roads_out_of_their_cities(miles_state):
    """
    A postal player cannot poke the map to learn it. The report names every
    route leaving the ground they stand on, with condition, miles and cost.
    """
    from spoils_engine import reporting
    from spoils_engine.turn_log import TurnLog

    gs = miles_state
    gs.factions["p"] = models.Faction(id="p", name="Reachers",
                                      controlled_city_ids={"town"})
    gs.characters["c"] = models.Character(
        id="c", name="Scout", faction_id="p", location_city_id="town")

    report = reporting.generate_player_reports(gs, TurnLog(), {"p": []})["p"]

    assert "THE LIE OF THE LAND" in report
    assert "Agnok" in report
    assert "-> Kitesta: good road, 103 miles," in report
    assert "-> Albatross City: sea lane, 342 miles," in report
    # Only where they stand: nothing about the far side of the map.
    assert "-> Ruin:" not in report


def test_turn_report_says_so_when_a_faction_holds_no_ground(miles_state):
    from spoils_engine import reporting
    from spoils_engine.turn_log import TurnLog

    gs = miles_state
    gs.factions["p"] = models.Faction(id="p", name="Landless")

    report = reporting.generate_player_reports(gs, TurnLog(), {"p": []})["p"]
    assert "you hold no ground" in report


# ============================================================================
# ENCUMBRANCE (rules.md Appendix B)
# ============================================================================

def test_appendix_b_substance_weights():
    """
    A unit of every substance is worth one gold, so the cheap ones are heavy:
    "3 copper would have the same weight or encumbrance as 300 gold."
    """
    from spoils_engine.encumbrance import resource_encumbrance

    assert resource_encumbrance({"copper": 3}) == pytest.approx(
        resource_encumbrance({}, gold=300))
    assert resource_encumbrance({"iron": 5}) == pytest.approx(
        resource_encumbrance({}, gold=5000))
    assert resource_encumbrance({"silver": 500}) == pytest.approx(
        resource_encumbrance({}, gold=5000))
    assert resource_encumbrance({"gems": 25_000}) == pytest.approx(
        resource_encumbrance({}, gold=5000))
    # Stone and wood weigh the same per unit, per the note under Appendix B.
    assert resource_encumbrance({"stone": 7}) == resource_encumbrance({"wood": 7}) == 7


def test_group_encumbrance_counts_people_and_cargo(miles_state):
    from spoils_engine import encumbrance

    gs = miles_state
    leader = models.Character(id="l", name="Leader", faction_id="p",
                              location_city_id="town", gold=5000)
    follower = models.Character(id="f", name="Follower", faction_id="p",
                                location_city_id="town", group_leader_id="l")
    follower.resources = {"iron": 10}
    gs.characters.update({"l": leader, "f": follower})
    gs.unit_stacks["s"] = models.UnitStack(
        id="s", faction_id="p", location_city_id="town",
        unit_type=models.UnitType.SOLDIER, count=30, owner_character_id="l")

    # leader 1 + 5000 gold (1) + 30 soldiers + follower 1 + 10 iron (2)
    assert encumbrance.group_encumbrance(leader, gs) == pytest.approx(35.0)
    # FLY is one fifth of that, rounded up; TELEPORT is the whole weight.
    assert encumbrance.fly_power_cost(leader, gs) == 7
    assert encumbrance.teleport_power_cost(leader, gs) == 35


def test_summoned_creatures_are_weightless(miles_state):
    """rules.md: summoned creatures "have zero encumbrance ... to teleport them"."""
    from spoils_engine import encumbrance

    gs = miles_state
    wizard = models.Character(id="w", name="Merlin", faction_id="p",
                              location_city_id="town", magic_skill=100)
    gs.characters["w"] = wizard
    before = encumbrance.group_encumbrance(wizard, gs)
    gs.summoned_creatures["k"] = models.SummonedCreature(
        id="k", summoner_id="w", creature_type=models.CreatureType.DRAGON,
        count=3)

    assert encumbrance.group_encumbrance(wizard, gs) == before


# ============================================================================
# ORB SCAN DISTANCE
# ============================================================================

def test_an_orb_can_scan_across_water(miles_state):
    """
    An orb is a crystal ball, not a courier: it does not follow roads. The
    island is 342 sea miles off, so the scan costs 34 power.
    """
    from spoils_engine.phases.intel import orb_scan_cost

    assert orb_scan_cost("town", "isle", miles_state) == 34
    # And an overland target is still priced off the road mileage.
    assert orb_scan_cost("town", "city", miles_state) == 10


def test_an_orb_scan_takes_the_shorter_way_round(miles_state):
    """
    town -> city -> ruin is 200 road miles. Open a 60-mile sea lane between the
    ends and the orb should price the shorter route, not the overland one.
    """
    from spoils_engine.phases.intel import orb_scan_cost

    gs = miles_state
    gs.world_map.cities["ruin"].is_port = True
    gs.world_map.cities["town"].is_port = True
    assert orb_scan_cost("town", "ruin", gs) == 20

    gs.world_map.roads["s2"] = models.Road(
        id="s2", from_city_id="town", to_city_id="ruin",
        quality=models.RoadQuality.SEA, distance_miles=60)
    assert orb_scan_cost("town", "ruin", gs) == 6


def test_an_unreachable_location_cannot_be_scanned(miles_state):
    from spoils_engine.phases.intel import orb_scan_cost

    gs = miles_state
    gs.world_map.cities["void"] = models.City(
        id="void", name="Nowhere", population_band=models.PopulationBand.TINY)
    assert orb_scan_cost("town", "void", gs) == -1


def test_find_route_sums_miles_from_the_roads_it_used(miles_state):
    """The route carries its own legs, so mileage is never re-guessed."""
    from spoils_engine.phases.pathing import find_route

    route = find_route("town", "ruin", miles_state)
    assert route.city_ids == ["town", "city", "ruin"]
    assert route.road_ids == ["r1", "r2"]
    assert route.miles(miles_state) == 200

    sea = find_route("town", "isle", miles_state, allow_land=False, allow_sea=True)
    assert sea.road_ids == ["s1"]
    assert sea.miles(miles_state) == 342

    assert not find_route("isle", "ruin", miles_state)  # no overland link
