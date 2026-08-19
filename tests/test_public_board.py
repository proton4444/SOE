"""The poster's board is the 2D map's board, and stays that way.

`webapp/static/public/board.js` is generated from the map the poster shows
(`MAP_PATH` below) by
`scripts/build_public_board.py`. Amendment 2 (docs/MARKETING_CLOSED_ALPHA.md)
widened what crosses to the public page from coordinate topology to everything
the app's own map draws -- populations, grid references, ports, regions, road
mileages, and the landmass hull.

Two things can go wrong with that and neither announces itself. The board can
be regenerated from a changed map and not committed, so the poster shows a
world the repository no longer has. Or the hull can be recomputed here instead
of carried across, and drift from the one `webapp/mapview.py` draws -- two
pictures of one map that disagree about where the coast is. Both are checked
below.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.build_elevation import build_elevation  # noqa: E402
from scripts.build_public_board import build_board  # noqa: E402
from webapp import mapview  # noqa: E402

MAP_PATH = REPO_ROOT / "maps" / "starter_map.json"
BOARD_JS = REPO_ROOT / "webapp" / "static" / "public" / "board.js"
ELEVATION_JS = REPO_ROOT / "webapp" / "static" / "public" / "elevation.js"

PARITY_CITY_FIELDS = (
    "id",
    "name",
    "x",
    "y",
    "x_miles",
    "y_miles",
    "terrain",
    "population",
    "population_band",
    "grid_ref",
    "region",
    "is_ruin",
    "is_port",
    "is_magic_free",
)


def shipped_board() -> dict:
    """The JS constant as data, parsed out of the file the page actually loads."""
    text = BOARD_JS.read_text(encoding="utf-8")
    return json.loads(text[text.index("{") : text.rindex(";")])


def test_board_js_matches_the_builder():
    """Regenerating must be a no-op, or the poster is showing a stale world."""
    from scripts.build_public_board import HEADER

    rebuilt = HEADER + json.dumps(build_board(MAP_PATH), indent=2,
                                  ensure_ascii=False) + ";\n"
    assert BOARD_JS.read_text(encoding="utf-8") == rebuilt, (
        f"board.js is out of date with maps/{MAP_PATH.name}. "
        "Regenerate with: python -m scripts.build_public_board"
    )


@pytest.mark.parametrize("field", PARITY_CITY_FIELDS)
def test_every_city_carries_the_parity_field(field):
    for city in shipped_board()["cities"]:
        assert field in city, f"{city.get('id')} is missing {field}"


def test_city_values_are_the_map_values():
    """Every shipped field is the map's own value, mile coordinates included.

    Miles are compared against `mapview.city_miles` rather than a raw field: a
    map may carry fractions and no miles at all -- starter_map does -- and the
    board is supposed to derive them the same way the app does.
    """
    raw = json.loads(MAP_PATH.read_text("utf-8"))
    layout = mapview.layout_for_map(MAP_PATH.name, raw)
    source = {c["id"]: c for c in raw["cities"]}
    for city in shipped_board()["cities"]:
        origin = source[city["id"]]
        want_miles = mapview.city_miles(origin, layout)
        for field in PARITY_CITY_FIELDS:
            if field == "x_miles":
                assert city[field] == pytest.approx(want_miles[0], abs=0.05)
            elif field == "y_miles":
                assert city[field] == pytest.approx(want_miles[1], abs=0.05)
            else:
                assert city[field] == origin[field], f"{city['id']}.{field}"


def test_roads_carry_distance_and_movement_cost():
    for road in shipped_board()["roads"]:
        assert road["distance_miles"] is not None
        assert road["move_cost"] is not None, (
            f"{road['from']}->{road['to']} has miles but no movement cost; "
            "a distance without its cost is trivia"
        )


def test_terrain_ships_as_the_whole_list():
    """A city may sit on more than one terrain; the board used to keep one."""
    source = {c["id"]: c for c in json.loads(MAP_PATH.read_text("utf-8"))["cities"]}
    for city in shipped_board()["cities"]:
        assert isinstance(city["terrain"], list)
        assert city["terrain"] == source[city["id"]]["terrain"]


def test_the_hull_is_the_2d_map_s_own_polygon():
    """Carried across, not recomputed -- so the two can never disagree.

    The board stores fractions and mapview works in SVG units, so this maps
    the shipped polygon forward through the same transform and expects the
    frame's own coordinates back, to well under a pixel.
    """
    source = json.loads(MAP_PATH.read_text("utf-8"))
    layout = mapview.layout_for_map(MAP_PATH.name, source)
    expected = mapview.compute_landmasses(
        source["cities"], source["roads"], mapview.positions(MAP_PATH.name)
    )
    shipped = shipped_board()["landmasses"]
    assert len(shipped) == len(expected)

    for mass, want in zip(shipped, expected):
        assert mass["name"] == want["name"]
        assert mass["kind"] == want["kind"]
        assert mass["city_ids"] == want["city_ids"]
        assert len(mass["hull"]) == len(want["hull"])
        for (fx, fy), (px, py) in zip(mass["hull"], want["hull"]):
            assert layout.pad_x + fx * layout.map_w == pytest.approx(px, abs=0.01)
            assert layout.pad_y + fy * layout.map_h == pytest.approx(py, abs=0.01)


def test_every_city_stands_on_the_land():
    """A padded hull of the cities contains all of them, by construction.

    Which makes this a check on the transform rather than on the geometry: the
    polygon is carried out of mapview's SVG frame into fractions, and any
    error in that mapping -- a flip, a missing pad offset, a wrong extent --
    shows up here as a city standing in open water.

    It does NOT guard the renderer. The coast was once drawn mirrored about
    the board's centre line while this data was correct, because the flip was
    in board3d.js's Shape construction. Nothing in this file can see that; only
    looking at the board can.
    """
    board = shipped_board()
    # Each city against ITS OWN mass. Checking every city against the first
    # hull holds only while a map has one landmass; on an archipelago it
    # reports the islanders as drowned.
    hull_of = {}
    for mass in board["landmasses"]:
        for cid in mass["city_ids"]:
            hull_of[cid] = mass["hull"]
    for city in board["cities"]:
        assert mapview._point_in_poly(city["x"], city["y"], hull_of[city["id"]]), (
            f"{city['name']} is outside its own landmass"
        )


def test_region_anchors_cover_every_region():
    board = shipped_board()
    named = {city["region"] for city in board["cities"]}
    assert {r["name"] for r in board["regions"]} == named
    assert sum(r["cities"] for r in board["regions"]) == len(board["cities"])


def test_landmass_name_does_not_depend_on_set_ordering():
    """A region tie must not be broken by hash order.

    `max(set(regions), key=regions.count)` picked whichever tied region set
    iteration happened to yield first, so a map whose cities split evenly
    across regions named its landmass differently between processes -- in the
    map title and in the legend. calib_12 splits 4/4/4 and was where this was
    found; it is checked here on whatever map the poster ships, by shuffling
    the input, which stands in for the hash seed changing.
    """
    source = json.loads(MAP_PATH.read_text("utf-8"))
    pos = mapview.positions(MAP_PATH.name)
    baseline = mapview.compute_landmasses(source["cities"], source["roads"], pos)
    names = [mass["name"] for mass in baseline]

    for rotation in range(1, len(source["cities"])):
        rotated = source["cities"][rotation:] + source["cities"][:rotation]
        masses = mapview.compute_landmasses(rotated, source["roads"], pos)
        assert [m["name"] for m in masses] == names


def test_a_sea_lane_does_not_join_land():
    """starter_map reaches Gullhaven only by sea, so it is its own island.

    This is the property that makes the board an archipelago rather than one
    blob, and it is easy to lose: give `compute_landmasses` a sea road it
    treats like a highway and the two masses silently merge into one hull with
    a bay where the water should be.
    """
    board = shipped_board()
    sea_roads = [r for r in board["roads"] if r["quality"] == "sea"]
    assert sea_roads, "this map is meant to have a sea lane on it"

    by_mass = {}
    for mass in board["landmasses"]:
        for cid in mass["city_ids"]:
            by_mass[cid] = mass["index"]
    for road in sea_roads:
        assert by_mass[road["from"]] != by_mass[road["to"]], (
            f"{road['from']} and {road['to']} are joined by sea and still "
            "landed on the same landmass"
        )


def shipped_elevation() -> dict:
    text = ELEVATION_JS.read_text(encoding="utf-8")
    return json.loads(text[text.index("{") : text.rindex(";")])


def test_elevation_js_matches_the_builder():
    """The generator is the model. If they disagree, the model is a rumour."""
    from scripts.build_elevation import HEADER

    rebuilt = HEADER + json.dumps(build_elevation(MAP_PATH), indent=2,
                                  ensure_ascii=False) + ";\n"
    assert ELEVATION_JS.read_text(encoding="utf-8") == rebuilt, (
        "elevation.js is out of date. "
        "Regenerate with: python -m scripts.build_elevation"
    )


def test_elevation_covers_the_same_frame_as_the_board():
    board, elevation = shipped_board(), shipped_elevation()
    assert elevation["map"] == board["map"]
    assert elevation["frame_units"] == board["frame_units"]
    raw = base64.b64decode(elevation["data"])
    assert len(raw) == elevation["width"] * elevation["height"]


def test_cities_are_above_water_and_the_open_field_is_not():
    """Where the waterline falls, now that it is an isoline and not a polygon.

    The shore used to be the hull, so the hull's own vertices sat exactly at
    sea level and this test said so. They do not any more: the generator
    perturbs the distance-to-hull with noise before taking the shelf from it,
    which is the whole point -- the coast bites into the hull in places and
    pushes past it in others. What still has to be true is the part that
    matters: every city stands on dry land, and the far field is sea.
    """
    board, elevation = shipped_board(), shipped_elevation()
    raw = base64.b64decode(elevation["data"])
    w, h = elevation["width"], elevation["height"]
    waterline = elevation["sea_level"] / elevation["scale"] * 255

    def at(fx, fy):
        col = min(w - 1, max(0, round(fx * (w - 1))))
        row = min(h - 1, max(0, round(fy * (h - 1))))
        return raw[row * w + col]

    for city in board["cities"]:
        assert at(city["x"], city["y"]) > waterline, (
            f"{city['name']} is under water"
        )

    # The corners of the field are far from any hull and must be open sea.
    for fx, fy in ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)):
        assert at(fx, fy) < waterline, "the corner of the field is not sea"


def test_the_coast_does_not_wander_off_the_map():
    """The wobble is bounded, and two margins downstream depend on it.

    board3d.js bounds the terrain mesh CLIP_MARGIN outside the hull and sizes
    the printed sheet wider than that again. If the shoreline could wander
    arbitrarily far it would run past both -- seabed hanging off the edge of
    the board, which is exactly what happened at the first attempt. This pins
    the invariant those constants are chosen against.
    """
    from scripts.build_elevation import COAST_WOBBLE

    board, elevation = shipped_board(), shipped_elevation()
    raw = base64.b64decode(elevation["data"])
    w, h = elevation["width"], elevation["height"]
    waterline = elevation["sea_level"] / elevation["scale"] * 255
    frame_w, frame_h = elevation["frame_units"]

    rings = [
        [(px * frame_w, py * frame_h) for px, py in mass["hull"]]
        for mass in board["landmasses"]
    ]

    # Generous: the shelf is taken from the perturbed distance, so land may sit
    # a shelf-width beyond where the wobble alone would put it.
    allowed = COAST_WOBBLE + 40.0

    worst = 0.0
    for row in range(h):
        pz = row / (h - 1) * frame_h
        for col in range(w):
            if raw[row * w + col] <= waterline:
                continue
            px = col / (w - 1) * frame_w
            if any(mapview._point_in_poly(px, pz, r) for r in rings):
                continue
            worst = max(worst, min(_ring_distance(r, px, pz) for r in rings))

    assert worst <= allowed, (
        f"land stands {worst:.0f} units outside the hull, past the {allowed:.0f} "
        "the renderer's clip margin and sheet are sized for"
    )


def _ring_distance(ring, px, pz):
    import math

    best = float("inf")
    j = len(ring) - 1
    for i in range(len(ring)):
        ax, az = ring[j]
        bx, bz = ring[i]
        dx, dz = bx - ax, bz - az
        length2 = dx * dx + dz * dz or 1.0
        t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / length2))
        best = min(best, math.hypot(px - (ax + dx * t), pz - (az + dz * t)))
        j = i
    return best


def test_high_terrain_cities_stand_above_low_ones():
    """The one thing in this model that is data, and it has to survive.

    Terrain labels are the only real input to the elevation. If a city on
    mountains did not end up above a city on plains, the model would have
    stopped reading the map and started decorating it.
    """
    from scripts.build_elevation import TERRAIN_ELEV, TERRAIN_FALLBACK

    board, elevation = shipped_board(), shipped_elevation()
    raw = base64.b64decode(elevation["data"])
    w, h = elevation["width"], elevation["height"]

    def at(city):
        col = min(w - 1, max(0, round(city["x"] * (w - 1))))
        row = min(h - 1, max(0, round(city["y"] * (h - 1))))
        return raw[row * w + col]

    def profile(city):
        label = city["terrain"][0] if city["terrain"] else None
        return TERRAIN_ELEV.get(label, TERRAIN_FALLBACK)[0]

    ranked = sorted(board["cities"], key=profile)
    lowest, highest = ranked[0], ranked[-1]
    assert profile(highest) > profile(lowest), "map has no terrain variety to check"
    assert at(highest) > at(lowest), (
        f"{highest['name']} ({highest['terrain']}) is not standing above "
        f"{lowest['name']} ({lowest['terrain']})"
    )


# ---------------------------------------------------------------------------
# --map, when it points outside the repository
# ---------------------------------------------------------------------------


def test_a_map_outside_the_repository_builds_from_the_file_it_was_given(tmp_path):
    """`--map` may point anywhere, and the builder must read what it was handed.

    Only the basename used to be carried across to `positions()`, which
    resolved it again under `maps/`. A custom filename named nothing there and
    raised; the board is built from a path, so that broke the option outright.
    """
    custom = tmp_path / "a_map_by_another_name.json"
    custom.write_text(MAP_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    board = build_board(custom)
    assert len(board["cities"]) == len(json.loads(MAP_PATH.read_text())["cities"])


def test_a_borrowed_basename_does_not_borrow_the_other_map_s_land(tmp_path):
    """The quiet half, and the worse one.

    A supplied map whose basename matches a bundled one resolved to the
    bundled file for positions, so the towns came from the map on disk and the
    landmass hulls from a different world: on a shifted copy of
    `starter_map.json` the cities spanned x 0.03..0.22 and the hulls
    0.07..0.94. The board drew land where there was no town and towns off the
    land, and nothing failed.
    """
    shifted = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    for city in shifted["cities"]:
        city["x"] *= 0.25
        city["y"] *= 0.25
    # The same name a bundled map already has.
    custom = tmp_path / MAP_PATH.name
    custom.write_text(json.dumps(shifted), encoding="utf-8")

    board = build_board(custom)
    xs = [city["x"] for city in board["cities"]]
    ys = [city["y"] for city in board["cities"]]
    assert max(xs) <= 0.30, "the towns are not the supplied map's"

    margin = 0.2
    for mass in board["landmasses"]:
        for hx, hy in mass["hull"]:
            assert min(xs) - margin <= hx <= max(xs) + margin, (
                f"{mass['name']} is drawn at x={hx:.3f}, away from its own towns"
            )
            assert min(ys) - margin <= hy <= max(ys) + margin, (
                f"{mass['name']} is drawn at y={hy:.3f}, away from its own towns"
            )
