"""Generate the atlas board's elevation map.

WHAT THIS IS. A heightmap for a map's landmass, baked to a grid and shipped to
the poster as data. It exists for one reason: the board looks like a world with
it and like a diagram without it. Nothing in the engine reads it. No order, no
movement cost, no combat result depends on a single value in this file --
`soe/config.py` computes movement from road quality and distance, and it will
go on doing that whether this file exists or not.

WHAT IT IS NOT. Survey data. `maps/calib_12.json` carries twelve terrain
LABELS and no elevation whatsoever: no mesh, no heightfield, not one spot
height. The labels are the only real input here. Which cities stand on hills is
data; the shape of the ground between them is this script's invention, and the
poster says so in its legend. See Amendment 3 in docs/MARKETING_CLOSED_ALPHA.md.

WHY IT IS BAKED AND NOT COMPUTED IN THE BROWSER. Three reasons, in order of how
much they matter. It is the same terrain on every machine, which a JS
implementation could promise and would eventually break. It is diffable and
testable -- `tests/test_public_board.py` regenerates it and compares, so a
change to the model cannot land without the shipped bytes changing with it. And
the page does the work once at build time rather than on a phone.

The model, in the order it is applied:

  1. a land mask and a coastal shelf, from the same hull the board draws;
  2. an orographic base, inverse-distance weighted from the city terrain
     labels -- hills raise the ground around them, desert keeps it low;
  3. domain-warped fractal noise for landform, so the contours meander rather
     than sitting in concentric rings around each city;
  4. ridged noise for high ground, folded about its midpoint so that hills and
     mountains get creases and valleys instead of domes;
  5. a shelf multiply, so everything falls to sea level at the shore.

A second channel goes out with it: `sea`, the distance from the shoreline
outward, clamped and quantised the same way. It is not elevation -- the seabed
is flat and stays flat -- it is what lets the renderer grade the water from
shallow at the coast to deep offshore and lay a strand line where the two meet.
Flat water in one tint is the single thing that most made this board read as a
diagram of a map rather than a picture of a world.

    python -m scripts.build_elevation
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.build_public_board import build_board  # noqa: E402

DEFAULT_MAP = REPO_ROOT / "maps" / "calib_12.json"
DEFAULT_OUT = REPO_ROOT / "webapp" / "static" / "public" / "elevation.js"

# Grid resolution. 256 across a 1180-unit frame is one sample every 4.6 units,
# finer than the mesh the board builds from it, so the renderer interpolates
# down rather than inventing detail up. Height is stored as one byte per cell
# against a recorded ceiling: the quantisation step is under a unit, which on a
# 1300-unit board is invisible once the samples are interpolated.
GRID_W = 256
GRID_H = 148

# Board units from the shore to full inland height.
#
# This was 150 and it inverted the map. The hull is a convex hull padded ~72
# units out from the cities, so the whole landmass is barely two shelf widths
# across: at 150 every city sat on the shelf and was scaled down by it, and
# scaled down HARDEST at the edges -- which is exactly where the two hills
# cities are. Drelerford's orographic base is 47.9 against a plain's 14, and
# it was rendering at a twelfth of that while inland plains rendered at full
# height. The board showed hills as hollows.
#
# 30 clears every city on this map: the nearest to the shore is Drelerford at
# 32.8 units. The shelf now does only the job it was for, which is putting the
# ground into the water at the coastline rather than dropping a cliff there.
COAST_SHELF = 30.0

# How far offshore the water goes on being drawn as shallow. Nothing physical:
# it is the width of the colour ramp from strand to open sea.
SEA_RANGE = 210.0

# Elevation profile per terrain label, in board units. The ordering is the
# data -- hills stand above plain, plain above desert -- and the amplitudes are
# presentation, the same bargain every relief map makes.
TERRAIN_ELEV = {
    "plain": (13.0, 8.0),
    "plains": (13.0, 8.0),
    "desert": (8.0, 5.0),
    "hills": (56.0, 30.0),
    "forest": (27.0, 14.0),
    "woods": (27.0, 14.0),
    "mountains": (112.0, 54.0),
    "swamp": (5.0, 3.0),
    "coastal": (8.0, 4.0),
    "river": (10.0, 5.0),
}
TERRAIN_FALLBACK = (13.0, 8.0)

# Softening on the inverse-distance weights, so a city is a region of high
# ground rather than a spike with a city on the point of it.
IDW_SOFT = 2600.0

VERTICAL_EXAGGERATION = 2.6
NOISE_SCALE = 1.0 / 125.0


def _hash(*parts: int) -> int:
    h = 2166136261
    for part in parts:
        value = part & 0xFFFFFFFF
        for _ in range(4):
            h ^= value & 0xFF
            h = (h * 16777619) & 0xFFFFFFFF
            value >>= 8
    return h


def _lattice(ix: int, iz: int, salt: int) -> float:
    return (_hash(ix, iz, salt) % 65536) / 65536.0


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _value_noise(x: float, z: float, salt: int) -> float:
    x0, z0 = math.floor(x), math.floor(z)
    fx, fz = _smoothstep(x - x0), _smoothstep(z - z0)
    a = _lattice(x0, z0, salt)
    b = _lattice(x0 + 1, z0, salt)
    c = _lattice(x0, z0 + 1, salt)
    d = _lattice(x0 + 1, z0 + 1, salt)
    return (a + (b - a) * fx) * (1 - fz) + (c + (d - c) * fx) * fz


def _fbm(x: float, z: float, salt: int, octaves: int = 4) -> float:
    total = 0.0
    norm = 0.0
    amp = 1.0
    freq = 1.0
    for octave in range(octaves):
        total += amp * _value_noise(x * freq, z * freq, salt + octave)
        norm += amp
        amp *= 0.5
        freq *= 2.07
    return total / norm


def _inside(ring: list, px: float, pz: float) -> bool:
    hit = False
    j = len(ring) - 1
    for i in range(len(ring)):
        ax, az = ring[i]
        bx, bz = ring[j]
        if (az > pz) != (bz > pz) and px < (bx - ax) * (pz - az) / (bz - az) + ax:
            hit = not hit
        j = i
    return hit


def _edge_distance(ring: list, px: float, pz: float) -> float:
    best = float("inf")
    j = len(ring) - 1
    for i in range(len(ring)):
        ax, az = ring[j]
        bx, bz = ring[i]
        dx, dz = bx - ax, bz - az
        length2 = dx * dx + dz * dz or 1.0
        t = ((px - ax) * dx + (pz - az) * dz) / length2
        t = max(0.0, min(1.0, t))
        cx, cz = ax + dx * t, az + dz * t
        best = min(best, math.hypot(px - cx, pz - cz))
        j = i
    return best


def build_elevation(map_path: Path) -> dict:
    board = build_board(map_path)
    frame_w, frame_h = board["frame_units"]

    rings = [
        [(px * frame_w, py * frame_h) for px, py in mass["hull"]]
        for mass in board["landmasses"]
    ]

    seeds = []
    for city in board["cities"]:
        terrain = city["terrain"][0] if city["terrain"] else None
        base, rough = TERRAIN_ELEV.get(terrain, TERRAIN_FALLBACK)
        seeds.append((city["x"] * frame_w, city["y"] * frame_h, base, rough))

    heights = []
    depths = []
    peak = 0.0
    for row in range(GRID_H):
        fy = row / (GRID_H - 1)
        pz = fy * frame_h
        for col in range(GRID_W):
            fx = col / (GRID_W - 1)
            px = fx * frame_w

            shelf = 0.0
            for ring in rings:
                if _inside(ring, px, pz):
                    shelf = max(
                        shelf,
                        _smoothstep(min(1.0, _edge_distance(ring, px, pz) / COAST_SHELF)),
                    )
            if shelf <= 0.0:
                # Open water. Record how far out it is, for the colour ramp.
                offshore = min(_edge_distance(ring, px, pz) for ring in rings)
                heights.append(0.0)
                depths.append(min(1.0, offshore / SEA_RANGE))
                continue
            depths.append(0.0)

            wsum = base_sum = rough_sum = 0.0
            for sx, sz, base, rough in seeds:
                d2 = (px - sx) ** 2 + (pz - sz) ** 2
                w = 1.0 / (d2 + IDW_SOFT)
                wsum += w
                base_sum += w * base
                rough_sum += w * rough
            base = base_sum / wsum
            rough = rough_sum / wsum

            # Domain warp. Without it the fractal sits in a fixed lattice and
            # the contours read as a grid of blobs; displacing the lookup by a
            # second, slower fractal makes the same noise meander.
            wx = px + 46.0 * (_fbm(px * NOISE_SCALE * 0.55,
                                   pz * NOISE_SCALE * 0.55, 907) - 0.5)
            wz = pz + 46.0 * (_fbm(px * NOISE_SCALE * 0.55 + 13.7,
                                   pz * NOISE_SCALE * 0.55 - 4.1, 331) - 0.5)

            broad = _fbm(wx * NOISE_SCALE, wz * NOISE_SCALE, 11)
            fine = _fbm(wx * NOISE_SCALE * 3.1, wz * NOISE_SCALE * 3.1, 71)
            ridged = 1.0 - abs(
                2.0 * _fbm(wx * NOISE_SCALE * 1.7, wz * NOISE_SCALE * 1.7, 33) - 1.0
            )

            height = (
                base * (0.5 + 0.75 * broad + 0.55 * ridged * ridged)
                + rough * (fine - 0.45) * 1.9
            )
            height = max(0.0, height) * shelf * VERTICAL_EXAGGERATION
            peak = max(peak, height)
            heights.append(height)

    ceiling = peak or 1.0
    packed = bytes(
        max(0, min(255, int(round(h / ceiling * 255.0)))) for h in heights
    )
    packed_sea = bytes(
        max(0, min(255, int(round(d * 255.0)))) for d in depths
    )

    return {
        "map": map_path.name,
        "width": GRID_W,
        "height": GRID_H,
        "frame_units": [frame_w, frame_h],
        "max_height": round(ceiling, 3),
        "sea_range": SEA_RANGE,
        "data": base64.b64encode(packed).decode("ascii"),
        "sea": base64.b64encode(packed_sea).decode("ascii"),
    }


HEADER = """\
// Atlas board elevation, generated from maps/calib_12.json by
// scripts/build_elevation.py. Do not hand-edit.
//
// One byte per cell over the map's own frame, scaled by max_height into board
// units. NOT survey data: calib_12.json has terrain labels and no elevation at
// all, so which cities stand on high ground is real and the shape of the
// ground between them is this model's invention. The page says so in its
// legend. Nothing in the engine reads this file.
const ATLAS_ELEVATION = """


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    elevation = build_elevation(args.map)
    body = json.dumps(elevation, indent=2, ensure_ascii=False)
    args.out.write_text(HEADER + body + ";\n", encoding="utf-8")

    raw = base64.b64decode(elevation["data"])
    land = sum(1 for b in raw if b > 0)
    print(
        f"{args.out}: {elevation['width']}x{elevation['height']} cells, "
        f"peak {elevation['max_height']} board units, "
        f"{land * 100 // len(raw)}% land"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
