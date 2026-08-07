"""
Extract coastlines and terrain regions from the gamemaster's map raster.

``docs/soe_map_sample.png`` is a 586x452 flat-palette image: every terrain
type is a solid legend colour, so the geography can be recovered exactly by
colour-keying rather than guessed at. Roads, rivers, sea lanes and town
labels are drawn *over* the terrain, punching line-shaped holes in it; we
close those holes morphologically before tracing, so a road crossing an
island does not cut the island in two.

Output is in miles, not pixels: the map's scale bar fixes 400 miles at
161px, and the 13x10 grid works out to 100-mile cells, so the whole field
is a 1300 x 1000 mile graticule. Working in miles keeps the geography in
the same units the engine already prices travel and SCAN in.

Usage:
    python scripts/extract_geography.py [--debug]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage import measure

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RASTER = REPO_ROOT / "docs" / "soe_map_sample.png"
DEFAULT_OUT = REPO_ROOT / "maps" / "soe_geography.json"

# Map field, registered from the grid tick marks in the raster's margins
# rather than from the frame: the ticks sit exactly 40px apart, giving 13x10
# cells of 40px and a clean 2.5 miles per pixel. (The drawn frame clips the
# last row short, but rows I-J hold no towns.)
FIELD = (27, 546, 43, 442)  # x0, x1, y0, y1 inclusive -> 520 x 400 px
GRID_COLS, GRID_ROWS = 13, 10
MILES_PER_CELL = 100.0

# Legend colours. Each terrain lists its fill plus any shading variants.
TERRAIN_COLOURS: dict[str, list[tuple[int, int, int]]] = {
    "mountains": [(170, 170, 170), (127, 127, 127)],
    "hills": [(213, 127, 63), (213, 85, 0)],
    "forest": [(0, 127, 0)],
    "plain": [(0, 255, 0), (0, 213, 0), (0, 170, 0)],
    "desert": [(255, 255, 0), (255, 213, 0)],
}
SWAMP_SPECKLE = (0, 127, 127)  # teal marks stippled over the forest green
SEA_COLOUR = (127, 213, 255)
PANEL_BORDER = (255, 0, 0)  # legend panels are drawn as red rectangles
RIVER_COLOUR = (0, 0, 255)  # rivers are the only pure blue on the map

# Terrain draw order: coarse ground first, distinctive relief on top.
TERRAIN_ORDER = ["plain", "forest", "swamp", "desert", "hills", "mountains"]


def mask_for(rgb: np.ndarray, colours: list[tuple[int, int, int]]) -> np.ndarray:
    out = np.zeros(rgb.shape[:2], dtype=bool)
    for colour in colours:
        out |= np.all(rgb == np.array(colour, dtype=rgb.dtype), axis=2)
    return out


def chrome_mask(rgb: np.ndarray) -> np.ndarray:
    """Legend panels sit inside the map field and their terrain swatches would
    otherwise trace as islands. Each panel is a large red rectangle, so find
    those and blank out their interiors."""
    red = mask_for(rgb, [PANEL_BORDER])
    labels, _ = ndimage.label(red, structure=np.ones((3, 3)))
    out = np.zeros(rgb.shape[:2], dtype=bool)
    for box in ndimage.find_objects(labels):
        height = box[0].stop - box[0].start
        width = box[1].stop - box[1].start
        if width > 50 and height > 40:  # a panel, not a road or a title glyph
            out[box] = True
    return ndimage.binary_dilation(out, np.ones((5, 5)))


def px_to_miles(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Field pixel coords -> miles, origin at the field's top-left corner."""
    x0, x1, y0, y1 = FIELD
    w, h = x1 - x0 + 1, y1 - y0 + 1
    return (
        x * (GRID_COLS * MILES_PER_CELL / w),
        y * (GRID_ROWS * MILES_PER_CELL / h),
    )


def trace(mask: np.ndarray, min_area_px: int, simplify_px: float) -> list[list]:
    """Marching-squares contours of a mask, simplified, in mile coordinates."""
    labels, count = ndimage.label(mask)
    polygons: list[list] = []
    for index in range(1, count + 1):
        component = labels == index
        if component.sum() < min_area_px:
            continue
        # Pad so components touching the field edge still close cleanly.
        padded = np.pad(component, 1)
        for contour in measure.find_contours(padded.astype(float), 0.5):
            if len(contour) < 8:
                continue
            coords = measure.approximate_polygon(contour, tolerance=simplify_px)
            if len(coords) < 4:
                continue
            xs, ys = px_to_miles(coords[:, 1] - 1, coords[:, 0] - 1)
            polygons.append(
                [[round(float(a), 2), round(float(b), 2)] for a, b in zip(xs, ys)]
            )
    return polygons


