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
