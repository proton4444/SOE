"""Generate the poster page's atlas relief board from the calibration map.

The public page ships static files only. It fetches one replay JSON and nothing
else, so the board topology is baked into a JS constant rather than loaded at
runtime.

Only the coordinate topology crosses the boundary: city id, display name, exact
fractional x/y, one terrain label, and the ruin flag. Population, mile
coordinates, grid refs, regions, port and magic-free flags, and road ids and
distances stay in the repo. See docs/MARKETING_CLOSED_ALPHA.md, "Visual
contract: atlas board".

    python -m scripts.build_public_board
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = REPO_ROOT / "maps" / "calib_12.json"
DEFAULT_OUT = REPO_ROOT / "webapp" / "static" / "public" / "board.js"

HEADER = """\
// Atlas relief board topology, generated from maps/calib_12.json.
// Coordinate topology only: twelve cities at their exact x/y, the roads as
// listed, and one terrain label per city. No coastline, no landmass, no
// elevation. Regenerate with scripts/build_public_board.py.
const ATLAS_BOARD = """


def build_board(map_path: Path) -> dict:
    source = json.loads(map_path.read_text(encoding="utf-8"))
    cities = [
        {
            "id": city["id"],
            "name": city["name"],
            "x": city["x"],
            "y": city["y"],
            "terrain": city["terrain"][0],
            "is_ruin": city["is_ruin"],
        }
        for city in source["cities"]
    ]
    roads = [
        {"from": road["from"], "to": road["to"], "quality": road["quality"]}
        for road in source["roads"]
    ]
    return {"map": map_path.name, "cities": cities, "roads": roads}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    board = build_board(args.map)
    body = json.dumps(board, indent=2, ensure_ascii=False)
    args.out.write_text(HEADER + body + ";\n", encoding="utf-8")

    terrains = sorted({city["terrain"] for city in board["cities"]})
    print(
        f"{args.out}: {len(board['cities'])} cities, "
        f"{len(board['roads'])} roads, terrain {', '.join(terrains)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