def terrain_rasters(raster: Path) -> tuple[np.ndarray, np.ndarray]:
    """Classify the field into terrain indices (1-based, per TERRAIN_ORDER)
    plus a land mask. Shared with the position solver so both agree on where
    the ground is."""
    x0, x1, y0, y1 = FIELD
    rgb = np.array(Image.open(raster).convert("RGB"))[y0 : y1 + 1, x0 : x1 + 1]

    chrome = chrome_mask(rgb)
    speckle = mask_for(rgb, [SWAMP_SPECKLE]) & ~chrome
    raw = {
        name: mask_for(rgb, cols) & ~chrome
        for name, cols in TERRAIN_COLOURS.items()
    }

    # Sea lanes are drawn in the same yellow as desert fill. Desert is a blob
    # and a sea lane is a 1-2px line, so an opening removes the lanes only.
    raw["desert"] = ndimage.binary_opening(raw["desert"], np.ones((3, 3)))

    # Swamp is teal stipple over forest green: the speckled forest components
    # are swamp, the rest stay forest.
    forest_labels, forest_count = ndimage.label(raw["forest"] | speckle)
    swamp_ids = set(np.unique(forest_labels[speckle])) - {0}
    swamp = np.isin(forest_labels, list(swamp_ids)) if swamp_ids else np.zeros_like(speckle)
    raw["swamp"] = swamp
    raw["forest"] = (raw["forest"] | speckle) & ~swamp

    # Land = any terrain. Roads/labels drawn over land leave line-shaped gaps;
    # close them and fill enclosed holes so islands stay whole.
    land = np.zeros(rgb.shape[:2], dtype=bool)
    for mask in raw.values():
        land |= mask
    land = ndimage.binary_closing(land, np.ones((5, 5)))
    land = ndimage.binary_fill_holes(land)
    # Never let the closing eat into open sea.
    land &= ~ndimage.binary_erosion(mask_for(rgb, [SEA_COLOUR]), np.ones((7, 7)))

    # Reassign overdrawn pixels to the nearest terrain so regions stay solid.
    assigned = np.zeros(rgb.shape[:2], dtype=np.int32)
    for i, name in enumerate(TERRAIN_ORDER, start=1):
        assigned[raw[name]] = i
    gaps = land & (assigned == 0)
    if gaps.any():
        _, (iy, ix) = ndimage.distance_transform_edt(
            assigned == 0, return_indices=True
        )
        assigned[gaps] = assigned[iy[gaps], ix[gaps]]

    rivers = mask_for(rgb, [RIVER_COLOUR]) & ~chrome & land
    return assigned, land, rivers


def build(raster: Path, out: Path, debug: bool) -> dict:
    assigned, land, rivers = terrain_rasters(raster)

    geography = {
        "units": "miles",
        "field_miles": [GRID_COLS * MILES_PER_CELL, GRID_ROWS * MILES_PER_CELL],
        "grid": {"cols": GRID_COLS, "rows": GRID_ROWS, "cell_miles": MILES_PER_CELL},
        "coastlines": trace(land, min_area_px=12, simplify_px=0.6),
        "rivers": trace(rivers, min_area_px=6, simplify_px=0.5),
        "terrain": {
            name: trace(
                (assigned == i) & land, min_area_px=10, simplify_px=0.8
            )
            for i, name in enumerate(TERRAIN_ORDER, start=1)
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(geography, indent=1) + "\n", encoding="utf-8")

    if debug:
        palette = {
            "plain": (120, 200, 90), "forest": (34, 110, 50),
            "swamp": (70, 120, 110), "desert": (232, 210, 140),
            "hills": (196, 150, 95), "mountains": (150, 145, 140),
        }
        canvas = np.full((*assigned.shape, 3), (150, 200, 230), dtype=np.uint8)
        for i, name in enumerate(TERRAIN_ORDER, start=1):
            canvas[assigned == i] = palette[name]
        canvas[~land] = (150, 200, 230)
        Image.fromarray(canvas).resize(
            (assigned.shape[1] * 2, assigned.shape[0] * 2), Image.NEAREST
        ).save(REPO_ROOT / "docs" / "debug_terrain.png")

    return geography


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", type=Path, default=DEFAULT_RASTER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    geo = build(args.raster, args.out, args.debug)
    print(f"wrote {args.out}")
    print(f"  coastline polygons: {len(geo['coastlines'])}")
    print(f"  river polygons:     {len(geo['rivers'])}")
    for name, polys in geo["terrain"].items():
        pts = sum(len(p) for p in polys)
        print(f"  {name:<10} {len(polys):4d} polygons, {pts:6d} points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
