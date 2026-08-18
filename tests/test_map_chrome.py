"""The map's chrome: the scale bar, and whether it tells the truth.

The map has always been drawn to scale -- towns carry mile coordinates, routes
are priced in miles, and the engine moves 10 miles a turn -- and it has never
said so anywhere on the page. Every distance on it was unreadable.

A scale bar that is merely present is worse than none, so the test that counts
is not that it renders: it is that the miles it claims and the miles the map
projects are the same number.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from webapp import mapview

GEO_MAP = "world2.json"


@pytest.fixture(scope="module")
def layout():
    return mapview.layout_for_map(GEO_MAP)


def units_per_mile_from_projection(layout) -> float:
    """What the map actually does, measured off two towns far apart.

    Not read from the layout -- measured through `city_miles` and
    `project_miles`, the same path the towns themselves are drawn by, so a
    bar that agrees with this agrees with the map and not with an intention.
    """
    cities = mapview.load_raw_map(GEO_MAP)["cities"]
    best = None
    for a in cities:
        for b in cities:
            ax, ay = mapview.city_miles(a, layout)
            bx, by = mapview.city_miles(b, layout)
            miles = math.hypot(bx - ax, by - ay)
            if best is None or miles > best[0]:
                best = (miles, a, b)
    miles, a, b = best
    ax, ay = layout.project_miles(*mapview.city_miles(a, layout))
    bx, by = layout.project_miles(*mapview.city_miles(b, layout))
    return math.hypot(bx - ax, by - ay) / miles


def test_the_scale_bar_is_on_the_map():
    svg = mapview.render_svg(GEO_MAP)
    assert 'class="map-scale"' in svg
    assert "MILES" in svg


def test_the_bar_measures_what_the_map_projects(layout):
    """The one test worth having: a bar that lies is worse than no bar."""
    svg = mapview.render_svg(GEO_MAP)
    group = re.search(r'<g class="map-scale"[^>]*>(.*?)</g>', svg, re.DOTALL)
    assert group, "no scale bar group in the SVG"

    # Four alternating segments; their combined width is the bar.
    widths = [float(w) for w in re.findall(r'<rect x="[\d.]+" y="0" width="([\d.]+)"', group.group(1))]
    assert len(widths) == 4
    drawn = sum(widths)

    miles = mapview.scale_bar_miles(layout)
    assert f">{miles}</text>" in group.group(1), "the bar's end is not labelled with its own length"

    expected = miles * units_per_mile_from_projection(layout)
    assert abs(drawn - expected) / expected < 0.01


def test_the_bar_is_a_number_a_person_can_hold():
    layout = mapview.layout_for_map(GEO_MAP)
    assert mapview.scale_bar_miles(layout) in mapview._SCALE_STEPS


def test_the_bar_is_a_sensible_share_of_the_frame(layout):
    miles = mapview.scale_bar_miles(layout)
    share = miles / layout.field_w_mi
    assert 0.08 <= share <= 0.30, f"a bar spanning {share:.0%} of the map is not a ruler"


def test_the_bar_sits_inside_the_frame(layout):
    """A bar clipped by the viewBox is a bar nobody can read."""
    svg = mapview.render_svg(GEO_MAP)
    transform = re.search(r'<g class="map-scale"[^>]*transform="translate\(([\d.]+),([\d.]+)\)"', svg)
    assert transform
    x, y = float(transform.group(1)), float(transform.group(2))
    length = mapview.scale_bar_miles(layout) * layout.map_w / layout.field_w_mi
    assert x >= 0 and y >= 0
    assert x + length <= layout.width
    # The caption and the labels live either side of the bar itself.
    assert y - 19 >= 0
    assert y + 18 <= layout.height


# ---------------------------------------------------------------------------
# landmass captions
# ---------------------------------------------------------------------------

CAPTION_RE = re.compile(
    r'<text class="map-label land-label" x="([\d.]+)" y="([\d.]+)"[^>]*'
    r'font-size="([\d.]+)"[^>]*>([^<]+)<'
)

#: Glyph width plus tracking, in ems. Mirrors the estimate the renderer sizes
#: the caption with; if one moves the other has to.
CAPTION_EM = 0.96


def captions(svg: str):
    for match in CAPTION_RE.finditer(svg):
        x, y, size, name = match.groups()
        yield {
            "x": float(x),
            "y": float(y),
            "size": float(size),
            "name": name,
            "width": len(name) * float(size) * CAPTION_EM,
        }


def test_a_caption_never_leaves_the_frame(layout):
    """ZELANSTEAD HINTERLAND used to run off the edge, clipped mid-word."""
    found = list(captions(mapview.render_svg(GEO_MAP)))
    assert found, "the map has landmasses and none of them is captioned"
    for caption in found:
        assert caption["x"] - caption["width"] / 2 >= 0
        assert caption["x"] + caption["width"] / 2 <= layout.width
        assert 0 <= caption["y"] <= layout.height


def test_a_caption_sits_on_the_land_it_names():
    """Horizontally within its own hull, and vertically inside its span.

    Placed at the top of the hull it floated over the sea above the widest
    point, which on the island put half the name in open water.
    """
    stats = mapview.map_stats(GEO_MAP)
    hulls = {m["name"].upper(): m["hull"] for m in stats["masses"] if m.get("hull")}
    for caption in captions(mapview.render_svg(GEO_MAP)):
        hull = hulls.get(caption["name"])
        assert hull, f"caption {caption['name']!r} names no landmass on this map"
        left = min(p[0] for p in hull)
        right = max(p[0] for p in hull)
        top = min(p[1] for p in hull)
        bottom = max(p[1] for p in hull)
        assert caption["x"] - caption["width"] / 2 >= left - 1
        assert caption["x"] + caption["width"] / 2 <= right + 1
        assert top < caption["y"] < bottom


def test_no_two_landmasses_answer_to_the_same_name():
    """A region can straddle water, and two masses took the same name from it.

    world2's mainland and a one-town islet were both "Fenavale fold", so the
    roster listed the same place twice and a caption could not say which it
    named.
    """
    names = [m["name"] for m in mapview.map_stats(GEO_MAP)["masses"]]
    assert len(names) == len(set(names))


def test_land_too_narrow_for_its_name_goes_uncaptioned():
    """world2 has three landmasses and a 17-cell islet is not one to write on."""
    stats = mapview.map_stats(GEO_MAP)
    named = {c["name"] for c in captions(mapview.render_svg(GEO_MAP))}
    assert len(named) < len(stats["masses"])


def test_a_caption_is_sized_to_its_land():
    """The island's name is set smaller than the mainland's, because it must."""
    sizes = {c["name"]: c["size"] for c in captions(mapview.render_svg(GEO_MAP))}
    assert len(sizes) >= 2
    stats = mapview.map_stats(GEO_MAP)
    widths = {
        m["name"].upper(): max(p[0] for p in m["hull"]) - min(p[0] for p in m["hull"])
        for m in stats["masses"]
        if m.get("hull")
    }
    ordered = sorted(sizes, key=lambda name: widths[name])
    assert sizes[ordered[0]] <= sizes[ordered[-1]]


# ---------------------------------------------------------------------------
# visual hierarchy
# ---------------------------------------------------------------------------


def route_ink(map_file: str) -> dict[str, float]:
    """Stroke area per route class: length x width x the lit part of the dash.

    A crude proxy for visual weight, but an objective one, and it caught what
    looking could not put a number on.
    """
    layout = mapview.layout_for_map(map_file)
    data = mapview.load_raw_map(map_file)
    pos = mapview.positions(map_file)
    sailed = (mapview.load_geography(map_file) or {}).get("sea_routes") or {}

    ink: dict[str, float] = {}
    for road in data["roads"]:
        try:
            _, width, dash = mapview._ROAD_STYLES[mapview.RoadQuality(road["quality"])]
        except (KeyError, ValueError):
            continue
        path = sailed.get(road["id"])
        if path:
            points = [layout.project_miles(x, y) for x, y in path]
            length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
        else:
            a, b = pos.get(road["from"]), pos.get(road["to"])
            if not a or not b:
                continue
            length = math.dist(a, b)
        lit = 1.0
        if dash != "none":
            parts = [float(v) for v in dash.split()]
            lit = parts[0] / sum(parts)
        key = "sea" if road["quality"] == "sea" else "land"
        ink[key] = ink.get(key, 0.0) + length * width * lit
    return ink


def test_sea_lanes_support_the_network_rather_than_dominate_it():
    """Nineteen routes were carrying 41% of the network's ink.

    A lane is long -- 273 units against a road's 48 -- so drawn at road weight
    it reads as the subject of the map, which on a map about marching is the
    wrong subject. Thinner and more broken brings it back to a fifth.
    """
    ink = route_ink(GEO_MAP)
    share = ink["sea"] / ink["land"]
    assert share < 0.30, f"sea lanes carry {share:.0%} of the road network's ink"


def test_the_lanes_are_still_visible_at_all():
    """The other direction: a lane nobody can see is a lane nobody can use."""
    ink = route_ink(GEO_MAP)
    assert ink["sea"] / ink["land"] > 0.10


def test_the_bar_clears_the_landmass_roster():
    """Both live bottom-left, and on a sparse map they were drawn on top of
    each other -- the roster panel straight through the ruler."""
    svg = mapview.render_svg("calib_12.json")
    bar = re.search(r'<g class="map-scale"[^>]*transform="translate\([\d.]+,([\d.]+)\)"', svg)
    roster = re.search(
        r'<g class="map-island-roster"[^>]*>\s*<rect x="[\d.-]+" y="([\d.-]+)"', svg
    )
    assert bar and roster, "this map should carry both"
    assert float(bar.group(1)) + 18 <= float(roster.group(1))


def test_a_map_without_geography_gets_no_bar(tmp_path, monkeypatch):
    """Without a mile field the frame is nominal, and a bar would be invented.

    The toy maps place towns by fraction only. Drawing a ruler on one would be
    stating a distance nothing recorded.
    """
    toy = {
        "cities": [
            {"id": "a", "name": "A", "x": 0.2, "y": 0.2, "terrain": ["plain"]},
            {"id": "b", "name": "B", "x": 0.8, "y": 0.7, "terrain": ["plain"]},
        ],
        "roads": [],
    }
    (tmp_path / "toy.json").write_text(json.dumps(toy), encoding="utf-8")
    # Both the loader and the geography pairing resolve through service's
    # maps directory, so that is the one thing to redirect.
    from webapp import service

    monkeypatch.setattr(service, "_MAPS_DIR", tmp_path)

    layout = mapview.layout_for_map("toy.json")
    assert not layout.has_geography
    assert mapview._scale_bar(layout) == ""
    assert 'class="map-scale"' not in mapview.render_svg("toy.json")


# ---------------------------------------------------------------------------
# label collisions
# ---------------------------------------------------------------------------
#
# Every permanent label on a sparse map used to be placed with no knowledge
# of any other. Town names and captions were laid out against each other,
# and mile labels were not laid out at all -- each one went to its own
# route's control point and printed through whatever was already there.
#
# On `calib_12_fbm` that was nine collisions, which is how "167 mi · 53.4 mv"
# and "0 · C4 · ruin · port · plain" became one line nobody could read.

PLAYABLE_MAPS = [
    "starter_map.json",
    "calib_12.json",
    "calib_12_fbm.json",
    "calib_12_s2.json",
    "calib_12_s3.json",
    "calib_24.json",
    "calib_48.json",
    "world.json",
    "world2.json",
]


def overlapping_labels(map_file: str):
    boxes = mapview.occupied_label_boxes(mapview.render_svg(map_file))
    return [
        (a, b)
        for i, a in enumerate(boxes)
        for b in boxes[i + 1 :]
        if mapview._boxes_overlap(a, b, pad=0.0)
    ]


@pytest.mark.parametrize("map_file", PLAYABLE_MAPS)
def test_no_two_permanent_labels_print_over_each_other(map_file):
    """The invariant the map never had.

    One exception, and the planner declares it: on a dense map a town whose
    name fits in none of its eight slots gets it anyway, because an unnamed
    town is worse than a crowded one. That licenses two *names* touching.
    It does not license a caption or a mile label landing on anything.
    """
    for a, b in overlapping_labels(map_file):
        assert "city-name" in a.cls and "city-name" in b.cls, (
            f"{map_file}: {a.text!r} prints over {b.text!r}"
        )
        assert len(mapview.load_raw_map(map_file)["cities"]) >= 24, (
            f"{map_file} is not crowded enough to excuse {a.text!r} on {b.text!r}"
        )


@pytest.mark.parametrize("map_file", PLAYABLE_MAPS)
def test_every_town_still_says_its_name(map_file):
    """Decluttering must not be achieved by dropping towns off the map."""
    svg = mapview.render_svg(map_file)
    for city in mapview.load_raw_map(map_file)["cities"]:
        assert f'data-city="{city["id"]}"' in svg


def test_the_box_model_knows_which_face_it_is_measuring():
    """The bug that made the model agree the map was clean when it was not.

    Captions are set in a monospace face and names in a serif one. Measured
    in the browser off the drawn SVG, the monospace advance is 0.602em a
    glyph against at most 0.54em for the serif -- so one width for both left
    every caption box about 15% short, and labels that overlapped measured
    clear.
    """
    assert mapview.LABEL_EM_MONO > mapview.LABEL_EM_SERIF
    assert mapview.LABEL_EM_MONO >= 0.602  # measured, not guessed
    assert mapview.LABEL_EM_SERIF >= 0.54

    text = "655 · H10 · port · desert"
    mono = mapview._label_box_at(
        100, 100, text, 8.5, "middle", em_width=mapview.LABEL_EM_MONO
    )
    serif = mapview._label_box_at(
        100, 100, text, 8.5, "middle", em_width=mapview.LABEL_EM_SERIF
    )
    assert (mono[2] - mono[0]) > (serif[2] - serif[0])


def test_a_translated_group_is_measured_where_it_is_drawn():
    """The scale bar and the compass are translated into their corner.

    Read flat, their text measures as if it sat at the top-left of the
    frame, where it collides with the title and reserves space nothing is
    using.
    """
    fragment = (
        '<g transform="translate(400.0,700.0)">'
        '<text x="10" y="20" font-size="10" text-anchor="middle">MILES</text>'
        "</g>"
    )
    (box,) = mapview.occupied_label_boxes(fragment)
    assert box.left > 300 and box.top > 600


def test_a_route_keeps_the_label_place_it_has_always_had():
    """A route with room around it does not move. Only a blocked one does."""
    a, b = (100.0, 100.0), (500.0, 100.0)
    road = {"id": "r1", "from": "a", "to": "b", "quality": "good", "distance_miles": 90}
    control = mapview._road_control_point(a, b, "r1")
    placed = mapview.plan_road_labels(
        [road], {"a": a, "b": b}, {}, reserved=[]
    )
    assert placed["r1"] == (control[0], control[1] + mapview.ROAD_LABEL_DY_LAND)


def test_a_label_with_nowhere_to_go_is_dropped_rather_than_overprinted():
    """The distance survives in the tooltip, where an unreadable one did not."""
    a, b = (100.0, 100.0), (500.0, 100.0)
    road = {"id": "r1", "from": "a", "to": "b", "quality": "good", "distance_miles": 90}
    placed = mapview.plan_road_labels(
        [road], {"a": a, "b": b}, {}, reserved=[(-1e4, -1e4, 1e4, 1e4)]
    )
    assert placed["r1"] is None

    drawn = mapview._route_svg(road, a, b, label_visible=False)
    assert "<text" not in drawn
    assert "90 mi" in drawn  # the <title> still carries it

    printed = mapview._route_svg(road, a, b, label_visible=True)
    assert f">{mapview.road_label_text(road)}</text>" in printed


def test_a_town_with_nowhere_for_its_caption_keeps_its_name():
    """Last resort on a sparse map: the caption goes to hover, the name stays.

    The name is what the map owes a town. The caption is detail, and the
    tooltip carries it whether or not it is printed.
    """
    cities = [
        {
            "id": f"c{i}",
            "name": f"Town{i}",
            "population": 40000,
            "population_band": "10k-99k",
            "grid_ref": "A1",
            "terrain": ["plain"],
        }
        for i in range(6)
    ]
    pos = {f"c{i}": (300.0 + i * 12.0, 300.0) for i in range(6)}
    plan = mapview._plan_city_labels(cities, pos)
    assert all(p.name_mode == "always" for p in plan.values())
    assert any(p.meta_mode == "hover" for p in plan.values()), (
        "six towns stacked on top of each other and every caption still fits"
    )


def test_the_land_does_not_repeat_the_roster_across_itself():
    """The engraved name is underprint and reads as one; a solid kind/count
    line at the same point is a label, and it printed through whichever town
    stood there -- while the roster in the corner already says it."""
    svg = mapview.render_svg("calib_12_fbm.json")
    assert "land-label-meta" not in svg
    assert "land-label" in svg  # the engraved name itself stays
    assert "continent" in svg  # the roster still says what kind it is
    assert "12 cities" in svg


def test_a_force_badge_may_sit_against_a_town_name():
    """The one label allowed to touch another, and why.

    A live board's force badge is drawn on its own opaque panel and set
    beside the name. Planning names around it would move them whenever a
    force moved, and a board whose town names walk about between turns is
    worse than one where a badge abuts a name.
    """
    overlay = {"cities": {"zeleis": {"units": 12, "ships": 2, "observed": True}}}
    live = mapview.render_svg("calib_12_fbm.json", overlay)
    assert "12▲" in live

    def names(svg):
        return sorted(
            (box.text, round(box.left, 1), round(box.top, 1))
            for box in mapview.occupied_label_boxes(svg)
            if "city-name" in box.cls
        )

    assert names(live) == names(mapview.render_svg("calib_12_fbm.json"))


def test_the_box_model_is_measured_against_the_faces_the_map_sets():
    """The constants are measurements, and a measurement names its subject.

    Change the font stack and the numbers stop describing anything, silently
    -- which is exactly how a caption box came to be 15% short. If this
    fails, re-measure with `python -m scripts.check_map_labels --browser`
    before touching the constants.
    """
    defs = mapview._defs()
    assert '.map-meta { font-family: ui-monospace, Consolas, monospace; }' in defs
    assert '.map-label { font-family: Georgia, "Times New Roman", serif; }' in defs


def test_the_label_audit_runs_and_passes_over_the_maps_we_ship():
    """The report an operator reads is the invariant this file holds.

    Without the browser: this is the renderer's own box model checking
    itself, which is worth having and is not proof. `--browser` is the
    proof, and needs Playwright and a Chromium this machine may not have.
    """
    from scripts import check_map_labels

    assert check_map_labels.main([]) == 0
