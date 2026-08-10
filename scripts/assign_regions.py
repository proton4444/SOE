"""
Give every town the name of the landmass it stands on.

The gazetteer names towns but never the lands they belong to. Those names
exist only as labels painted on the gamemaster's raster, so this is the one
stage of the pipeline that cannot be derived end to end: the fifteen labels
below were read off the raster by eye.

Everything after the transcription *is* derived. Each label's anchor is
converted from raster pixels to miles, matched to the nearest coastline in
``maps/soe_geography.json``, and every town inside (or nearest to) that
coastline takes its name. The match is checked for bijection - fifteen
labels, fifteen coastlines, one each - so a mis-transcribed anchor fails
loudly instead of quietly relabelling half the world.

Four labels are set in the map's smallest, most horizontally squeezed face
and are marked ``certain=False``. Their letters are genuinely ambiguous at
586px; correct them here and re-run if you have a better source.

Usage:
    python scripts/assign_regions.py [--report]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_geography import FIELD, px_to_miles  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / "maps" / "soe_world.json"
GEOGRAPHY = ROOT / "maps" / "soe_geography.json"

# A town further than this from every coastline is reported rather than
# labelled: solved positions carry a median residual of ~15 miles, so a
# town a little offshore still belongs to the land it sits beside.
MAX_ORPHAN_MILES = 60.0

# Region name, the bounding box of its blue label in raster pixels, and
# whether the letters are legible beyond doubt.
LABELS: list[tuple[str, tuple[int, int, int, int], bool]] = [
    ("Farsanya", (57, 59, 92, 68), True),
    ("Kyupaa", (323, 47, 367, 60), True),
    ("Olighotsi", (196, 63, 240, 74), True),
    ("Uutani", (290, 63, 315, 70), True),
    ("Boriagris", (291, 123, 330, 133), True),
    ("Ajd", (209, 142, 227, 151), False),
    ("Piram Atanki", (35, 167, 68, 183), True),
    ("Juansaye", (496, 174, 532, 183), False),
    ("Ipsen", (271, 219, 301, 227), False),
    ("Lanotro", (147, 261, 178, 268), True),
    ("Rechig", (42, 262, 73, 272), True),
    ("Slamoniya", (389, 292, 450, 304), True),
    ("Hamrika", (238, 304, 277, 313), True),
    ("Taatun", (320, 304, 343, 310), False),
    ("Jlokdiri", (122, 322, 153, 329), True),
]


def _point_segment_miles(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _inside(p, poly) -> bool:
    x, y = p
    hit = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def signed_distance(p, poly) -> float:
    """Miles from p to the coastline; negative when p is inland."""
    d = min(
        _point_segment_miles(p, poly[i], poly[(i + 1) % len(poly)])
        for i in range(len(poly))
    )
    return -d if _inside(p, poly) else d


def label_anchor_miles(box: tuple[int, int, int, int]) -> tuple[float, float]:
    """Centre of a label's pixel bounding box, in miles from the field's corner."""
    x0, y0, x1, y1 = box
    mx, my = px_to_miles((x0 + x1) / 2.0 - FIELD[0], (y0 + y1) / 2.0 - FIELD[2])
    return float(mx), float(my)


def match_labels_to_coastlines(coastlines) -> dict[int, tuple[str, bool]]:
    """Each label claims its nearest coastline; the match must be one to one."""
    claims: dict[int, tuple[str, bool]] = {}
    for name, box, certain in LABELS:
        p = label_anchor_miles(box)
        index = min(
            range(len(coastlines)), key=lambda i: signed_distance(p, coastlines[i])
        )
        if index in claims:
            raise SystemExit(
                f"'{name}' and '{claims[index][0]}' both claim coastline {index}"
            )
        claims[index] = (name, certain)
    missing = sorted(set(range(len(coastlines))) - set(claims))
    if missing:
        raise SystemExit(f"coastlines with no label: {missing}")
    return claims


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="list the assignment")
    args = ap.parse_args()

    world = json.loads(WORLD.read_text(encoding="utf8"))
    coastlines = json.loads(GEOGRAPHY.read_text(encoding="utf8"))["coastlines"]
    claims = match_labels_to_coastlines(coastlines)

    counts: dict[str, int] = {}
    orphans: list[str] = []
    for city in world["cities"]:
        if city.get("x_miles") is None or city.get("y_miles") is None:
            orphans.append(f"{city['name']}: unsolved position")
            continue
        p = (city["x_miles"], city["y_miles"])
        index = min(
            range(len(coastlines)), key=lambda i: signed_distance(p, coastlines[i])
        )
        distance = signed_distance(p, coastlines[index])
        if distance > MAX_ORPHAN_MILES:
            city.pop("region", None)
            orphans.append(f"{city['name']}: {distance:.0f} miles from any coast")
            continue
        name = claims[index][0]
        city["region"] = name
        counts[name] = counts.get(name, 0) + 1

    WORLD.write_text(
        json.dumps(world, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )

    unsure = [name for _, (name, certain) in sorted(claims.items()) if not certain]
    print(f"{sum(counts.values())} towns labelled across {len(counts)} regions")
    if unsure:
        print("transcription not certain: " + ", ".join(unsure))
    if orphans:
        print(f"{len(orphans)} towns left unlabelled")
    if args.report:
        for index, (name, certain) in sorted(claims.items(), key=lambda kv: kv[1][0]):
            mark = "" if certain else "  (name uncertain)"
            print(
                f"  {name:14} coastline {index:2}  {counts.get(name, 0):3} towns{mark}"
            )
        for line in orphans:
            print(f"  ! {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
