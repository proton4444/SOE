"""The coastline sidecar, and whether it is the world's own coast.

`generate_world.py` builds a landmass, grows terrain on it, samples towns from
it, and returns only the towns. `generate_geography.py` recovers the rest from
the same seed. The whole value of that is provenance: this is the land the
towns were placed on, not a shore drawn around them afterwards, and these
tests are what keeps the difference real.

Three things are checked. The trace agrees with the lattice it came from, to
the cell. A map that does not belong to the seed is refused rather than
decorated. And no town ends up in the water once the shore is drawn -- which
two of them did, before the smoothing learned to leave a town's own cell
alone.
"""

from __future__ import annotations

import json
import random

import pytest

from scripts import generate_geography as gg
from scripts import generate_world as gw

SEED = 1
REPO_MAPS = gg.REPO_ROOT / "maps"


@pytest.fixture(scope="module")
def field():
    return gg.build_field(SEED)


@pytest.fixture(scope="module")
def world():
    return json.loads((REPO_MAPS / "world.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def geography(world):
    return gg.build_geography(SEED, world["cities"])


# ---------------------------------------------------------------------------
# the field is the generator's own
# ---------------------------------------------------------------------------


def test_the_field_is_the_one_the_towns_were_placed_on(field):
    """Same seed, same two calls, in `generate()`'s order."""
    rng = random.Random(SEED)
    land = gw.build_landmass(rng)
    terrain = gw.build_terrain(rng, land)
    assert (land, terrain) == field


def test_the_shipped_world_regenerates_from_this_seed(world):
    assert gg.verify_exact(world["cities"], SEED) == []


def test_a_different_seed_is_a_different_world(world):
    assert gg.verify_exact(world["cities"], SEED + 1) != []


def test_building_the_geography_twice_gives_the_same_file(world):
    first = gg.build_geography(SEED, world["cities"])
    second = gg.build_geography(SEED, world["cities"])
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ---------------------------------------------------------------------------
# the trace agrees with the lattice
# ---------------------------------------------------------------------------


def test_signed_areas_sum_to_the_land_cell_count(field):
    """The invariant that says the trace is exact.

    Outlines are negative and enclosed water positive, so the whole set sums
    to the area of the land itself -- cell for cell, with no tolerance.
    """
    land, _ = field
    cells = sum(row.count(True) for row in land)
    total = sum(gg.signed_area(loop) for loop in gg.trace_mask(land))
    assert total == -float(cells)


def test_outlines_and_lakes_are_told_apart_by_winding(field):
    land, _ = field
    outlines, lakes = gg.polygons_for(land, smooth=False)
    assert outlines and lakes
    # Re-measure in mile coordinates: the sign has to survive the emit.
    for polygon in outlines:
        assert gg.signed_area([tuple(p) for p in polygon]) < 0
    for polygon in lakes:
        assert gg.signed_area([tuple(p) for p in polygon]) > 0


def test_seed_one_is_a_continent_an_island_and_its_lakes(geography):
    """Not 30 landmasses.

    Emitting every ring as a coastline made `mapview` count 30 landmasses and
    fill 28 inland lakes as if they were land.
    """
    assert len(geography["coastlines"]) == 2
    assert len(geography["lakes"]) == 28


def test_rivers_are_empty_because_the_generator_has_none(geography):
    assert geography["rivers"] == []


def test_every_terrain_the_field_uses_is_emitted(field, geography):
    _, terrain = field
    used = {terrain[y][x] for y in range(gw.GRID_H) for x in range(gw.GRID_W) if terrain[y][x]}
    for kind in used:
        assert geography["terrain"][kind], f"{kind} is on the field but has no polygon"


# ---------------------------------------------------------------------------
# a map either belongs to the field or is refused
# ---------------------------------------------------------------------------


def test_the_shipped_world_stands_on_the_field(world, field):
    land, terrain = field
    assert gg.verify_field(world["cities"], land, terrain) == []


def test_the_gate_map_stands_on_the_same_field(field):
    """calib_12 is a renamed twelve-town subsample of this world.

    So the poster's board is not a diagram floating in space: those twelve
    cities have a coast, and it is this one.
    """
    land, terrain = field
    calib = json.loads((REPO_MAPS / "calib_12.json").read_text(encoding="utf-8"))
    assert gg.verify_field(calib["cities"], land, terrain) == []


def test_a_town_moved_into_the_sea_is_refused(world, field):
    land, terrain = field
    strays = [dict(c) for c in world["cities"]]
    # The far corner is off the continent by construction: build_landmass
    # fades the field to nothing at the frame.
    strays[0] = {**strays[0], "x_miles": 5.0, "y_miles": 5.0}
    problems = gg.verify_field(strays, land, terrain)
    assert any("open water" in p for p in problems)


def test_a_relabelled_terrain_is_refused(world, field):
    land, terrain = field
    strays = [dict(c) for c in world["cities"]]
    current = strays[0]["terrain"][0]
    strays[0] = {**strays[0], "terrain": ["swamp" if current != "swamp" else "desert"]}
    problems = gg.verify_field(strays, land, terrain)
    assert any("the field says" in p for p in problems)


def test_a_coastal_town_that_is_not_a_port_is_refused(world, field):
    land, terrain = field
    strays = [dict(c) for c in world["cities"]]
    coastal = next(
        c for c in strays
        if c["is_port"] and any(gw.is_coastal(land, cx, cy) for cx, cy in gg.candidate_cells(c))
    )
    strays[strays.index(coastal)] = {**coastal, "is_port": False}
    problems = gg.verify_field(strays, land, terrain)
    assert any("no port" in p for p in problems)


def test_an_inland_port_is_allowed_because_the_generator_makes_them(world, field):
    """`build_routes` promotes both ends of a water crossing to `is_port`.

    It records nothing about having done so, so an inland port cannot be told
    from a mismatch, and treating it as one refused the shipped world over its
    own generator's behaviour.
    """
    land, terrain = field
    inland_ports = [
        c for c in world["cities"]
        if c["is_port"] and not any(gw.is_coastal(land, cx, cy) for cx, cy in gg.candidate_cells(c))
    ]
    assert inland_ports, "seed 1 has one; if that changes this test has nothing to say"
    assert gg.verify_field(inland_ports, land, terrain) == []


def test_a_coordinate_on_a_cell_boundary_offers_both_cells():
    """`round((cell + fraction) * 10, 1)` is lossy exactly at the boundary."""
    city = {"x_miles": 640.0, "y_miles": 640.0}
    assert (64, 64) in gg.candidate_cells(city)
    assert (63, 63) in gg.candidate_cells(city)
    assert len(gg.candidate_cells(city)) == 4
    assert gg.candidate_cells({"x_miles": 645.0, "y_miles": 643.0}) == [(64, 64)]


# ---------------------------------------------------------------------------
# no town may end up offshore
# ---------------------------------------------------------------------------


def test_the_drawn_coastline_contains_every_town(world, geography):
    assert gg.check_containment(world["cities"], geography["coastlines"]) == []


def test_the_gate_map_towns_are_ashore_too(geography):
    calib = json.loads((REPO_MAPS / "calib_12.json").read_text(encoding="utf-8"))
    assert gg.check_containment(calib["cities"], geography["coastlines"]) == []


def test_without_pinning_the_smoothing_beaches_two_towns(world):
    """The regression the pin exists for.

    Chaikin cuts every convex corner inward, and a town sampled at the seaward
    corner of a coastal cell sits in the piece that gets cut off. `ithford`
    and `caluen` are on capes narrow enough for it to happen.
    """
    unpinned = gg.build_geography(SEED, cities=None)
    offshore = gg.check_containment(world["cities"], unpinned["coastlines"])
    assert offshore, "smoothing no longer beaches anyone; the pin may be unnecessary"

    pinned = gg.build_geography(SEED, world["cities"])
    assert gg.check_containment(world["cities"], pinned["coastlines"]) == []


def test_raw_mode_emits_the_lattice_itself(world):
    """`--raw` is the escape hatch, and it has to be exactly the trace."""
    raw = gg.build_geography(SEED, world["cities"], smooth=False)
    for polygon in raw["coastlines"]:
        for x, y in polygon:
            assert x % gw.CELL_MILES == 0, f"{x} is not on a cell edge"
            assert y % gw.CELL_MILES == 0, f"{y} is not on a cell edge"


# ---------------------------------------------------------------------------
# the shipped sidecars, and the consumer that reads them
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# the fbm relief, and the world chosen with it
# ---------------------------------------------------------------------------

W2_SEED = 49
W2_RELIEF = "fbm"


def test_the_default_relief_is_the_original_and_stays_the_default():
    """maps/world.json was generated with it and games resolve town ids on it."""
    assert gw.DEFAULT_RELIEF == "noise"
    assert gw.build_landmass(random.Random(SEED)) == gw.build_landmass(
        random.Random(SEED), "noise"
    )


def test_an_unknown_relief_is_refused():
    with pytest.raises(ValueError):
        gw.build_landmass(random.Random(SEED), "erosion")


def test_world2_regenerates_from_its_seed_and_relief():
    world2 = json.loads((REPO_MAPS / "world2.json").read_text(encoding="utf-8"))
    assert gg.verify_exact(world2["cities"], W2_SEED, W2_RELIEF) == []


def test_world2_is_not_the_legacy_relief():
    """Belt and braces: the two modes must not have converged."""
    world2 = json.loads((REPO_MAPS / "world2.json").read_text(encoding="utf-8"))
    assert gg.verify_exact(world2["cities"], W2_SEED, "noise") != []


def test_the_fbm_relief_makes_a_continent_rather_than_a_slab():
    """The reason the mode exists, measured rather than asserted.

    The legacy field is white noise box-blurred three times: nothing survives
    larger than the kernel, so it thresholds to a frame-filling slab with a
    fractal edge and dozens of one-cell lakes. Over 200 seeds its main outline
    never got more compact than 0.27 or carried fewer than 21 pinholes.
    """
    import math

    def shape(mask):
        loops = gg.trace_mask(mask)
        outlines = [loop for loop in loops if gg.signed_area(loop) < 0]
        holes = [loop for loop in loops if gg.signed_area(loop) > 0]
        main = max(outlines, key=lambda loop: abs(gg.signed_area(loop)))
        perimeter = sum(
            math.dist(main[i], main[(i + 1) % len(main)]) for i in range(len(main))
        )
        return 4 * math.pi * abs(gg.signed_area(main)) / perimeter ** 2, len(holes)

    # Across seeds, not one: the claim is about the field, and a single draw
    # can flatter either mode.
    seeds = [W2_SEED, 7, 13, 31, 42]
    fbm = [shape(gw.build_landmass(random.Random(s), "fbm")) for s in seeds]
    old = [shape(gw.build_landmass(random.Random(s), "noise")) for s in seeds]

    fbm_compact = sum(c for c, _ in fbm) / len(fbm)
    old_compact = sum(c for c, _ in old) / len(old)
    assert fbm_compact > old_compact * 1.5

    assert max(h for _, h in fbm) <= 5
    assert min(h for _, h in old) >= 15


def test_the_fbm_relief_keeps_the_land_fraction():
    """A different shape, not a different amount of world."""
    fbm = gw.build_landmass(random.Random(W2_SEED), "fbm")
    cells = sum(row.count(True) for row in fbm)
    target = gw.TARGET_LAND_FRACTION * gw.GRID_W * gw.GRID_H
    assert abs(cells - target) / target < 0.02


def test_fbm_terrain_regions_are_country_sized():
    """One region per 14 cells is a 37-mile patch: right as data, confetti as a map."""
    land = gw.build_landmass(random.Random(W2_SEED), "fbm")
    fine = gw.build_terrain(random.Random(W2_SEED), land, "noise")
    coarse = gw.build_terrain(random.Random(W2_SEED), land, "fbm")

    def regions(terrain):
        mask = [[terrain[y][x] is not None for x in range(gw.GRID_W)] for y in range(gw.GRID_H)]
        assert mask  # terrain covers exactly the land
        kinds = {terrain[y][x] for y in range(gw.GRID_H) for x in range(gw.GRID_W)}
        return kinds

    # Same terrain vocabulary, larger pieces: the polygon count is the tell.
    fine_polys = sum(
        len(v) for v in gg.build_geography(W2_SEED, relief="fbm")["terrain"].values()
    )
    assert regions(fine) == regions(coarse)
    assert fine_polys < 80


def test_world2_towns_stand_on_the_fbm_field():
    land, terrain = gg.build_field(W2_SEED, W2_RELIEF)
    world2 = json.loads((REPO_MAPS / "world2.json").read_text(encoding="utf-8"))
    assert gg.verify_field(world2["cities"], land, terrain) == []
    geography = gg.build_geography(W2_SEED, world2["cities"], relief=W2_RELIEF)
    assert gg.check_containment(world2["cities"], geography["coastlines"]) == []


def test_world2_sidecar_records_its_relief():
    shipped = json.loads((REPO_MAPS / "world2_geography.json").read_text(encoding="utf-8"))
    assert shipped["source"] == {
        "generator": "scripts/generate_world.py",
        "seed": W2_SEED,
        "relief": W2_RELIEF,
    }


def test_world2_sidecar_matches_a_fresh_build():
    shipped = json.loads((REPO_MAPS / "world2_geography.json").read_text(encoding="utf-8"))
    source = json.loads((REPO_MAPS / "world2.json").read_text(encoding="utf-8"))
    fresh = gg.build_geography(
        W2_SEED, source["cities"], relief=W2_RELIEF, roads=source["roads"]
    )
    assert shipped == json.loads(json.dumps(fresh))


def test_every_sea_lane_sails_through_water():
    """The lane is drawn where a ship could actually be.

    Straight from town to town, an island-to-mainland lane crosses most of
    both: thirteen of world2's nineteen were drawn mostly over land, one of
    them 78% ashore. Only the two endpoints may be dry -- they are the ports.
    """
    land, _ = gg.build_field(W2_SEED, W2_RELIEF)
    world2 = json.loads((REPO_MAPS / "world2.json").read_text(encoding="utf-8"))
    paths = gg.sea_route_paths(land, world2["cities"], world2["roads"])

    lanes = [r for r in world2["roads"] if r["quality"] == "sea"]
    assert len(paths) == len(lanes)

    for road_id, path in paths.items():
        ashore = 0
        for x, y in path[1:-1]:
            cx = min(gw.GRID_W - 1, max(0, int(x // gw.CELL_MILES)))
            cy = min(gw.GRID_H - 1, max(0, int(y // gw.CELL_MILES)))
            if land[cy][cx]:
                ashore += 1
        # Smoothing can shave a corner across a headland by under a cell.
        assert ashore <= 1, f"{road_id} crosses land at {ashore} points"


def test_a_map_without_roads_gets_no_sea_routes():
    """The sidecar never invents a lane the map does not have."""
    assert gg.build_geography(W2_SEED, relief=W2_RELIEF)["sea_routes"] == {}


@pytest.mark.parametrize("name", ["world", "calib_12"])
def test_the_shipped_sidecar_matches_a_fresh_build(name):
    """A sidecar in the tree that no longer matches its seed is a stale map."""
    shipped = json.loads((REPO_MAPS / f"{name}_geography.json").read_text(encoding="utf-8"))
    source = json.loads((REPO_MAPS / f"{name}.json").read_text(encoding="utf-8"))
    fresh = gg.build_geography(SEED, source["cities"], roads=source.get("roads"))
    assert shipped == json.loads(json.dumps(fresh))


@pytest.mark.parametrize("name", ["world.json", "calib_12.json", "world2.json"])
def test_mapview_reads_the_sidecar(name):
    mapview = pytest.importorskip("webapp.mapview")
    geo = mapview.load_geography(name)
    assert geo is not None
    assert geo["coastlines"]
    layout = mapview.layout_for_map(name)
    assert layout.has_geography
    assert (layout.field_w_mi, layout.field_h_mi) == (
        gw.FIELD_WIDTH_MILES,
        gw.FIELD_HEIGHT_MILES,
    )


def test_the_sidecar_carries_the_schema_the_consumers_expect(geography):
    assert geography["units"] == "miles"
    assert geography["field_miles"] == [gw.FIELD_WIDTH_MILES, gw.FIELD_HEIGHT_MILES]
    assert geography["grid"]["cell_miles"] * geography["grid"]["cols"] == gw.FIELD_WIDTH_MILES
    assert geography["source"] == {
        "generator": "scripts/generate_world.py",
        "seed": SEED,
        "relief": gw.DEFAULT_RELIEF,
    }
