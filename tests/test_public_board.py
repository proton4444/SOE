"""The poster's board is the 2D map's board, and stays that way.

`webapp/static/public/board.js` is generated from `maps/calib_12.json` by
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

MAP_PATH = REPO_ROOT / "maps" / "calib_12.json"
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
        "board.js is out of date with maps/calib_12.json. "
        "Regenerate with: python -m scripts.build_public_board"
    )


@pytest.mark.parametrize("field", PARITY_CITY_FIELDS)
def test_every_city_carries_the_parity_field(field):
    for city in shipped_board()["cities"]:
        assert field in city, f"{city.get('id')} is missing {field}"


def test_city_values_are_the_map_values():
    source = {c["id"]: c for c in json.loads(MAP_PATH.read_text("utf-8"))["cities"]}
    for city in shipped_board()["cities"]:
        origin = source[city["id"]]
        for field in PARITY_CITY_FIELDS:
            if field in ("x_miles", "y_miles"):
                assert city[field] == pytest.approx(origin[field], abs=0.05)
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
    layout = mapview.layout_for_map("calib_12.json", source)
    expected = mapview.compute_landmasses(
        source["cities"], source["roads"], mapview.positions("calib_12.json")
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
    hull = board["landmasses"][0]["hull"]
    for city in board["cities"]:
        assert mapview._point_in_poly(city["x"], city["y"], hull), (
            f"{city['name']} is outside its own landmass"
        )


def test_region_anchors_cover_every_region():
    board = shipped_board()
    named = {city["region"] for city in board["cities"]}
    assert {r["name"] for r in board["regions"]} == named
    assert sum(r["cities"] for r in board["regions"]) == len(board["cities"])


def test_landmass_name_does_not_depend_on_set_ordering():
    """calib_12 splits 4/4/4, and a tie must not be broken by hash order.

    `max(set(regions), key=regions.count)` picked whichever tied region set
    iteration happened to yield first, so the same map named its landmass
    differently between processes -- in the map title and in the legend.
    Shuffling the input here stands in for the hash seed changing.
    """
    source = json.loads(MAP_PATH.read_text("utf-8"))
    pos = mapview.positions("calib_12.json")
    baseline = mapview.compute_landmasses(source["cities"], source["roads"], pos)

    names = {mass["name"] for mass in baseline}
    for rotation in range(1, len(source["cities"])):
        rotated = source["cities"][rotation:] + source["cities"][:rotation]
        masses = mapview.compute_landmasses(rotated, source["roads"], pos)
        assert {m["name"] for m in masses} == names

    regions = sorted({c["region"] for c in source["cities"]})
    assert baseline[0]["name"] == regions[0], (
        "a three-way tie should settle on the alphabetically first region"
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


def test_the_sea_is_at_sea_level_and_the_land_is_not():
    """The shelf reaches zero at the shore, and only inside the hull is it not.

    A model that leaked height outside the coast would put mountains in the
    water; one that never rose would be a flat board with a heightmap file
    next to it, which is the failure this whole change exists to undo.
    """
    board, elevation = shipped_board(), shipped_elevation()
    raw = base64.b64decode(elevation["data"])
    w, h = elevation["width"], elevation["height"]
    hull = board["landmasses"][0]["hull"]

    # A point well outside the hull is sea.
    assert raw[0] == 0, "the top-left corner of the field is not sea"

    # Every city stands on ground above sea level.
    for city in board["cities"]:
        col = min(w - 1, max(0, round(city["x"] * (w - 1))))
        row = min(h - 1, max(0, round(city["y"] * (h - 1))))
        assert raw[row * w + col] > 0, f"{city['name']} is at sea level"

    # And the hull's own vertices are at (or within a cell of) the waterline,
    # because the shelf falls to zero there.
    for fx, fy in hull:
        col = min(w - 1, max(0, round(fx * (w - 1))))
        row = min(h - 1, max(0, round(fy * (h - 1))))
        assert raw[row * w + col] <= 8, "the shore is not at the waterline"


def test_hill_cities_stand_above_plain_cities():
    """The one thing in this model that is data, and it has to survive.

    Terrain labels are the only real input to the elevation. If a hills city
    did not end up higher than a plain city, the model would have stopped
    reading the map and started decorating it.
    """
    board, elevation = shipped_board(), shipped_elevation()
    raw = base64.b64decode(elevation["data"])
    w, h = elevation["width"], elevation["height"]

    def at(city):
        col = min(w - 1, max(0, round(city["x"] * (w - 1))))
        row = min(h - 1, max(0, round(city["y"] * (h - 1))))
        return raw[row * w + col]

    hills = [c for c in board["cities"] if "hills" in c["terrain"]]
    plain = [c for c in board["cities"] if c["terrain"] == ["plain"]]
    assert hills and plain
    assert min(at(c) for c in hills) > max(at(c) for c in plain), (
        "hill cities are not standing above plain cities"
    )
