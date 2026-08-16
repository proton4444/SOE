"""Emit the coastline and terrain sidecar for a generated world.

`generate_world.py` builds a landmass, grows terrain regions on it, and then
samples towns from it -- and throws the first two away. `world.json` keeps the
towns and the roads; the continent they stand on exists only for the length of
one function call. So the engine has always known where the coast is and has
never been able to say.

This recovers it. Same seed, same two calls in the same order, so the land
under the towns is the land the towns were placed on -- not a plausible
coastline drawn around them afterwards:

    python -m scripts.generate_geography --seed 1 --map maps/world.json \\
        --out maps/world_geography.json

The output is the schema `webapp/mapview.py` already reads and the retired
`extract_geography.py` used to produce, so the sidecar drops into the existing
consumers unchanged: `units`, `field_miles`, `grid`, `coastlines`, `rivers`,
`terrain`.

Nothing here is authored. The only thing this file decides that the generator
did not is how to draw the boundary of a 10-mile lattice, which is a question
about rendering a known field, not about where the land is:

  - the boundary is traced as the cell edges between land and water, which is
    exact;
  - simplified, then rounded with two Chaikin passes, because a staircase at
    10-mile steps is an artefact of the lattice and not a claim about the
    shore. Both stay inside half a cell of the traced edge, and `--raw` turns
    them off to show the lattice as it is.

`--map` is not decoration and not optional in practice. It checks every town
against the field: on land, terrain label matching its cell, and a port
wherever that cell touches water. A map that fails is a map that was not
generated on this seed, and the sidecar is refused rather than written,
because a coastline drawn around towns that never stood on it is precisely
the invented geography this project does not ship. When the map is a whole
generated world it is checked far harder than that -- regenerated from the
seed and compared outright.

The port check is asymmetric but not blind. A coastal cell must be a port. An
inland one may be, because `build_routes` promotes both ends of a
water-crossing link -- but it records that link as a route of quality `sea`,
so the promotion is checkable: an inland port with no sea route is a
mismatch, not a generator quirk.

Rivers are emitted empty. The generator does not model them; an empty list
says so, and a drawn one would be the invention.

Exit code 0 = written (or verified), 1 = refused.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import generate_world as gw  # noqa: E402
from scripts.generate_world import (  # noqa: E402
    CELL_MILES,
    FIELD_HEIGHT_MILES,
    FIELD_WIDTH_MILES,
    GRID_COLS,
    GRID_H,
    GRID_ROWS,
    GRID_W,
    TERRAIN_WEIGHTS,
    build_landmass,
    build_terrain,
    is_coastal,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Cell-units. A traced edge is simplified to this tolerance before smoothing:
#: below a third of a cell the simplification cannot move the shore anywhere
#: the lattice did not already allow.
SIMPLIFY_TOLERANCE = 0.34

#: Chaikin passes. Two rounds cut each staircase corner twice, which reads as
#: a shore; more starts eroding capes the field really does have.
SMOOTH_PASSES = 2

#: Cells. Below this a component is lattice noise, not an island worth a
#: polygon -- the same call `extract_geography.py` made with `min_area_px`.
MIN_COMPONENT_CELLS = 2

TERRAIN_KINDS = [kind for kind, _ in TERRAIN_WEIGHTS]


# ---------------------------------------------------------------------------
# tracing
# ---------------------------------------------------------------------------


def trace_mask(mask: list[list[bool]]) -> list[list[tuple[float, float]]]:
    """Closed loops around the true cells of a lattice, in cell coordinates.

    Every edge of a true cell whose neighbour is false (or off the lattice) is
    a boundary edge. Emitting them with a fixed orientation -- so the loop is
    always walked the same way round the cell -- makes the stitch unambiguous
    where two cells touch only at a diagonal, which an undirected edge set
    cannot resolve.
    """
    edges: dict[tuple[float, float], list[tuple[float, float]]] = {}

    def add(start: tuple[float, float], end: tuple[float, float]) -> None:
        edges.setdefault(start, []).append(end)

    for y in range(GRID_H):
        for x in range(GRID_W):
            if not mask[y][x]:
                continue
            north = y > 0 and mask[y - 1][x]
            south = y < GRID_H - 1 and mask[y + 1][x]
            west = x > 0 and mask[y][x - 1]
            east = x < GRID_W - 1 and mask[y][x + 1]
            if not north:
                add((x + 1, y), (x, y))
            if not west:
                add((x, y), (x, y + 1))
            if not south:
                add((x, y + 1), (x + 1, y + 1))
            if not east:
                add((x + 1, y + 1), (x + 1, y))

    loops: list[list[tuple[float, float]]] = []
    for start in sorted(edges):
        while edges.get(start):
            loop = [start]
            point = start
            while True:
                following = edges.get(point)
                if not following:
                    break
                nxt = following.pop()
                if not following:
                    del edges[point]
                point = nxt
                if point == start:
                    break
                loop.append(point)
            if len(loop) >= 4:
                loops.append(loop)
    return loops


def signed_area(loop: list[tuple[float, float]]) -> float:
    """Shoelace area with sign, which is what says shore from lakeshore.

    `trace_mask` walks every cell's boundary the same way round, so an outer
    boundary and the boundary of an enclosed hole come out wound in opposite
    directions. Under that convention an outline of land is negative and a
    ring of water inside it is positive, and the two sum to the land area:
    seed 1 traces to exactly -4420, its 4420 land cells.
    """
    total = 0.0
    for i, (x1, y1) in enumerate(loop):
        x2, y2 = loop[(i + 1) % len(loop)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def polygon_area(loop: list[tuple[float, float]]) -> float:
    """Shoelace area, unsigned."""
    return abs(signed_area(loop))


def _segment_distance(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _rdp(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker over an open run of points."""
    if len(points) < 3:
        return points
    first, last = points[0], points[-1]
    worst, index = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _segment_distance(points[i], first, last)
        if d > worst:
            worst, index = d, i
    if worst <= tolerance:
        return [first, last]
    return _rdp(points[: index + 1], tolerance)[:-1] + _rdp(points[index:], tolerance)


