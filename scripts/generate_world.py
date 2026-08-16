"""
Generate an original world map from a seed.

This replaces the traced-and-transcribed pipeline (`extract_geography.py` +
`build_world_map.py`), whose inputs were third-party material. Everything here
is synthesised: coastlines from a smoothed random field, towns from Poisson
sampling on land, names from per-region syllable morphology, and a route
network built to be connected and to match the density the engine was tuned
against.

Two properties matter and are tested:

*Determinism.* One seed gives one world, byte for byte. Nothing reads the
clock, the filesystem or the process environment.

*Distributional fidelity.* Town count, population bands, terrain mix, port
share, route qualities and node degrees track the profile the engine's balance
assumes, so a generated world plays like a hand-built one.

Usage:
    python scripts/generate_world.py --seed 1 --out maps/world_seed1.json
    python scripts/generate_world.py --seed 1 --stats
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The field the engine prices travel in. 1300 x 1000 miles on a 13 x 10
# graticule of 100-mile cells, so a grid reference is one cell.
FIELD_WIDTH_MILES = 1300
FIELD_HEIGHT_MILES = 1000
GRID_COLS = 13
GRID_ROWS = 10
ROW_LETTERS = "ABCDEFGHIJ"

# Terrain lattice: one cell per 10 miles.
CELL_MILES = 10
GRID_W = FIELD_WIDTH_MILES // CELL_MILES
GRID_H = FIELD_HEIGHT_MILES // CELL_MILES

DEFAULT_TOWNS = 154
DEFAULT_REGIONS = 15

# Share of towns per population band. Most of the world is villages; the
# handful of great cities are what factions actually fight over.
BAND_WEIGHTS = [("< 1k", 78), ("1k-9k", 50), ("10k-99k", 22), ("100k+", 4)]
BAND_POPULATION = {
    "< 1k": (150, 950),
    "1k-9k": (1_200, 9_500),
    "10k-99k": (12_000, 95_000),
    "100k+": (105_000, 240_000),
}

# Terrain mix, and how habitable each type is. Towns prefer plains; mountains
# and swamp carry a few stubborn settlements.
TERRAIN_WEIGHTS = [
    ("plain", 78), ("forest", 33), ("hills", 21),
    ("mountains", 10), ("desert", 10), ("swamp", 2),
]
# Settlement bias. Towns favour plains, but the floor is high enough that the
# world's terrain mix survives into the towns actually placed on it.
TERRAIN_HABITABILITY = {
    "plain": 1.0, "forest": 0.88, "hills": 0.82,
    "desert": 0.66, "mountains": 0.6, "swamp": 0.55,
}

ROAD_QUALITY_WEIGHTS = [("good", 83), ("fair", 52), ("poor", 28), ("excellent", 13)]

TARGET_LAND_FRACTION = 0.34
MIN_TOWN_SEPARATION_MILES = 28
SEA_ROUTE_SHARE = 0.23      # 54 of 230 routes on the reference world
MAX_SEA_LANE_MILES = 420    # beyond this a crossing is never worth sailing
ROAD_WINDING_FACTOR = 1.15  # roads are longer than the straight line

# Syllable stock. Regions draw disjoint slices of it, so towns in one region
# sound related and towns in different regions do not.
HEADS = [
    "bar", "cal", "dun", "esh", "fen", "gar", "hal", "ith", "jor", "kel",
    "lun", "mor", "nar", "oss", "pel", "quen", "rha", "sel", "tor", "ulm",
    "vas", "wen", "xan", "yr", "zel", "brae", "cor", "drel", "eph", "fal",
]
MIDS = ["", "a", "e", "i", "o", "u", "an", "er", "il", "or", "un", "ath", "eth", "oth"]
TAILS = [
    "burn", "dale", "fell", "ford", "gate", "haven", "hold", "mere", "moor",
    "port", "reach", "ridge", "stead", "thorpe", "vale", "wick", "wold",
    "ath", "en", "is", "on", "ur", "yn",
]
REGION_TAILS = [
    "march", "reach", "vale", "expanse", "coast", "hollow", "waste", "downs",
    "fold", "verge", "basin", "range", "strand", "weald", "hinterland",
]


# ---------------------------------------------------------------------------
# Terrain field
# ---------------------------------------------------------------------------

def _smooth(field: list[list[float]], passes: int) -> list[list[float]]:
    """Box-blur the lattice, clamping at the edges."""
    for _ in range(passes):
        out = [[0.0] * GRID_W for _ in range(GRID_H)]
        for y in range(GRID_H):
            for x in range(GRID_W):
                total = 0.0
                count = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < GRID_H and 0 <= nx < GRID_W:
                            total += field[ny][nx]
                            count += 1
                out[y][x] = total / count
        field = out
    return field


# ---------------------------------------------------------------------------
# Relief: how the landmass gets its shape
# ---------------------------------------------------------------------------
#
# `noise` is the original and stays the default, because maps/world.json was
# generated with it and games in progress resolve their town ids against it.
#
# It has a flaw worth naming. Box-blurring white noise gives you noise with a
# shorter spectrum, not shape: nothing survives that is larger than the kernel.
# Thresholding that produces a frame-filling slab with a fractal edge and
# dozens of one-cell lakes, and no seed escapes it -- over 200 seeds the main
# outline never gets more compact than 0.27 (a disc is 1.0) and never carries
# fewer than 21 pinholes. The square falloff, `max(|fx|, |fy|)`, is what makes
# the slab rectangular: at the margins you are looking at the mask, not the
# land.
#
# `fbm` fixes both. Value noise on coarse lattices, interpolated smoothly and
# summed with falling amplitude, so the lowest octave is the continent and the
# highest is the coastline; a radial falloff whose radius is modulated by
# low-frequency noise, so the outline is a silhouette rather than an ellipse;
# and a cleanup pass that fills pinhole lakes and drops specks, so the lakes
# that remain are inland seas somebody meant.

RELIEF_MODES = ("noise", "fbm")
DEFAULT_RELIEF = "noise"

#: fbm relief, fixed. These are the settings the chosen world was found with,
#: so changing them changes every fbm map, not just the next one.
FBM_OCTAVES = (3, 6, 12, 24)     # lattice columns per octave; 3 is the continent
FBM_GAIN = 0.55                  # amplitude falloff per octave
FBM_LOBES = 7                    # harmonics in the silhouette modulation
FBM_WARP = 0.34                  # how far the silhouette departs from a circle
FBM_INNER = 0.30                 # radius held at full strength before the fade
FBM_POWER = 1.0
FBM_MIN_LAKE = 6                 # cells; smaller enclosed water is a pinhole
FBM_MIN_ISLAND = 4               # cells; smaller land is a speck

#: Land cells per terrain region. The original seeds one region per 14 cells,
#: which is a 37-mile patch: correct as data, unreadable as a map, and it
#: renders as confetti rather than as country. At 70 the regions are large
#: enough to be somewhere -- a forest belt, a mountain range -- while the
#: terrain mix over the whole world is unchanged, because the seeds are still
#: drawn from the same weighted pool.
TERRAIN_CELLS_PER_REGION = {"noise": 14, "fbm": 70}

#: How a route is judged to be a sea crossing.
#:
#: `touches` is the original and the default: sample the straight line and
#: call it a crossing when more than a quarter of the samples are water. It
#: cannot tell a crossing from a route that clips one bay, so on the chosen
#: world 16 of its 30 "sea lanes" joined towns on the same landmass, and the
#: map drew them as ships sailing over mountains.
#:
#: `detour` asks the question that matters: can you walk it, and is walking
#: sane? A route is a crossing when there is no land path at all, or when the
#: shortest one is more than SEA_DETOUR_FACTOR times the straight line -- a
#: gulf you would rather sail across than march around.
SEA_RULES = ("touches", "detour")
DEFAULT_SEA_RULE = "touches"
SEA_DETOUR_FACTOR = 2.2


def _smootherstep(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def _value_noise(rng: random.Random, cols: int, rows: int):
    """One octave: random values on a coarse lattice, smoothly interpolated."""
    grid = [[rng.random() for _ in range(cols + 1)] for _ in range(rows + 1)]

    def at(fx: float, fy: float) -> float:
        gx, gy = fx * cols, fy * rows
        x0, y0 = int(gx), int(gy)
        tx, ty = _smootherstep(gx - x0), _smootherstep(gy - y0)
        x1, y1 = min(x0 + 1, cols), min(y0 + 1, rows)
        top = grid[y0][x0] * (1 - tx) + grid[y0][x1] * tx
        bottom = grid[y1][x0] * (1 - tx) + grid[y1][x1] * tx
        return top * (1 - ty) + bottom * ty

    return at


def _fbm_field(rng: random.Random) -> list[list[float]]:
    layers = []
    amplitude = 1.0
    total = 0.0
    for base in FBM_OCTAVES:
        rows = max(2, round(base * GRID_H / GRID_W))
        layers.append((amplitude, _value_noise(rng, base, rows)))
        total += amplitude
        amplitude *= FBM_GAIN

    field = [[0.0] * GRID_W for _ in range(GRID_H)]
    for y in range(GRID_H):
        for x in range(GRID_W):
            fx, fy = (x + 0.5) / GRID_W, (y + 0.5) / GRID_H
            field[y][x] = sum(a * f(fx, fy) for a, f in layers) / total
    return field


def _silhouette(rng: random.Random):
    """Low-frequency radial modulation: the continent's outline, not a circle."""
    amps = [rng.random() * 2 - 1 for _ in range(FBM_LOBES)]
    phases = [rng.random() * math.tau for _ in range(FBM_LOBES)]

    def at(angle: float) -> float:
        return sum(
            a * math.cos(k * angle + p) / k
            for k, (a, p) in enumerate(zip(amps, phases), start=1)
        )

    return at


