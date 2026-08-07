"""
Place every town at a position consistent with the gamemaster's own data.

The index fixes each town's grid cell (100 miles square) and its terrain,
and gives the mileage of all 230 routes. Those three facts together pin the
towns down far more tightly than the grid alone: a cell centre is only good
to +-50 miles, but a town also has to sit on the right kind of ground and at
the right distance from its neighbours.

So we solve, rather than guess:

  * candidates  - the pixels inside the town's grid cell that are land, and
                  preferably of the town's stated terrain;
  * objective   - stress majorization (SMACOF) against route mileages, with
                  land routes trusted more than sea lanes, which bend around
                  headlands;
  * projection  - after each update the town is snapped back to its nearest
                  candidate pixel, so it can never leave its cell or its
                  terrain, or wander into the sea.

Route mileage exceeds crow-flight distance, so we fit a detour factor per
route type each iteration instead of assuming one.

Usage:
    python scripts/solve_positions.py [--iterations N] [--report]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_geography import (  # noqa: E402
    GRID_COLS,
    GRID_ROWS,
    MILES_PER_CELL,
    TERRAIN_ORDER,
    terrain_rasters,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORLD = REPO_ROOT / "maps" / "soe_world.json"
DEFAULT_RASTER = REPO_ROOT / "docs" / "soe_map_sample.png"

ROW_LETTERS = "ABCDEFGHIJ"
SEA_WEIGHT = 0.25  # sea lanes detour around coasts; trust them less
MIN_SEPARATION = 6.0  # miles; keeps co-located towns legible


def cell_box(grid_ref: str) -> tuple[float, float, float, float]:
    """Grid reference -> (x0, x1, y0, y1) in miles."""
    row = ROW_LETTERS.index(grid_ref[0])
    col = int(grid_ref[1:])
    return (
        (col - 1) * MILES_PER_CELL,
        col * MILES_PER_CELL,
        row * MILES_PER_CELL,
        (row + 1) * MILES_PER_CELL,
    )


def build_candidates(world: dict, raster: Path) -> tuple[dict, list[str]]:
    """For each town, the mile coordinates it is allowed to occupy."""
    assigned, land, _rivers = terrain_rasters(raster)
    height, width = assigned.shape
    mx = GRID_COLS * MILES_PER_CELL / width
    my = GRID_ROWS * MILES_PER_CELL / height

    cols_mi = (np.arange(width) + 0.5) * mx
    rows_mi = (np.arange(height) + 0.5) * my

    candidates: dict[str, np.ndarray] = {}
    notes: list[str] = []
    for city in world["cities"]:
        wanted = [TERRAIN_ORDER.index(t) + 1 for t in city["terrain"]
                  if t in TERRAIN_ORDER]

        def window_for(pad: float):
            x0, x1, y0, y1 = cell_box(city["grid_ref"])
            cx = (cols_mi >= x0 - pad) & (cols_mi < x1 + pad)
            cy = (rows_mi >= y0 - pad) & (rows_mi < y1 + pad)
            return cx, cy

        # The grid reference is hand-assigned and a handful of cells hold no
        # land at all, so it is a preference, not a hard bound: fall back
        # through terrain, then land, then the surrounding ring of cells.
        chosen = None
        for pad, label in ((0.0, "cell"), (MILES_PER_CELL, "neighbouring cells")):
            cx, cy = window_for(pad)
            window = np.ix_(cy, cx)
            here_land = land[window]
            here_terrain = np.isin(assigned[window], wanted) & here_land
            for mask, why in (
                (here_terrain, None if pad == 0 else f"terrain found in {label}"),
                (here_land, f"no matching terrain; any land in {label}"),
            ):
                if mask.any():
                    chosen = (mask, cx, cy, why)
                    break
            if chosen:
                break
        if chosen is None:
            cx, cy = window_for(0.0)
            chosen = (np.ones((cy.sum(), cx.sum()), bool), cx, cy,
                      "no land nearby; anywhere in cell")

        mask, cx, cy, why = chosen
        if why:
            notes.append(f"{city['name']} ({city['grid_ref']}, "
                         f"{'/'.join(city['terrain'])}): {why}")

        ys, xs = np.nonzero(mask)
        candidates[city["id"]] = np.column_stack(
            (cols_mi[cx][xs], rows_mi[cy][ys])
        )
    return candidates, notes


def solve(world: dict, candidates: dict, iterations: int) -> tuple[dict, dict]:
    ids = [c["id"] for c in world["cities"]]
    index = {cid: i for i, cid in enumerate(ids)}

    edges, miles, weights, is_sea = [], [], [], []
    for road in world["roads"]:
        edges.append((index[road["from"]], index[road["to"]]))
        miles.append(road["distance_miles"])
        sea = road["quality"] == "sea"
        is_sea.append(sea)
        weights.append(SEA_WEIGHT if sea else 1.0)
    edges = np.array(edges)
    miles = np.array(miles, dtype=float)
    weights = np.array(weights)
    is_sea = np.array(is_sea)

    # Start at the candidate nearest each cell centre.
    pos = np.zeros((len(ids), 2))
    for city in world["cities"]:
        x0, x1, y0, y1 = cell_box(city["grid_ref"])
        centre = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        cand = candidates[city["id"]]
        pos[index[city["id"]]] = cand[
            np.argmin(((cand - centre) ** 2).sum(axis=1))
        ]

    detour = {"land": 1.15, "sea": 1.15}
    for _ in range(iterations):
        delta = pos[edges[:, 0]] - pos[edges[:, 1]]
        dist = np.hypot(delta[:, 0], delta[:, 1])

        # Refit how much longer a route is than the straight line it spans.
        # A route can never be shorter than the straight line it spans, so the
        # detour factor is clamped at 1: anything less would mean the fitted
        # positions are further apart than the gamemaster's own mileage.
        for name, sel in (("land", ~is_sea), ("sea", is_sea)):
            live = sel & (dist > 1.0)
            if live.any():
                detour[name] = float(
                    np.clip(np.median(miles[live] / dist[live]), 1.0, 2.0)
                )
        target = miles / np.where(is_sea, detour["sea"], detour["land"])

        # SMACOF update: pull each endpoint toward its target separation.
        unit = delta / np.maximum(dist, 1e-9)[:, None]
        nxt = np.zeros_like(pos)
        wsum = np.zeros(len(ids))
        for (a, b), t, w, u in zip(edges, target, weights, unit):
            nxt[a] += w * (pos[b] + t * u)
            nxt[b] += w * (pos[a] - t * u)
            wsum[a] += w
            wsum[b] += w
        moved = wsum > 0
        pos[moved] = nxt[moved] / wsum[moved][:, None]

        # Project back onto legal ground.
        for cid, i in index.items():
            cand = candidates[cid]
            pos[i] = cand[np.argmin(((cand - pos[i]) ** 2).sum(axis=1))]

        # Nudge apart any towns that landed on the same spot.
        for i in range(len(ids)):
            close = np.nonzero(
                (np.hypot(*(pos - pos[i]).T) < MIN_SEPARATION)
                & (np.arange(len(ids)) != i)
            )[0]
            for j in close:
                push = pos[j] - pos[i]
                norm = np.hypot(*push) or 1.0
                cand = candidates[ids[j]]
                want = pos[j] + push / norm * MIN_SEPARATION
                pos[j] = cand[np.argmin(((cand - want) ** 2).sum(axis=1))]

    delta = pos[edges[:, 0]] - pos[edges[:, 1]]
    dist = np.hypot(delta[:, 0], delta[:, 1])
    target = miles / np.where(is_sea, detour["sea"], detour["land"])
    residual = np.abs(dist - target)
    stats = {
        "detour_land": round(detour["land"], 3),
        "detour_sea": round(detour["sea"], 3),
        "median_residual_miles": round(float(np.median(residual)), 1),
        "p90_residual_miles": round(float(np.percentile(residual, 90)), 1),
        "worst_residual_miles": round(float(residual.max()), 1),
    }
    return {cid: pos[i] for cid, i in index.items()}, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--iterations", type=int, default=60)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    world = json.loads(args.world.read_text(encoding="utf-8"))
    candidates, notes = build_candidates(world, args.raster)
    placed, stats = solve(world, candidates, args.iterations)

    span_x = GRID_COLS * MILES_PER_CELL
    span_y = GRID_ROWS * MILES_PER_CELL
    for city in world["cities"]:
        x, y = placed[city["id"]]
        city["x_miles"] = round(float(x), 1)
        city["y_miles"] = round(float(y), 1)
        city["x"] = round(float(x) / span_x, 4)
        city["y"] = round(float(y) / span_y, 4)

    args.world.write_text(
        json.dumps(world, indent=2) + "\n", encoding="utf-8"
    )
    print(f"placed {len(placed)} towns in {args.world}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    if notes:
        print(f"\n{len(notes)} towns needed a relaxed candidate set:")
        for note in notes if args.report else notes[:10]:
            print(f"  - {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