def simplify_open(
    path: list[tuple[float, float]], tolerance: float
) -> list[tuple[float, float]]:
    return _rdp(path, tolerance) if len(path) > 2 else path


def smooth_open(
    path: list[tuple[float, float]], passes: int
) -> list[tuple[float, float]]:
    """Chaikin on an open run: the two ends stay put, the corners round off.

    The closed-loop version wraps, which on a sea lane joins its destination
    back to its origin and rounds the join -- a ship sailing in a circle.
    """
    points = path
    for _ in range(passes):
        if len(points) < 3:
            break
        out = [points[0]]
        for i in range(len(points) - 1):
            (x1, y1), (x2, y2) = points[i], points[i + 1]
            out.append((x1 * 0.75 + x2 * 0.25, y1 * 0.75 + y2 * 0.25))
            out.append((x1 * 0.25 + x2 * 0.75, y1 * 0.25 + y2 * 0.75))
        out.append(points[-1])
        points = out
    return points


def simplify(
    loop: list[tuple[float, float]],
    tolerance: float,
    pinned: frozenset[tuple[float, float]] = frozenset(),
) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker over a closed loop, keeping it closed.

    A pinned vertex is a corner of a cell some town stands in, and dropping it
    moves the shore past the town just as surely as smoothing it would, so the
    loop is cut at those vertices and each run simplified between them.
    """
    if len(loop) < 4 or tolerance <= 0:
        return loop

    def rdp(points):
        if len(points) < 3:
            return points
        first, last = points[0], points[-1]
        worst, index = 0.0, 0
        for i in range(1, len(points) - 1):
            d = _segment_distance(points[i], first, last)
            if d > worst:
                worst, index = d, i
        if worst <= tolerance:
            return [first, last]
        return rdp(points[: index + 1])[:-1] + rdp(points[index:])

    anchors = [i for i, point in enumerate(loop) if point in pinned]
    if anchors:
        # Simplify each run between consecutive pinned vertices, so every one
        # of them survives and the shore between them still relaxes.
        out: list[tuple[float, float]] = []
        for start, end in zip(anchors, anchors[1:] + [anchors[0] + len(loop)]):
            run = [loop[i % len(loop)] for i in range(start, end + 1)]
            out += rdp(run)[:-1]
        return out if len(out) > 3 else loop

    # Split at the extreme point so the two ends are not both anchored at an
    # arbitrary vertex, which on a closed ring cuts a corner that is really
    # there.
    pivot = max(range(len(loop)), key=lambda i: (loop[i][1], loop[i][0]))
    rolled = loop[pivot:] + loop[:pivot]
    out = rdp(rolled + [rolled[0]])
    return out[:-1] if len(out) > 3 else loop


def chaikin(
    loop: list[tuple[float, float]],
    passes: int,
    pinned: frozenset[tuple[float, float]] = frozenset(),
) -> list[tuple[float, float]]:
    """Corner-cutting on a closed loop, except where a town stands on it.

    Chaikin cuts every convex corner inward. A town is sampled anywhere inside
    its cell, corner included, so cutting the corner of a coastal cell can put
    the town in the sea -- which is exactly what it did to the two capes
    `ithford` and `caluen` stand on.

    So a vertex belonging to a cell that holds a town survives each pass
    unmoved. The shore is smoothed everywhere the smoothing cannot cost
    anything, and stays on the traced lattice edge where it could. The
    containment check afterwards is what proves it worked.
    """
    points = loop
    for _ in range(passes):
        out: list[tuple[float, float]] = []
        for i, (x1, y1) in enumerate(points):
            x2, y2 = points[(i + 1) % len(points)]
            if (x1, y1) in pinned:
                out.append((x1, y1))
            else:
                out.append((x1 * 0.75 + x2 * 0.25, y1 * 0.75 + y2 * 0.25))
            if (x2, y2) not in pinned:
                out.append((x1 * 0.25 + x2 * 0.75, y1 * 0.25 + y2 * 0.75))
        points = out
    return points


def point_in_polygon(point: tuple[float, float], loop: Sequence[Sequence[float]]) -> bool:
    """Ray casting, in whatever units the loop is in."""
    px, py = point
    inside = False
    for i, corner in enumerate(loop):
        x1, y1 = corner[0], corner[1]
        following = loop[(i + 1) % len(loop)]
        x2, y2 = following[0], following[1]
        if (y1 > py) != (y2 > py):
            cross = x1 + (py - y1) / (y2 - y1) * (x2 - x1)
            if cross > px:
                inside = not inside
    return inside


def polygons_for(
    mask: list[list[bool]],
    smooth: bool,
    pinned: frozenset[tuple[float, float]] = frozenset(),
) -> tuple[list[list[list[float]]], list[list[list[float]]]]:
    """Outlines and enclosed holes of a lattice mask, in miles, largest first.

    Returned apart because they are different things and a consumer that
    cannot tell them apart draws the second as the first: emitting all 30 of
    seed 1's rings as `coastlines` made `mapview` report "30 landmasses (29
    islands)" and fill twenty-eight inland lakes as if they were land.
    """
    outlines: list[tuple[float, list]] = []
    holes: list[tuple[float, list]] = []
    for loop in trace_mask(mask):
        area = signed_area(loop)
        if abs(area) < MIN_COMPONENT_CELLS:
            continue
        shaped = loop
        if smooth:
            shaped = chaikin(simplify(loop, SIMPLIFY_TOLERANCE, pinned), SMOOTH_PASSES, pinned)
        polygon = [
            [round(x * CELL_MILES, 2), round(y * CELL_MILES, 2)] for x, y in shaped
        ]
        (outlines if area < 0 else holes).append((abs(area), polygon))

    outlines.sort(key=lambda pair: pair[0], reverse=True)
    holes.sort(key=lambda pair: pair[0], reverse=True)
    return [p for _, p in outlines], [p for _, p in holes]


# ---------------------------------------------------------------------------
# the field, and whether a map belongs to it
# ---------------------------------------------------------------------------


def build_field(seed: int, relief: str = gw.DEFAULT_RELIEF):
    """The generator's own landmass and terrain, from its own calls.

    The call order is `generate()`'s, and it has to stay that way: the two
    functions draw from one Random, so building terrain before land, or
    skipping either, silently produces a different continent. `relief` has to
    match the mode the world was generated with, for the same reason.
    """
    rng = random.Random(seed)
    land = build_landmass(rng, relief)
    terrain = build_terrain(rng, land, relief)
    return land, terrain


def candidate_cells(city: dict) -> list[tuple[int, int]]:
    """The cells a town's recorded coordinates can have come from.

    `place_towns` writes `round((cell + fraction) * 10, 1)`, and that rounding
    is lossy at the cell boundary: a fraction above 0.9995 rounds up into the
    next cell's coordinate, and one below 0.0005 rounds down onto its own.
    A coordinate that is an exact multiple of ten is therefore ambiguous
    between two cells, and the map does not record which. Both are offered,
    and a town is accepted if either explains it -- refusing on a tie the data
    cannot break would be reporting the rounding as a different world.
    """
    x_miles = city.get("x_miles")
    y_miles = city.get("y_miles")
    if not isinstance(x_miles, (int, float)) or not isinstance(y_miles, (int, float)):
        x_miles = float(city.get("x", 0)) * FIELD_WIDTH_MILES
        y_miles = float(city.get("y", 0)) * FIELD_HEIGHT_MILES

    def axis(miles: float, limit: int) -> list[int]:
        base = int(float(miles) // CELL_MILES)
        cells = [base]
        if abs(float(miles) - base * CELL_MILES) < 1e-9:
            cells.append(base - 1)
        return [c for c in cells if 0 <= c < limit]

    return [(cx, cy) for cx in axis(x_miles, GRID_W) for cy in axis(y_miles, GRID_H)]


def sea_route_towns(roads: list[dict] | None) -> set[str]:
    """Towns with a sea route. `build_routes` records those as quality `sea`."""
    towns: set[str] = set()
    for road in roads or []:
        if road.get("quality") != "sea":
            continue
        for end in (road.get("from"), road.get("to")):
            if isinstance(end, str):
                towns.add(end)
    return towns


def verify_field(cities: list[dict], land, terrain, roads: list[dict] | None = None) -> list[str]:
    """Whether every town in a map stands where this field allows.

    A town must be on land, and its terrain label must match the cell it
    stands in.

    The port check is asymmetric. A coastal cell is always a port, so a
    coastal town that is not one fails. An inland port does not fail on its
    own, because `build_routes` promotes both ends of a connectivity link that
    has to cross water wherever they are -- but it records that link as a
    route of quality `sea`, so when the map's roads are supplied the promotion
    is checked rather than waved through: an inland port with no sea route
    touching it is a mismatch.
    """
    problems = []
    sailing = sea_route_towns(roads)
    for city in cities:
        name = city.get("id", "?")
        labels = city.get("terrain") or []
        label = labels[0] if labels else None
        cells = candidate_cells(city)

        ashore = [(cx, cy) for cx, cy in cells if land[cy][cx]]
        if not ashore:
            where = ", ".join(str(c) for c in cells)
            problems.append(f"{name}: stands in open water at cell {where}")
            continue

        matching = [(cx, cy) for cx, cy in ashore if not label or terrain[cy][cx] == label]
        if not matching:
            found = sorted({terrain[cy][cx] for cx, cy in ashore})
            problems.append(f"{name}: map says {label!r}, the field says {found}")
            continue

        coastal = any(is_coastal(land, cx, cy) for cx, cy in matching)
        if not city.get("is_port") and all(is_coastal(land, cx, cy) for cx, cy in matching):
            problems.append(f"{name}: the cell touches water but the map says it is no port")
        elif city.get("is_port") and not coastal and roads is not None and name not in sailing:
            problems.append(
                f"{name}: an inland port with no sea route to explain it"
            )
    return problems


def verify_exact(cities: list[dict], seed: int, relief: str = gw.DEFAULT_RELIEF) -> list[str]:
    """The strongest check there is: regenerate the world and compare.

    Only a full generated world can pass this -- a subsampled or renamed map
    cannot -- so it is a proof of provenance when it holds, and silence when
    it does not, rather than a failure.
    """
    from scripts.generate_world import generate

    try:
        produced = generate(seed, towns=len(cities), relief=relief)["cities"]
    except ValueError:
        # Fewer towns than the generator's regions: a subsample, which this
        # check cannot speak to either way.
        return ["too few towns to regenerate"]
    if produced == cities:
        return []
    return ["not a verbatim regeneration of this seed"]


def check_containment(cities: list[dict], coastlines: list[list[list[float]]]) -> list[str]:
    """No town may end up offshore once the shore is smoothed.

    Simplifying and rounding move the drawn coast by up to half a cell, and a
    town sampled at the seaward corner of a coastal cell is exactly where that
    matters. A town in the water is the one drawing error nobody would forgive,
    so it is checked rather than assumed.
    """
    problems = []
    for city in cities:
        x_miles = city.get("x_miles")
        y_miles = city.get("y_miles")
        if not isinstance(x_miles, (int, float)) or not isinstance(y_miles, (int, float)):
            continue
        point = (float(x_miles), float(y_miles))
        # Even-odd across every ring: a town inside an island and outside its
        # lake counts as ashore.
        if sum(point_in_polygon(point, ring) for ring in coastlines) % 2 == 0:
            problems.append(
                f"{city.get('id', '?')}: at ({point[0]}, {point[1]}) the drawn "
                "coastline puts it offshore"
            )
    return problems


def _nearest_water(land, cx: int, cy: int) -> tuple[int, int] | None:
    """The cell itself if it is water, else the closest water within a few."""
    if not land[cy][cx]:
        return cx, cy
    for radius in (1, 2, 3, 4):
        best = None
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < GRID_W and 0 <= ny < GRID_H and not land[ny][nx]:
                    d = dx * dx + dy * dy
                    if best is None or d < best[0]:
                        best = (d, (nx, ny))
        if best:
            return best[1]
    return None


def water_path(land, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    """Shortest run of water cells from one to the other, or [] if there is none."""
    import heapq

    if start == goal:
        return [start]
    diagonal = math.sqrt(2)
    best = {start: 0.0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    queue = [(0.0, start)]
    while queue:
        cost, cell = heapq.heappop(queue)
        if cell == goal:
            break
        if cost > best.get(cell, math.inf):
            continue
        x, y = cell
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < GRID_W and 0 <= ny < GRID_H) or land[ny][nx]:
                    continue
                step = diagonal if dx and dy else 1.0
                if cost + step < best.get((nx, ny), math.inf):
                    best[(nx, ny)] = cost + step
                    came[(nx, ny)] = cell
                    heapq.heappush(queue, (cost + step, (nx, ny)))

    if goal not in came and goal != start:
        return []
    path = [goal]
    while path[-1] != start:
        path.append(came[path[-1]])
    path.reverse()
    return path


def sea_route_paths(land, cities: list[dict], roads: list[dict] | None) -> dict:
    """Where each sea lane actually sails, as mile coordinates.

    A lane drawn straight from town to town crosses whatever lies between,
    which for an island-to-mainland run is most of both: on the chosen world
    thirteen of nineteen lanes were drawn mostly over land, one of them 78%
    ashore. The classification was right and the line was a lie.

    So the lane is routed through water and only its two ends touch the shore.
    The path is the shortest run of water cells between the towns' nearest
    water, simplified and rounded the same way the coast is, with the towns
    themselves as endpoints so the lane still visibly starts and finishes at a
    port.
    """
    if not roads:
        return {}
    by_id = {c.get("id"): c for c in cities}
    paths: dict[str, list[list[float]]] = {}
    for road in roads:
        if road.get("quality") != "sea":
            continue
        a, b = by_id.get(road.get("from")), by_id.get(road.get("to"))
        if not a or not b:
            continue
        start = _nearest_water(land, *candidate_cells(a)[0])
        goal = _nearest_water(land, *candidate_cells(b)[0])
        if start is None or goal is None:
            continue
        cells = water_path(land, start, goal)
        if not cells:
            continue
        middle = [(x + 0.5, y + 0.5) for x, y in cells]
        if len(middle) > 3:
            middle = smooth_open(simplify_open(middle, SIMPLIFY_TOLERANCE), SMOOTH_PASSES)
        points = (
            [(a["x_miles"] / CELL_MILES, a["y_miles"] / CELL_MILES)]
            + middle
            + [(b["x_miles"] / CELL_MILES, b["y_miles"] / CELL_MILES)]
        )
        paths[road["id"]] = [
            [round(x * CELL_MILES, 2), round(y * CELL_MILES, 2)] for x, y in points
        ]
    return paths


def pinned_corners(cities: list[dict]) -> frozenset[tuple[float, float]]:
    """The lattice corners of every cell a town could stand in.

    These are the vertices simplification and smoothing may not move, because
    a town sampled at the seaward corner of a coastal cell is inside the
    traced boundary and outside any shore drawn short of it.
    """
    corners: set[tuple[float, float]] = set()
    for city in cities:
        for cx, cy in candidate_cells(city):
            corners.update(
                {(cx, cy), (cx + 1, cy), (cx, cy + 1), (cx + 1, cy + 1)}
            )
    return frozenset(corners)


def build_geography(
    seed: int,
    cities: list[dict] | None = None,
    smooth: bool = True,
    relief: str = gw.DEFAULT_RELIEF,
    roads: list[dict] | None = None,
) -> dict:
    land, terrain = build_field(seed, relief)
    pinned = pinned_corners(cities or [])
    coastlines, lakes = polygons_for(land, smooth, pinned)
    return {
        "units": "miles",
        "field_miles": [FIELD_WIDTH_MILES, FIELD_HEIGHT_MILES],
        "grid": {
            "cols": GRID_COLS,
            "rows": GRID_ROWS,
            "cell_miles": FIELD_WIDTH_MILES // GRID_COLS,
        },
        "source": {
            "generator": "scripts/generate_world.py",
            "seed": seed,
            "relief": relief,
        },
        "coastlines": coastlines,
        # Where each sea lane sails. Empty when the map has no sea lanes, or
        # when it was built without its roads.
        "sea_routes": sea_route_paths(land, cities or [], roads),
        # Water the continent encloses. A separate key because the schema's
        # consumers read `coastlines` as land, and a lake in that list is an
        # island. Nothing in the tree reads this yet; dropping it instead
        # would be drawing land over water the field really has.
        "lakes": lakes,
        # The generator models no rivers. An empty list says that; a drawn one
        # would be this file inventing hydrology.
        "rivers": [],
        "terrain": {
            # Outlines only. A hole in a terrain region is either another
            # terrain, which paints its own outline over it, or a lake, which
            # is drawn from `lakes` -- so the hole is covered either way and
            # a second ring here would only fight the first.
            kind: polygons_for(
                [
                    [land[y][x] and terrain[y][x] == kind for x in range(GRID_W)]
                    for y in range(GRID_H)
                ],
                smooth,
                pinned,
            )[0]
            for kind in TERRAIN_KINDS
        },
    }


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seed", type=int, required=True, help="the world's generator seed")
    parser.add_argument(
        "--relief", choices=gw.RELIEF_MODES, default=gw.DEFAULT_RELIEF,
        help="the relief the world was generated with; a mismatch is refused",
    )
    parser.add_argument(
        "--map",
        type=Path,
        help="world JSON to verify against; every town must belong to this field",
    )
    parser.add_argument("--out", type=Path, help="where to write the sidecar")
    parser.add_argument(
        "--raw", action="store_true", help="emit the lattice staircase, unsmoothed"
    )
    parser.add_argument(
        "--check-only", action="store_true", help="verify and report, write nothing"
    )
    args = parser.parse_args(argv)

    if not args.out and not args.check_only:
        parser.error("give --out, or --check-only")

    land, terrain = build_field(args.seed, args.relief)
    land_cells = sum(row.count(True) for row in land)
    print(
        f"seed {args.seed}: {land_cells} land cells of {GRID_W * GRID_H} "
        f"({land_cells / (GRID_W * GRID_H):.0%} land)"
    )

    cities: list[dict] = []
    if args.map:
        world = json.loads(args.map.read_text(encoding="utf-8"))
        cities = world.get("cities", [])
        problems = verify_field(cities, land, terrain, world.get("roads"))
        if problems:
            print(f"\nrefusing: {args.map} does not belong to seed {args.seed}")
            for problem in problems[:20]:
                print(f"  {problem}")
            if len(problems) > 20:
                print(f"  ... and {len(problems) - 20} more")
            return 1

        if not verify_exact(cities, args.seed, args.relief):
            print(f"{args.map}: regenerates verbatim from seed {args.seed}")
        else:
            print(
                f"{args.map}: all {len(cities)} towns stand on this field "
                "(derived map: not a verbatim regeneration)"
            )

    geography = build_geography(
        args.seed, cities, smooth=not args.raw, relief=args.relief,
        roads=(world.get("roads") if args.map else None),
    )

    if cities:
        offshore = check_containment(cities, geography["coastlines"])
        if offshore:
            print("\nrefusing: the drawn coastline does not contain every town")
            for problem in offshore[:20]:
                print(f"  {problem}")
            print("\nRe-run with --raw to emit the lattice boundary instead.")
            return 1
        print(f"drawn coastline contains all {len(cities)} towns")

    counts = ", ".join(
        f"{kind} {len(polys)}" for kind, polys in geography["terrain"].items() if polys
    )
    print(f"coastline polygons: {len(geography['coastlines'])}; terrain: {counts}")

    if args.check_only:
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(geography, indent=1) + "\n", encoding="utf-8")
    size = args.out.stat().st_size
    print(f"wrote {args.out} ({size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
