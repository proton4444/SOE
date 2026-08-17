"""Generate the poster page's atlas relief board from the calibration map.

The public page ships static files only. It fetches one replay JSON and nothing
else, so the board topology is baked into a JS constant rather than loaded at
runtime.

Amendment 2 (see docs/MARKETING_CLOSED_ALPHA.md) opened this boundary. The
board used to carry coordinate topology alone -- id, name, x/y, one terrain
label, the ruin flag -- and the page drew twelve mounds on empty paper. It read
as a different world from the one the game draws, because it was: the 2D map a
coach opens carries a named landmass, ports, populations, grid references and
road mileages, and none of that crossed. Now all of it does.

The landmass is the part to be careful about. `maps/calib_12.json` has no
coastline and no paired geography file, so `webapp/mapview.py` falls back to a
padded convex hull of the road-connected cities. That hull is a confine, not a
survey. This script does not re-derive it: it calls the same
`compute_landmasses` the 2D map calls and maps the polygon it returns back
through the layout into fractional coordinates, so the poster draws the same
shape the app draws rather than a lookalike computed twice.

    python -m scripts.build_public_board
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from webapp.mapview import (  # noqa: E402
    compute_landmasses,
    layout_for_map,
    positions,
)

# Private on purpose -- it is mapview's own helper, and the movement cost the
# poster prints has to be the number the 2D map prints, not a second
# implementation of the same formula that can drift away from it.
from webapp.mapview import _hop_cost_for_raw_road  # noqa: E402

DEFAULT_MAP = REPO_ROOT / "maps" / "calib_12.json"
DEFAULT_OUT = REPO_ROOT / "webapp" / "static" / "public" / "board.js"

HEADER = """\
// Atlas relief board, generated from maps/calib_12.json by
// scripts/build_public_board.py. Do not hand-edit.
//
// Twelve cities at their exact x/y with their populations, grid references,
// terrain, port and magic-free flags and regions; the roads with quality,
// mileage and movement cost; and the landmass hull that webapp/mapview.py
// draws for this map, mapped from its SVG frame into the same 0..1 fractions
// the cities use. The hull is a road-connectivity confine, not a surveyed
// coast -- calib_12.json has no geography file. See Amendment 2 in
// docs/MARKETING_CLOSED_ALPHA.md.
const ATLAS_BOARD = """


def _round(value: float, places: int = 4) -> float:
    """Trim float noise so a regenerated board diffs only when it changed."""
    return round(float(value), places)


def build_board(map_path: Path) -> dict:
    source = json.loads(map_path.read_text(encoding="utf-8"))
    map_file = map_path.name

    layout = layout_for_map(map_file, source)
    pos = positions(map_file)

    cities = [
        {
            "id": city["id"],
            "name": city["name"],
            "x": city["x"],
            "y": city["y"],
            "x_miles": _round(city["x_miles"], 1),
            "y_miles": _round(city["y_miles"], 1),
            "terrain": list(city["terrain"]),
            "population": city["population"],
            "population_band": city["population_band"],
            "grid_ref": city["grid_ref"],
            "region": city["region"],
            "is_ruin": city["is_ruin"],
            "is_port": city["is_port"],
            "is_magic_free": city["is_magic_free"],
        }
        for city in source["cities"]
    ]

    roads = []
    for road in source["roads"]:
        cost = _hop_cost_for_raw_road(road)
        roads.append(
            {
                "from": road["from"],
                "to": road["to"],
                "quality": road["quality"],
                "distance_miles": road.get("distance_miles"),
                "move_cost": None if cost is None else _round(cost, 1),
            }
        )

    return {
        "map": map_file,
        "field_miles": [layout.field_w_mi, layout.field_h_mi],
        "landmasses": _landmasses_in_fractions(source, pos, layout),
        "regions": _region_anchors(source["cities"]),
        "cities": cities,
        "roads": roads,
    }


def _landmasses_in_fractions(source: dict, pos: dict, layout) -> list[dict]:
    """The 2D map's own hulls, carried from its SVG frame into 0..1 fractions.

    `project_miles` places a mile coordinate at `pad + (mi / field) * map_extent`;
    this inverts that. The hull is padded outward from the cities, so points
    outside 0..1 are expected and are not clamped -- clamping would flatten the
    shore against the field edge.
    """
    masses = compute_landmasses(source["cities"], source["roads"], pos)
    out = []
    for mass in masses:
        # Six places, not the usual four. A fraction is multiplied by the frame
        # extent on the way back, so 1e-4 here is 0.12px of shoreline there --
        # small, but this polygon is meant to BE the 2D map's, and a test says
        # so to a tolerance the rounding would otherwise set.
        hull = [
            [
                _round((px - layout.pad_x) / layout.map_w, 6),
                _round((py - layout.pad_y) / layout.map_h, 6),
            ]
            for px, py in mass["hull"]
        ]
        out.append(
            {
                "index": mass["index"],
                "name": mass["name"],
                "kind": mass["kind"],
                "city_ids": mass["city_ids"],
                "hull": hull,
            }
        )
    return out


def _region_anchors(cities: list[dict]) -> list[dict]:
    """One label anchor per region, at the mean of that region's cities.

    The 2D map names the landmass and leaves the regions to the city rows.
    Twelve cities split 4/4/4 here, so a single landmass name tells a reader
    about a third of the board; three anchors tell them all of it.
    """
    grouped: dict[str, list[dict]] = {}
    for city in cities:
        region = city.get("region")
        if region:
            grouped.setdefault(region, []).append(city)

    anchors = []
    for name in sorted(grouped):
        members = grouped[name]
        anchors.append(
            {
                "name": name,
                "x": _round(sum(c["x"] for c in members) / len(members)),
                "y": _round(sum(c["y"] for c in members) / len(members)),
                "cities": len(members),
            }
        )
    return anchors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    board = build_board(args.map)
    body = json.dumps(board, indent=2, ensure_ascii=False)
    args.out.write_text(HEADER + body + ";\n", encoding="utf-8")

    terrains = sorted({t for city in board["cities"] for t in city["terrain"]})
    masses = ", ".join(
        f"{m['name']} ({len(m['city_ids'])})" for m in board["landmasses"]
    )
    print(
        f"{args.out}: {len(board['cities'])} cities, "
        f"{len(board['roads'])} roads, terrain {', '.join(terrains)}\n"
        f"  landmasses: {masses}\n"
        f"  regions: {', '.join(r['name'] for r in board['regions'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
