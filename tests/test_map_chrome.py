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
