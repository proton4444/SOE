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
  5. a shelf multiply, so everything falls to sea level at the shore;
  6. a normalise, so the tallest ground on any map lands at the same fraction
     of the frame -- a hills map and a mountains map both read as themselves
     rather than one of them reading as flat and the other as absurd.

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

DEFAULT_MAP = REPO_ROOT / "maps" / "starter_map.json"
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

# The shoreline is not the hull.
#
# mapview's landmass is a CONVEX HULL -- for starter_map's mainland, literally
# four points and four straight edges. Drawn as the coast it looks like what it
# is: a survey boundary, not a shore. Nothing in nature is convex.
#
# So the hull stops being the coastline and goes back to being what it always
# was, a confine. The shoreline is now an isoline of the heightfield: the
# distance to the hull is perturbed by fractal noise before the shelf is taken
# from it, and the ground goes on descending past it to a seabed. Where that
# surface crosses sea level IS the coast -- bays, headlands and all -- and it
# is a real intersection rather than a polygon anyone has to draw.
#
# WOBBLE is how far the shore may wander from the hull, in board units.
#
# It was described as bounded on purpose -- "the hull sits ~72 units outside
# the cities it was built around, so a shore that wandered further inland than
# that would start drowning towns". That is not true of `starter_map.json`,
# and nothing was checking it. Measured, hull to town:
#
#     Highfell 23.3   Ashford 34.6   Oldbarrow 45.3
#     Gullhaven 55.5  Sarnvale 46.4  Redport 112.4
#
# So 46 units of inward wobble, plus the 30-unit shelf ramp behind it, reaches
# 76 units inland -- past every town on the board but one. SITE_GUARD below is
# what actually keeps them out of the water now; this number is free to be
# chosen for how the coast looks.
COAST_WOBBLE = 46.0
COAST_NOISE = 1.0 / 210.0

# How close the shelf may come to a town, in board units.
#
# A town stands on its own ground. Without this the shelf decided the height
# of a settlement: it ramps the land to sea level across COAST_SHELF units,
# and where the wobble brought the shore near a town it multiplied that town's
# ground by whatever fraction was left. `starter_map.json` came out with its
# terrain ordering inverted --
#
#     Redport   river plains  raw 45.8  shelf 1.00  ->  45.8
#     Oldbarrow mountains     raw 84.2  shelf 0.11  ->   9.5
#
# -- so the one mountains city on the board stood a third the height of a
# river town, while the page's own legend read "relief interpolated from city
# terrain, high ground is data". The raw field had it right all along; the
# shelf took it away.
#
# The shore may still run between towns. It may not run through one.
SITE_GUARD = 78.0

# Below the waterline. The seabed exists so the coast can be an intersection
# instead of an edge; it is never seen, because the water above it is opaque.
SEA_DEPTH_FRAC = 0.28
SEA_SLOPE = 190.0

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
#
# 2600 is a ~51-unit influence radius, which was survivable while the tallest
# thing on the map was a 56-unit hill. Put a mountains city (base 112) into it
# and the model raises 290 units of ground inside 50 units of radius: a
# flat-topped tower with vertical sides, standing in the middle of the board
# like a cooling stack. 12000 is a ~110-unit radius and high ground spreads
# into a massif with flanks, which is what a mountain is.
IDW_SOFT = 12000.0

# Vertical exaggeration, chosen per map rather than fixed.
#
# It used to be a constant 2.6, tuned on a map whose boldest feature was a
# hill. The constant is the wrong shape of knob: on calib_12 it produced 157
# units of relief and on a map with mountains in it, 368 -- the same setting
# reading as "subtle" on one board and "absurd" on the next. Instead the model
# scales its own output so the tallest ground on ANY map lands at this
# fraction of the frame width. Relief maps have always chosen their vertical
# to suit the sheet; this just says so out loud.
TARGET_RELIEF = 0.17
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


