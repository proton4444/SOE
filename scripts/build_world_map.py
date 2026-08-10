"""
Convert the gamemaster's map index into an engine map file.

The index (``docs/soe_map_index.txt``) is the authoritative source for the
Spoils of Empire world: it lists every town with its population, terrain,
magic-free status and grid reference, followed by every route out of that
town with its quality and mileage. It is the same data the engine prices
travel and SCAN from, so the map file and the engine cannot disagree.

Usage:
    python scripts/build_world_map.py [--index PATH] [--out PATH]

Route listings are symmetric: each edge appears once under each endpoint.
We keep one Road per (pair, quality) — a pair may legitimately have both a
land route and a water route — and report any mileage disagreement rather
than silently picking a side.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = REPO_ROOT / "docs" / "soe_map_index.txt"
DEFAULT_OUT = REPO_ROOT / "maps" / "soe_world.json"

# Terrain vocabulary used by the gamemaster's map legend.
TERRAIN = {"plain", "forest", "hills", "mountains", "desert", "swamp"}

# The index writes sea lanes as "water"; the engine calls them "sea".
QUALITY_MAP = {
    "excellent": "excellent",
    "good": "good",
    "fair": "fair",
    "poor": "poor",
    "water": "sea",
}

# Grid drawn on the map: columns 1-13, rows A-J (only A-H hold towns).
GRID_COLS = 13
GRID_ROWS = "ABCDEFGHIJ"

HEADER_RE = re.compile(
    r"^(?P<name>[^,\n]+), pop (?P<pop>\d+)"
    r"(?P<attrs>(?:, *[a-z\- ]+)*) *\.+ *(?P<row>[A-J])(?P<col>\d+)\.?\s*$"
)
ROUTE_RE = re.compile(
    r"^\s*(?:Routes to:)?\s*(?P<dest>.+?) - (?P<quality>\w+) - (?P<miles>\d+) miles[,.]\s*$"
)


def slugify(name: str) -> str:
    """Stable city id: 'Yangi Utoran' -> 'yangi_utoran'."""
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", ascii_name.lower())).strip("_")


def population_band(pop: int) -> str:
    """Map an exact population onto the engine's PopulationBand values.

    The bands are the gamemaster's four-tier legend (>100k / 10k-99,999 /
    1k-9,999 / <1k), so this is the same partition the original map's
    symbols use and every band is populated.
    """
    if pop >= 100_000:
        return "100k+"
    if pop >= 10_000:
        return "10k-99k"
    if pop >= 1_000:
        return "1k-9k"
    return "< 1k"


def grid_centre(row: str, col: int) -> tuple[float, float]:
    """Centre of a grid cell as 0..1 fractions, y measured downward."""
    return ((col - 0.5) / GRID_COLS, (GRID_ROWS.index(row) + 0.5) / len(GRID_ROWS))


def parse_index(text: str) -> tuple[list[dict], list[dict]]:
    """Parse the index into raw town records and directed route legs."""
    towns: list[dict] = []
    legs: list[dict] = []
    current: dict | None = None

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue

        header = HEADER_RE.match(line)
        if header:
            attrs = [a.strip() for a in header["attrs"].split(",") if a.strip()]
            current = {
                "name": header["name"].strip(),
                "population": int(header["pop"]),
                "terrain": sorted(a for a in attrs if a in TERRAIN),
                "flags": [a for a in attrs if a not in TERRAIN],
                "row": header["row"],
                "col": int(header["col"]),
                "lineno": lineno,
            }
            towns.append(current)
            continue

        route = ROUTE_RE.match(line)
        if route:
            if current is None:
                raise ValueError(f"line {lineno}: route before any town header")
            legs.append(
                {
                    "from": current["name"],
                    "to": route["dest"].strip(),
                    "quality": route["quality"],
                    "miles": int(route["miles"]),
                    "lineno": lineno,
                }
            )
            continue

        raise ValueError(f"line {lineno}: unrecognised: {line!r}")

    return towns, legs


def build(index_path: Path, out_path: Path) -> list[str]:
    """Build the map file. Returns a list of human-readable anomalies."""
    towns, legs = parse_index(index_path.read_text(encoding="utf-8"))
    problems: list[str] = []

    by_name: dict[str, dict] = {}
    for town in towns:
        if town["name"] in by_name:
            problems.append(f"duplicate town name {town['name']!r}")
        by_name[town["name"]] = town

    ids: dict[str, str] = {}
    for town in towns:
        town_id = slugify(town["name"])
        if town_id in ids:
            problems.append(
                f"id collision {town_id!r}: {ids[town_id]!r} and {town['name']!r}"
            )
        ids[town_id] = town["name"]
        town["id"] = town_id

    for town in towns:
        if not town["terrain"]:
            problems.append(f"{town['name']}: no terrain")
        for flag in town["flags"]:
            if flag != "magic-free":
                problems.append(f"{town['name']}: unknown attribute {flag!r}")

    # Collapse the symmetric listings into one edge per (pair, quality).
    grouped: dict[tuple[frozenset[str], str], list[dict]] = defaultdict(list)
    for leg in legs:
        if leg["to"] not in by_name:
            problems.append(
                f"line {leg['lineno']}: route from {leg['from']} to unknown town "
                f"{leg['to']!r}"
            )
            continue
        if leg["quality"] not in QUALITY_MAP:
            problems.append(f"line {leg['lineno']}: unknown quality {leg['quality']!r}")
            continue
        pair = frozenset({by_name[leg["from"]]["id"], by_name[leg["to"]]["id"]})
        if len(pair) == 1:
            problems.append(f"line {leg['lineno']}: {leg['from']} routes to itself")
            continue
        grouped[(pair, leg["quality"])].append(leg)

    roads = []
    for (pair, quality), members in sorted(
        grouped.items(), key=lambda kv: (sorted(kv[0][0]), kv[0][1])
    ):
        miles = {m["miles"] for m in members}
        if len(miles) > 1:
            problems.append(
                f"{' <-> '.join(sorted(pair))} ({quality}): conflicting mileages "
                f"{sorted(miles)}; using the shorter"
            )
        if len(members) == 1:
            problems.append(
                f"{' <-> '.join(sorted(pair))} ({quality}): listed from only one end"
            )
        a, b = sorted(pair)
        roads.append(
            {
                "id": f"{a}__{b}__{QUALITY_MAP[quality]}",
                "from": a,
                "to": b,
                "quality": QUALITY_MAP[quality],
                "distance_miles": min(miles),
                "bidirectional": True,
            }
        )

    # A town is a port if any sea lane touches it.
    ports = {
        endpoint
        for road in roads
        if road["quality"] == "sea"
        for endpoint in (road["from"], road["to"])
    }

    cities = []
    for town in sorted(towns, key=lambda t: t["id"]):
        x, y = grid_centre(town["row"], town["col"])
        cities.append(
            {
                "id": town["id"],
                "name": town["name"],
                "population_band": population_band(town["population"]),
                "population": town["population"],
                "terrain": town["terrain"],
                "is_port": town["id"] in ports,
                "is_magic_free": "magic-free" in town["flags"],
                "is_ruin": town["population"] == 0,
                "grid_ref": f"{town['row']}{town['col']}",
                "x": round(x, 4),
                "y": round(y, 4),
            }
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"cities": cities, "roads": roads}, indent=2) + "\n",
        encoding="utf-8",
    )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    problems = build(args.index, args.out)
    data = json.loads(args.out.read_text(encoding="utf-8"))
    print(f"wrote {args.out}: {len(data['cities'])} cities, {len(data['roads'])} roads")
    if problems:
        print(f"\n{len(problems)} anomal{'y' if len(problems) == 1 else 'ies'}:")
        for problem in problems:
            print(f"  - {problem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