def _apply_falloff(field: list[list[float]], rng: random.Random) -> list[list[float]]:
    warp = _silhouette(rng)
    for y in range(GRID_H):
        for x in range(GRID_W):
            fx = (x + 0.5) / GRID_W * 2 - 1
            fy = (y + 0.5) / GRID_H * 2 - 1
            edge = math.hypot(fx, fy) / math.sqrt(2) * 1.28
            edge *= 1.0 + FBM_WARP * warp(math.atan2(fy, fx))
            k = max(0.0, min(1.0, 1.0 - max(0.0, edge - FBM_INNER) / (1 - FBM_INNER)))
            field[y][x] *= _smootherstep(k) ** FBM_POWER
    return field


def _components(mask: list[list[bool]], want: bool) -> list[list[tuple[int, int]]]:
    """Four-connected groups of cells equal to `want`."""
    seen = [[False] * GRID_W for _ in range(GRID_H)]
    groups = []
    for sy in range(GRID_H):
        for sx in range(GRID_W):
            if seen[sy][sx] or mask[sy][sx] != want:
                continue
            stack = [(sx, sy)]
            seen[sy][sx] = True
            group = []
            while stack:
                x, y = stack.pop()
                group.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if (
                        0 <= nx < GRID_W and 0 <= ny < GRID_H
                        and not seen[ny][nx] and mask[ny][nx] == want
                    ):
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            groups.append(group)
    return groups