class _Coast:
    """The coastline rings, bucketed so a lookup does not walk all of them.

    `_edge_distance` and `_inside` are both linear in the number of ring
    vertices, and they are called once per grid cell. A connectivity hull has
    four; a traced coastline has thousands. `maps/world.json` carries 5,284
    across two rings, and 256x148 cells over them is roughly 200 million edge
    visits per helper -- `python -m scripts.build_elevation --map
    maps/world.json` took 118 seconds, and it is a documented option.

    Both questions are local. A uniform bucket grid over the frame answers
    them from the handful of edges that could matter: the ray cast reads one
    row of buckets, and the distance search walks outward from the query's own
    bucket and stops as soon as the ring it is about to search is further away
    than the best edge it has found. Same answers, and `starter_map.json`
    regenerates byte-identical.
    """

    def __init__(self, rings: list, frame_w: float, frame_h: float) -> None:
        self.rings = rings
        edges = []
        owner = []
        for r, ring in enumerate(rings):
            for i in range(len(ring)):
                edges.append((ring[i - 1], ring[i]))
                owner.append(r)
        self.edges = edges
        self.owner = owner

        # About one edge per bucket, and never so fine that the grid itself
        # costs more to walk than the edges it holds.
        count = max(1, len(edges))
        self.cell = max(4.0, math.sqrt(frame_w * frame_h / count))
        self.cols = max(1, int(frame_w / self.cell) + 2)
        self.rows = max(1, int(frame_h / self.cell) + 2)
        self.buckets: list[list[int]] = [[] for _ in range(self.cols * self.rows)]
        for n, ((ax, az), (bx, bz)) in enumerate(edges):
            lo_c, hi_c = self._span(min(ax, bx), max(ax, bx), self.cols)
            lo_r, hi_r = self._span(min(az, bz), max(az, bz), self.rows)
            for r in range(lo_r, hi_r + 1):
                row = r * self.cols
                for c in range(lo_c, hi_c + 1):
                    self.buckets[row + c].append(n)

        # Ray casting only ever needs one row of the grid, so those are kept
        # whole: an edge lands in every row its z-span crosses. Each edge
        # carries the ring it came from, because parity has to be counted per
        # ring -- see `inside`.
        self.rows_index: list[list[int]] = [[] for _ in range(self.rows)]
        for n, ((_ax, az), (_bx, bz)) in enumerate(edges):
            lo_r, hi_r = self._span(min(az, bz), max(az, bz), self.rows)
            for r in range(lo_r, hi_r + 1):
                self.rows_index[r].append(n)

    def _span(self, lo: float, hi: float, limit: int) -> tuple[int, int]:
        a = max(0, min(limit - 1, int(lo / self.cell)))
        b = max(0, min(limit - 1, int(hi / self.cell)))
        return a, b

    def inside(self, px: float, pz: float) -> bool:
        """Inside ANY ring -- parity counted per ring, never pooled.

        Pooling it is wrong and not only in the nested case. These rings are
        convex hulls padded outward from their cities, and padding makes
        neighbours overlap: `calib_24.json` has 219 points and `calib_48.json`
        932 that lie inside two hulls at once. One shared parity counter
        cancels them to False, `build_elevation` reads that as a negative
        signed distance, and the board gets ocean cut through land that
        `mapview` draws as the union of those same hulls.
        """
        r = max(0, min(self.rows - 1, int(pz / self.cell)))
        hits = [False] * len(self.rings)
        for n in self.rows_index[r]:
            (ax, az), (bx, bz) = self.edges[n]
            if (az > pz) != (bz > pz) and px < (bx - ax) * (pz - az) / (bz - az) + ax:
                ring = self.owner[n]
                hits[ring] = not hits[ring]
        return any(hits)

    def distance(self, px: float, pz: float) -> float:
        c0 = max(0, min(self.cols - 1, int(px / self.cell)))
        r0 = max(0, min(self.rows - 1, int(pz / self.cell)))
        best = math.inf
        reach = max(self.cols, self.rows)
        for step in range(reach + 1):
            # Everything in the previous rings is closer than this one can be,
            # so once the best edge is inside that radius there is no point
            # looking further out.
            if best <= (step - 1) * self.cell:
                break
            lo_r, hi_r = max(0, r0 - step), min(self.rows - 1, r0 + step)
            lo_c, hi_c = max(0, c0 - step), min(self.cols - 1, c0 + step)
            for r in range(lo_r, hi_r + 1):
                on_r_edge = r in (r0 - step, r0 + step)
                row = r * self.cols
                span = (
                    range(lo_c, hi_c + 1)
                    if on_r_edge
                    else (c for c in (c0 - step, c0 + step) if lo_c <= c <= hi_c)
                )
                for c in span:
                    for n in self.buckets[row + c]:
                        d = _segment_distance(self.edges[n], px, pz)
                        if d < best:
                            best = d
        return best