def _clean(mask: list[list[bool]]) -> list[list[bool]]:
    """Fill pinhole lakes and drop specks.

    Water that reaches the frame is the sea and is never filled, however
    narrow the channel it arrives through.
    """
    for group in _components(mask, False):
        if any(x in (0, GRID_W - 1) or y in (0, GRID_H - 1) for x, y in group):
            continue
        if len(group) < FBM_MIN_LAKE:
            for x, y in group:
                mask[y][x] = True
    for group in _components(mask, True):
        if len(group) < FBM_MIN_ISLAND:
            for x, y in group:
                mask[y][x] = False
    return mask


def _landmass_fbm(rng: random.Random) -> list[list[bool]]:
    field = _apply_falloff(_fbm_field(rng), rng)
    values = sorted(v for row in field for v in row)
    cutoff = values[int(len(values) * (1 - TARGET_LAND_FRACTION))]
    mask = [[field[y][x] > cutoff for x in range(GRID_W)] for y in range(GRID_H)]
    return _clean(mask)


def build_landmass(
    rng: random.Random, relief: str = DEFAULT_RELIEF
) -> list[list[bool]]:
    """A smoothed random field, thresholded so the target fraction is land.

    An edge falloff keeps the continent off the frame, so coastal towns are
    genuinely coastal rather than clipped by the map border.

    `relief` picks how the shape is arrived at; see RELIEF_MODES above. The
    default is the original, and its output must not move.
    """
    if relief not in RELIEF_MODES:
        raise ValueError(f"unknown relief {relief!r}, expected one of {RELIEF_MODES}")
    if relief == "fbm":
        return _landmass_fbm(rng)

    field = [[rng.random() for _ in range(GRID_W)] for _ in range(GRID_H)]
    field = _smooth(field, passes=3)

    for y in range(GRID_H):
        for x in range(GRID_W):
            fx = (x + 0.5) / GRID_W * 2 - 1
            fy = (y + 0.5) / GRID_H * 2 - 1
            edge = max(abs(fx), abs(fy))
            # Full strength inland, fading to nothing at the frame.
            field[y][x] *= max(0.0, 1.0 - max(0.0, edge - 0.55) / 0.45)

    values = sorted(v for row in field for v in row)
    cutoff = values[int(len(values) * (1 - TARGET_LAND_FRACTION))]
    land = [[field[y][x] > cutoff for x in range(GRID_W)] for y in range(GRID_H)]

    # Drop specks: a one-cell island carries no town and only confuses routing.
    for y in range(GRID_H):
        for x in range(GRID_W):
            if not land[y][x]:
                continue
            neighbours = sum(
                land[y + dy][x + dx]
                for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dy or dx) and 0 <= y + dy < GRID_H and 0 <= x + dx < GRID_W
            )
            if neighbours == 0:
                land[y][x] = False
    return land