def _segment_distance(edge: tuple, px: float, pz: float) -> float:
    (ax, az), (bx, bz) = edge
    dx, dz = bx - ax, bz - az
    length2 = dx * dx + dz * dz or 1.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / length2))
    return math.hypot(px - (ax + dx * t), pz - (az + dz * t))


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

    coast_index = _Coast(rings, frame_w, frame_h)

    heights = []
    depths = []
    peak = 0.0
    for row in range(GRID_H):
        fy = row / (GRID_H - 1)
        pz = fy * frame_h
        for col in range(GRID_W):
            fx = col / (GRID_W - 1)
            px = fx * frame_w

            # Signed distance to the nearest hull: positive inside, negative out.
            near = coast_index.distance(px, pz)
            signed = near if coast_index.inside(px, pz) else -near

            # Perturb it, and the shoreline moves with it. Two octaves: a slow
            # one for bays and headlands, a quick one for the ragged detail
            # that stops the slow one reading as a wave.
            # Biased inward (0.68, not 0.5). A hull is the smallest convex
            # shape containing its cities, so a real coast inside one is
            # mostly BITING INTO it -- bays, inlets, a river mouth -- and only
            # occasionally pushing a headland out. A symmetric wobble instead
            # bulges as far out as it cuts in, which puts land past the hull
            # the board is framed around and off the edge of the printed sheet.
            coast = signed + COAST_WOBBLE * (
                (_fbm(px * COAST_NOISE, pz * COAST_NOISE, 401) - 0.68) * 1.5
                + (_fbm(px * COAST_NOISE * 3.9, pz * COAST_NOISE * 3.9, 907) - 0.55) * 0.6
            )

            # A town stands on its own ground: the shelf is not allowed to
            # reach one. This only ever lifts, so the coast keeps its shape
            # everywhere it is not about to run through a settlement.
            if seeds:
                near_city = min(
                    math.hypot(px - sx, pz - sz) for sx, sz, _b, _r in seeds
                )
                if near_city < SITE_GUARD:
                    # Capped at the UNWOBBLED distance, so the guard can only
                    # undo the wobble near a town, never invent land beyond
                    # the hull. Without the cap it did: `world.json`'s hull is
                    # its traced coastline, and 154 cities each pushing the
                    # shore out took the map from 31% land to 51% -- a board
                    # whose coast no longer matched the one the app draws,
                    # which is the disagreement this builder exists to
                    # prevent. Offshore `signed` is negative and the cap makes
                    # this a no-op.
                    lift = COAST_SHELF * (1.0 - near_city / SITE_GUARD)
                    coast = max(coast, min(signed, lift))

            shelf = _smoothstep(min(1.0, max(0.0, coast / COAST_SHELF)))
            # Below the waterline, running out to the seabed floor.
            submerged = max(-1.0, min(0.0, coast / SEA_SLOPE))
            depths.append(min(1.0, max(0.0, -coast / SEA_RANGE)))

            if shelf <= 0.0:
                # Seabed. Recorded, not skipped: the waterline is where this
                # surface crosses sea level, so the surface has to exist on
                # both sides of it.
                heights.append(submerged)
                continue

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
            height = max(0.0, height) * shelf
            peak = max(peak, height)
            heights.append(height + submerged)

    # Normalise the land so its tallest point is TARGET_RELIEF of the frame.
    # Every height scales with it, so the ORDERING the terrain labels set is
    # untouched -- only the amplitude is chosen here.
    ceiling = frame_w * TARGET_RELIEF
    depth = ceiling * SEA_DEPTH_FRAC
    scale = ceiling + depth

    # Land was accumulated in raw units and the seabed in [-1, 0]; put both on
    # the same scale, then lift the whole field so the seabed floor is zero and
    # a byte can carry it. `sea_level` is where the water sits in that field.
    out = []
    for h in heights:
        if h < 0:
            out.append(depth + h * depth)
        else:
            out.append(depth + (h / peak * ceiling if peak > 0 else 0.0))
    packed = bytes(
        max(0, min(255, int(round(h / scale * 255.0)))) for h in out
    )
    packed_sea = bytes(
        max(0, min(255, int(round(d * 255.0)))) for d in depths
    )

    return {
        "map": map_path.name,
        "width": GRID_W,
        "height": GRID_H,
        "frame_units": [frame_w, frame_h],
        # Board units a full byte is worth, where the water sits in that
        # range, and how much of it is land. The renderer subtracts sea_level
        # so its own y = 0 is the waterline.
        "scale": round(scale, 3),
        "sea_level": round(depth, 3),
        "max_height": round(ceiling, 3),
        "sea_range": SEA_RANGE,
        "data": base64.b64encode(packed).decode("ascii"),
        "sea": base64.b64encode(packed_sea).decode("ascii"),
    }


HEADER = """\
// Atlas board elevation, generated from maps/starter_map.json by
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
    # Above the waterline, not merely above zero: every cell carries a value
    # now, because the seabed is part of the field.
    waterline = elevation["sea_level"] / elevation["scale"] * 255
    land = sum(1 for b in raw if b > waterline)
    print(
        f"{args.out}: {elevation['width']}x{elevation['height']} cells, "
        f"peak {elevation['max_height']} board units, "
        f"{land * 100 // len(raw)}% land"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