def build_terrain(
    rng: random.Random,
    land: list[list[bool]],
    relief: str = DEFAULT_RELIEF,
) -> list[list[str | None]]:
    """Grow terrain regions from seeds so like sits with like."""
    kinds = [k for k, _ in TERRAIN_WEIGHTS]
    weights = [w for _, w in TERRAIN_WEIGHTS]
    land_cells = [(x, y) for y in range(GRID_H) for x in range(GRID_W) if land[y][x]]

    per_region = TERRAIN_CELLS_PER_REGION.get(relief, 14)
    seed_count = max(24, len(land_cells) // per_region)
    # Draw kinds proportionally rather than independently, so a rare terrain
    # is not lost to sampling noise across a handful of seeds.
    pool: list[str] = []
    total = sum(weights)
    for kind, weight in zip(kinds, weights):
        pool += [kind] * max(1, round(seed_count * weight / total))
    rng.shuffle(pool)
    seeds = []
    for kind in pool[:seed_count]:
        x, y = rng.choice(land_cells)
        seeds.append((x, y, kind))

    terrain: list[list[str | None]] = [[None] * GRID_W for _ in range(GRID_H)]
    for x, y in land_cells:
        best, best_d = "plain", None
        for sx, sy, kind in seeds:
            d = (sx - x) ** 2 + (sy - y) ** 2
            if best_d is None or d < best_d:
                best, best_d = kind, d
        terrain[y][x] = best
    return terrain


def is_coastal(land: list[list[bool]], cx: int, cy: int) -> bool:
    """True when a land cell touches water within one cell."""
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ny, nx = cy + dy, cx + dx
            if not (0 <= ny < GRID_H and 0 <= nx < GRID_W) or not land[ny][nx]:
                return True
    return False


# ---------------------------------------------------------------------------
# Towns
# ---------------------------------------------------------------------------

def place_towns(rng: random.Random, land, terrain, count: int) -> list[dict]:
    """Poisson-ish sampling on land, biased toward habitable terrain."""
    candidates = [
        (x, y) for y in range(GRID_H) for x in range(GRID_W)
        if land[y][x]
    ]
    rng.shuffle(candidates)

    placed: list[dict] = []
    min_sq = MIN_TOWN_SEPARATION_MILES ** 2
    # Several relaxation rounds: take the easy spacing first, then loosen.
    for relax in (1.0, 0.75, 0.55, 0.4):
        for cx, cy in candidates:
            if len(placed) >= count:
                break
            kind = terrain[cy][cx] or "plain"
            if rng.random() > TERRAIN_HABITABILITY[kind] * relax + (1 - relax):
                continue
            x_miles = round((cx + rng.random()) * CELL_MILES, 1)
            y_miles = round((cy + rng.random()) * CELL_MILES, 1)
            if any((x_miles - p["x_miles"]) ** 2 + (y_miles - p["y_miles"]) ** 2
                   < min_sq * relax for p in placed):
                continue
            placed.append({
                "cell": (cx, cy),
                "terrain": kind,
                "x_miles": x_miles,
                "y_miles": y_miles,
                "coastal": is_coastal(land, cx, cy),
            })
        if len(placed) >= count:
            break
    return placed[:count]


def assign_regions(rng: random.Random, towns: list[dict], k: int) -> None:
    """Lloyd relaxation: towns join the nearest of k drifting centres."""
    centres = [(t["x_miles"], t["y_miles"]) for t in rng.sample(towns, k)]
    for _ in range(12):
        buckets: list[list[dict]] = [[] for _ in range(k)]
        for t in towns:
            best, best_d = 0, None
            for i, (cx, cy) in enumerate(centres):
                d = (t["x_miles"] - cx) ** 2 + (t["y_miles"] - cy) ** 2
                if best_d is None or d < best_d:
                    best, best_d = i, d
            buckets[best].append(t)
        for i, bucket in enumerate(buckets):
            if bucket:
                centres[i] = (
                    sum(t["x_miles"] for t in bucket) / len(bucket),
                    sum(t["y_miles"] for t in bucket) / len(bucket),
                )
    for i, bucket in enumerate(buckets):
        for t in bucket:
            t["region_index"] = i


def name_maker(rng: random.Random, region_count: int):
    """One naming morphology per region, drawn from disjoint syllable slices."""
    heads = HEADS[:]
    tails = TAILS[:]
    rng.shuffle(heads)
    rng.shuffle(tails)
    per_head = max(3, len(heads) // region_count)
    per_tail = max(3, len(tails) // region_count)

    palettes = []
    for i in range(region_count):
        palettes.append((
            heads[(i * per_head) % len(heads):][:per_head] or heads[:per_head],
            tails[(i * per_tail) % len(tails):][:per_tail] or tails[:per_tail],
        ))

    used: set[str] = set()

    def make(region_index: int) -> str:
        head_pool, tail_pool = palettes[region_index % region_count]
        for _ in range(200):
            name = (rng.choice(head_pool) + rng.choice(MIDS)
                    + rng.choice(tail_pool)).capitalize()
            if name.lower() not in used and len(name) >= 5:
                used.add(name.lower())
                return name
        name = f"Holding{len(used) + 1}"
        used.add(name.lower())
        return name

    return make


def grid_ref(x_miles: float, y_miles: float) -> str:
    col = min(GRID_COLS, int(x_miles / (FIELD_WIDTH_MILES / GRID_COLS)) + 1)
    row = min(GRID_ROWS - 1, int(y_miles / (FIELD_HEIGHT_MILES / GRID_ROWS)))
    return f"{ROW_LETTERS[row]}{col}"


def finish_towns(rng: random.Random, towns: list[dict], region_count: int) -> list[dict]:
    make_name = name_maker(rng, region_count)
    region_names = {}
    for i in range(region_count):
        region_names[i] = f"{make_name(i)} {REGION_TAILS[i % len(REGION_TAILS)]}"

    # Bands go to the best-connected, most habitable sites first, so the great
    # cities land on plains and coasts rather than on a swamp in the corner.
    bands: list[str] = []
    for band, share in BAND_WEIGHTS:
        bands += [band] * share
    bands = bands[:len(towns)]
    while len(bands) < len(towns):
        bands.append("< 1k")

    ranked = sorted(
        towns,
        key=lambda t: (TERRAIN_HABITABILITY[t["terrain"]] + (0.2 if t["coastal"] else 0)),
        reverse=True,
    )
    band_order = sorted(bands, key=lambda b: [x for x, _ in BAND_WEIGHTS].index(b))
    for town, band in zip(ranked, reversed(band_order)):
        town["population_band"] = band

    out = []
    for town in towns:
        band = town["population_band"]
        low, high = BAND_POPULATION[band]
        name = make_name(town["region_index"])
        is_ruin = rng.random() < 0.13
        out.append({
            "id": name.lower().replace(" ", "_"),
            "name": name,
            "population_band": band,
            "population": 0 if is_ruin else rng.randint(low, high),
            "terrain": [town["terrain"]],
            "is_port": bool(town["coastal"]),
            "is_magic_free": rng.random() < 0.085,
            "is_ruin": is_ruin,
            "grid_ref": grid_ref(town["x_miles"], town["y_miles"]),
            "x": round(town["x_miles"] / FIELD_WIDTH_MILES, 4),
            "y": round(town["y_miles"] / FIELD_HEIGHT_MILES, 4),
            "x_miles": town["x_miles"],
            "y_miles": town["y_miles"],
            "region": region_names[town["region_index"]],
        })
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _distance(a: dict, b: dict) -> float:
    return math.hypot(a["x_miles"] - b["x_miles"], a["y_miles"] - b["y_miles"])


def _cell_of_town(town: dict) -> tuple[int, int]:
    return (
        min(GRID_W - 1, max(0, int(town["x_miles"] / CELL_MILES))),
        min(GRID_H - 1, max(0, int(town["y_miles"] / CELL_MILES))),
    )


def _nearest_land(land, cx: int, cy: int) -> tuple[int, int] | None:
    """The town's own cell, or the closest land to it within a few cells."""
    if land[cy][cx]:
        return cx, cy
    for radius in (1, 2, 3):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < GRID_W and 0 <= ny < GRID_H and land[ny][nx]:
                    return nx, ny
    return None


def _land_distances(land, start: tuple[int, int]) -> dict[tuple[int, int], float]:
    """Shortest overland distance in miles from one cell to every reachable one.

    Eight-connected with true step costs, so a diagonal is not priced as a
    detour through two orthogonal moves.
    """
    import heapq

    best: dict[tuple[int, int], float] = {start: 0.0}
    queue = [(0.0, start)]
    diagonal = math.sqrt(2) * CELL_MILES
    while queue:
        cost, (x, y) = heapq.heappop(queue)
        if cost > best.get((x, y), math.inf):
            continue
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < GRID_W and 0 <= ny < GRID_H) or not land[ny][nx]:
                    continue
                step = diagonal if dx and dy else CELL_MILES
                if cost + step < best.get((nx, ny), math.inf):
                    best[(nx, ny)] = cost + step
                    heapq.heappush(queue, (cost + step, (nx, ny)))
    return best


def build_routes(
    rng: random.Random,
    cities: list[dict],
    land,
    sea_rule: str = DEFAULT_SEA_RULE,
) -> list[dict]:
    """Nearest-neighbour candidates, pruned, then forced into one component.

    A land route needs land under it; anything crossing open water is a sea
    lane, and sea lanes need a port at both ends.

    What counts as "crossing open water" is `sea_rule`; see SEA_RULES.
    """
    if sea_rule not in SEA_RULES:
        raise ValueError(f"unknown sea rule {sea_rule!r}, expected one of {SEA_RULES}")

    land_reach: dict[tuple[int, int], dict[tuple[int, int], float]] = {}

    def overland_miles(a: dict, b: dict) -> float:
        """Shortest walk from a to b, or infinity when there is no walk."""
        start = _nearest_land(land, *_cell_of_town(a))
        end = _nearest_land(land, *_cell_of_town(b))
        if start is None or end is None:
            return math.inf
        if start not in land_reach:
            land_reach[start] = _land_distances(land, start)
        return land_reach[start].get(end, math.inf)

    def crosses_water(a: dict, b: dict) -> bool:
        if sea_rule == "detour":
            # A route is a crossing when walking is impossible, or so much
            # longer than the crossing that nobody would walk it. Sampling the
            # straight line instead calls a route that clips one bay a sea
            # lane -- on the chosen world that was 16 of 30 "lanes", drawn as
            # ships sailing over mountains.
            walk = overland_miles(a, b)
            if walk == math.inf:
                return True
            return walk > _distance(a, b) * SEA_DETOUR_FACTOR

        steps = max(2, int(_distance(a, b) / CELL_MILES))
        water = 0
        for i in range(steps + 1):
            t = i / steps
            x = a["x_miles"] + (b["x_miles"] - a["x_miles"]) * t
            y = a["y_miles"] + (b["y_miles"] - a["y_miles"]) * t
            cx = min(GRID_W - 1, max(0, int(x / CELL_MILES)))
            cy = min(GRID_H - 1, max(0, int(y / CELL_MILES)))
            if not land[cy][cx]:
                water += 1
        return water > steps * 0.25

    edges: dict[tuple[int, int], dict] = {}

    def consider(i: int, j: int) -> None:
        key = (min(i, j), max(i, j))
        if key in edges:
            return
        a, b = cities[i], cities[j]
        miles = _distance(a, b)
        sea = crosses_water(a, b)
        if sea and not (a["is_port"] and b["is_port"]):
            return
        edges[key] = {
            "i": i, "j": j, "sea": sea,
            "miles": miles if sea else miles * ROAD_WINDING_FACTOR,
        }

    order = sorted(range(len(cities)), key=lambda i: cities[i]["x_miles"])
    for i in order:
        neighbours = sorted(
            (j for j in range(len(cities)) if j != i),
            key=lambda j: _distance(cities[i], cities[j]),
        )[:6]
        for j in neighbours[:rng.randint(1, 3)]:
            consider(i, j)

    # Union-find: every town must be reachable, or a faction can be marooned.
    parent = list(range(len(cities)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[rb] = ra
        return True

    for e in sorted(edges.values(), key=lambda e: e["miles"]):
        union(e["i"], e["j"])

    while len({find(i) for i in range(len(cities))}) > 1:
        best = None
        for i in range(len(cities)):
            for j in range(i + 1, len(cities)):
                if find(i) == find(j):
                    continue
                d = _distance(cities[i], cities[j])
                if best is None or d < best[0]:
                    best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        a, b = cities[i], cities[j]
        sea = crosses_water(a, b)
        if sea:
            a["is_port"] = b["is_port"] = True
        edges[(min(i, j), max(i, j))] = {
            "i": i, "j": j, "sea": sea,
            "miles": _distance(a, b) * (1.0 if sea else ROAD_WINDING_FACTOR),
        }
        union(i, j)

    # Sea lanes are not a by-product of nearest-neighbour search: coastal
    # towns are usually nearer some inland neighbour than any port across the
    # water. Add them deliberately, shortest first, until the network carries
    # the share of sea traffic the engine's balance assumes.
    ports = [i for i, c in enumerate(cities) if c["is_port"]]
    target_sea = int(len(edges) * SEA_ROUTE_SHARE / (1 - SEA_ROUTE_SHARE))
    have_sea = sum(1 for e in edges.values() if e["sea"])
    candidates = []
    for a_i in range(len(ports)):
        for b_i in range(a_i + 1, len(ports)):
            i, j = ports[a_i], ports[b_i]
            if (min(i, j), max(i, j)) in edges:
                continue
            if not crosses_water(cities[i], cities[j]):
                continue
            miles = _distance(cities[i], cities[j])
            # A lane longer than this is weeks of sailing and never worth
            # taking; it would only inflate the route count.
            if miles > MAX_SEA_LANE_MILES:
                continue
            candidates.append((miles, i, j))
    candidates.sort()
    lane_count: dict[int, int] = {}
    for miles, i, j in candidates:
        if have_sea >= target_sea:
            break
        # Spread the lanes around rather than hanging them all off one harbour.
        if lane_count.get(i, 0) >= 3 or lane_count.get(j, 0) >= 3:
            continue
        edges[(min(i, j), max(i, j))] = {"i": i, "j": j, "sea": True, "miles": miles}
        lane_count[i] = lane_count.get(i, 0) + 1
        lane_count[j] = lane_count.get(j, 0) + 1
        have_sea += 1

    kinds = [k for k, _ in ROAD_QUALITY_WEIGHTS]
    weights = [w for _, w in ROAD_QUALITY_WEIGHTS]
    band_rank = {b: i for i, (b, _) in enumerate(BAND_WEIGHTS)}

    roads = []
    for e in sorted(edges.values(), key=lambda e: (e["i"], e["j"])):
        a, b = cities[e["i"]], cities[e["j"]]
        if e["sea"]:
            quality = "sea"
        else:
            # Traffic between big towns keeps a road in better repair.
            importance = band_rank[a["population_band"]] + band_rank[b["population_band"]]
            pool = kinds if importance < 3 else ["fair", "poor", "good", "excellent"]
            quality = rng.choices(pool, weights=weights, k=1)[0]
        roads.append({
            "id": f"{a['id']}__{b['id']}__{quality}",
            "from": a["id"],
            "to": b["id"],
            "quality": quality,
            "distance_miles": max(12, int(round(e["miles"]))),
            "bidirectional": True,
        })
    return roads


# ---------------------------------------------------------------------------

def generate(seed: int, towns: int = DEFAULT_TOWNS,
             regions: int = DEFAULT_REGIONS,
             relief: str = DEFAULT_RELIEF,
             sea_rule: str = DEFAULT_SEA_RULE) -> dict:
    rng = random.Random(seed)
    land = build_landmass(rng, relief)
    terrain = build_terrain(rng, land, relief)
    raw = place_towns(rng, land, terrain, towns)
    assign_regions(rng, raw, regions)
    cities = finish_towns(rng, raw, regions)
    roads = build_routes(rng, cities, land, sea_rule)
    return {"cities": cities, "roads": roads}


def summarise(world: dict) -> str:
    import collections
    cities, roads = world["cities"], world["roads"]
    degree: collections.Counter = collections.Counter()
    for r in roads:
        degree[r["from"]] += 1
        degree[r["to"]] += 1
    lines = [
        f"towns: {len(cities)}   routes: {len(roads)}",
        f"bands: {dict(collections.Counter(c['population_band'] for c in cities))}",
        f"terrain: {dict(collections.Counter(t for c in cities for t in c['terrain']))}",
        f"quality: {dict(collections.Counter(r['quality'] for r in roads))}",
        f"ports: {sum(c['is_port'] for c in cities)}   "
        f"magic-free: {sum(c['is_magic_free'] for c in cities)}   "
        f"ruins: {sum(c['is_ruin'] for c in cities)}",
        f"regions: {len({c['region'] for c in cities})}   "
        f"unconnected towns: {len(cities) - len(degree)}",
        f"route miles: {min(r['distance_miles'] for r in roads)}"
        f"-{max(r['distance_miles'] for r in roads)}",
        f"sample: {', '.join(c['name'] for c in cities[:8])}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--towns", type=int, default=DEFAULT_TOWNS)
    ap.add_argument("--regions", type=int, default=DEFAULT_REGIONS)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--stats", action="store_true", help="print a profile only")
    ap.add_argument(
        "--relief", choices=RELIEF_MODES, default=DEFAULT_RELIEF,
        help="how the landmass is shaped; 'noise' is the original and the default",
    )
    ap.add_argument(
        "--sea-rule", choices=SEA_RULES, default=DEFAULT_SEA_RULE,
        help="what counts as a sea crossing; 'touches' is the original and the default",
    )
    args = ap.parse_args()

    world = generate(args.seed, args.towns, args.regions, args.relief, args.sea_rule)
    if args.stats or args.out is None:
        print(summarise(world))
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(world, indent=2), encoding="utf-8")
    print(f"wrote {args.out}  ({len(world['cities'])} towns, "
          f"{len(world['roads'])} routes)")


if __name__ == "__main__":
    main()
