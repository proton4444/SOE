"""
Render the master map of the Spoils of Empire world as SVG.

Everything drawn here comes from ``maps/soe_world.json`` (the gamemaster's
gazetteer) and ``maps/soe_geography.json`` (coastlines traced from the
original raster). Nothing is invented at draw time, so the map cannot
disagree with the engine: same towns, same grid references, same mileages.

The visual language follows Rick Morneau's original -- red for excellent
roads, dashed for fair, dotted for poor, gold sea lanes, four population
tiers plus a marker for uninhabited ruins, and label colour carrying
seaport and magic-free status -- but redrawn as vector art with real
typography, a coastal halo, and terrain that reads at poster size.

Usage:
    python scripts/render_map.py [--out maps/soe_world_map.svg] [--scale 1.6]
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from assign_regions import LABELS as REGION_LABELS  # noqa: E402
from assign_regions import label_anchor_miles  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORLD = REPO_ROOT / "maps" / "soe_world.json"
DEFAULT_GEO = REPO_ROOT / "maps" / "soe_geography.json"
DEFAULT_TEXTURES = REPO_ROOT / "maps" / "textures"
DEFAULT_OUT = REPO_ROOT / "maps" / "soe_world_map.svg"

# Tile size in map pixels for each surface texture, and how strongly it
# multiplies over the flat colour. Ground tiles are small enough that the
# detail reads as texture rather than as landform.
TEXTURE_TILE = {
    "paper": (430, 0.45),
    "sea": (560, 0.34),
    "plain": (300, 0.42),
    "forest": (270, 0.52),
    "swamp": (280, 0.48),
    "desert": (330, 0.40),
    "hills": (310, 0.50),
    "mountains": (360, 0.62),
}

ROW_LETTERS = "ABCDEFGHIJ"

# Muted descendants of the original's saturated legend colours.
PALETTE = {
    "sea": "#a9cfe3",
    "sea_deep": "#8fbcd4",
    "plain": "#cfdca6",
    "forest": "#8aab77",
    "swamp": "#7f9a80",
    "desert": "#ecdcac",
    "hills": "#d7bd93",
    "mountains": "#c3b6a6",
    "coast": "#5d6b70",
    "river": "#6f9fc0",
    "ink": "#20272b",
    "paper": "#f3ece0",
    "excellent": "#b03a2e",
    "sealane": "#b8912f",
    "seaport": "#8e3d78",
    "magicfree": "#9a5a2a",
}

# Population tiers exactly as the original legend states them.
TIERS = [
    (100_000, None, 7.0, "> 100,000"),
    (10_000, 99_999, 5.4, "10,000 - 99,999"),
    (1_000, 9_999, 4.0, "1,000 - 9,999"),
    (1, 999, 2.9, "< 1,000"),
]
RUIN_RADIUS = 3.6

ROAD_STYLE = {
    "excellent": (PALETTE["excellent"], 2.0, None),
    "good": (PALETTE["ink"], 1.7, None),
    "fair": (PALETTE["ink"], 1.4, "7,4"),
    "poor": (PALETTE["ink"], 1.2, "2,4"),
    "sea": (PALETTE["sealane"], 1.1, None),
}


def chaikin(poly: list[list[float]], iterations: int = 2) -> list[list[float]]:
    """Corner-cutting on a closed ring.

    The geography is traced from a 586px raster, so every outline arrives as
    a staircase of axis-aligned steps. Two rounds of Chaikin turn that back
    into something that reads as a drawn coastline. It moves points by well
    under the 2.5-mile source pixel, so nothing meaningful shifts.
    """
    for _ in range(iterations):
        if len(poly) < 4:
            return poly
        smoothed = []
        for i, point in enumerate(poly):
            nxt = poly[(i + 1) % len(poly)]
            smoothed.append(
                [
                    0.75 * point[0] + 0.25 * nxt[0],
                    0.75 * point[1] + 0.25 * nxt[1],
                ]
            )
            smoothed.append(
                [
                    0.25 * point[0] + 0.75 * nxt[0],
                    0.25 * point[1] + 0.75 * nxt[1],
                ]
            )
        poly = smoothed
    return poly


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tier_for(city: dict) -> tuple[float, str]:
    """Symbol radius and CSS class for a town's population."""
    if city["is_ruin"] or city["population"] == 0:
        return RUIN_RADIUS, "ruin"
    for low, _high, radius, _label in TIERS:
        if city["population"] >= low:
            return radius, "town"
    return TIERS[-1][2], "town"


def label_colour(city: dict) -> str:
    if city["is_magic_free"]:
        return PALETTE["magicfree"]
    if city["is_port"]:
        return PALETTE["seaport"]
    return PALETTE["ink"]


def place_labels(cities: list[dict], to_xy, field_w: float, field_h: float):
    """Greedy label placement: big towns pick first, everyone avoids overlap.

    Text width is estimated from character count -- good enough to keep 154
    labels legible without a font-metrics dependency.
    """
    placed: list[tuple[float, float, float, float]] = []
    results = []
    order = sorted(cities, key=lambda c: (-c["population"], c["name"]))
    for city in order:
        x, y = to_xy(city["x_miles"], city["y_miles"])
        radius, _ = tier_for(city)
        size = 9.5 if city["population"] >= 10_000 else 8.2
        width = len(city["name"]) * size * 0.52
        height = size * 1.15

        best = None
        for dx, dy, anchor in (
            (radius + 3, size * 0.35, "start"),
            (-(radius + 3), size * 0.35, "end"),
            (0, -(radius + 4), "middle"),
            (0, radius + size + 1, "middle"),
            (radius + 3, -(radius + 3), "start"),
            (-(radius + 3), -(radius + 3), "end"),
            (radius + 3, radius + size, "start"),
            (-(radius + 3), radius + size, "end"),
        ):
            lx, ly = x + dx, y + dy
            if anchor == "start":
                box = (lx, ly - height, lx + width, ly)
            elif anchor == "end":
                box = (lx - width, ly - height, lx, ly)
            else:
                box = (lx - width / 2, ly - height, lx + width / 2, ly)
            if box[0] < 2 or box[2] > field_w - 2 or box[1] < 2 or box[3] > field_h - 2:
                continue
            if any(
                box[0] < p[2] and p[0] < box[2] and box[1] < p[3] and p[1] < box[3]
                for p in placed
            ):
                continue
            best = (lx, ly, anchor, box)
            break

        if best is None:  # nowhere clear: place right and accept the clash
            lx, ly, anchor = x + radius + 3, y + size * 0.35, "start"
            best = (lx, ly, anchor, (lx, ly - height, lx + width, ly))
        placed.append(best[3])
        results.append((city, best[0], best[1], best[2], size))
    return results


def load_textures(directory: Path) -> dict[str, str]:
    """Read the surface tiles as base64 so the poster is one portable file."""
    if not directory.is_dir():
        return {}
    out = {}
    for name in TEXTURE_TILE:
        path = directory / f"{name}.jpg"
        if path.is_file():
            out[name] = base64.b64encode(path.read_bytes()).decode("ascii")
    return out


def texture_defs(textures: dict[str, str], scale: float) -> str:
    """Tile sizes are quoted at scale 1.6, so scale them with the output to
    keep the texture reading identically at any poster size."""
    parts = []
    for name, data in textures.items():
        tile = round(TEXTURE_TILE[name][0] * scale / 1.6)
        parts.append(
            f'<pattern id="tex-{name}" width="{tile}" height="{tile}" '
            f'patternUnits="userSpaceOnUse">'
            f'<image width="{tile}" height="{tile}" '
            f'href="data:image/jpeg;base64,{data}"/></pattern>'
        )
    return "".join(parts)


def occupied_rows(world: dict, geo: dict) -> int:
    """How many grid rows actually hold land or towns.

    The gamemaster's sheet reserves the bottom rows for its legend panels,
    so drawing all ten would leave a quarter of the poster as empty ocean.
    """
    cell = geo["grid"]["cell_miles"]
    reach = max(
        [p[1] for poly in geo["coastlines"] for p in poly]
        + [c["y_miles"] for c in world["cities"]]
    )
    return min(geo["grid"]["rows"], int(reach // cell) + 1)


def render(
    world: dict, geo: dict, scale: float, rows: int, textures: dict[str, str]
) -> str:
    field_mi_w = geo["field_miles"][0]
    field_mi_h = rows * geo["grid"]["cell_miles"]
    fw, fh = field_mi_w * scale, field_mi_h * scale
    margin = 46.0  # gutter holding the grid letters and numbers
    band = 170.0  # title / legend band beneath the map
    total_w = fw + margin * 2
    total_h = fh + margin * 2 + band

    def to_xy(mx: float, my: float) -> tuple[float, float]:
        return mx * scale, my * scale

    def path_of(poly: list[list[float]], smooth: bool = True) -> str:
        if smooth:
            poly = chaikin(poly)
        pts = " ".join(f"{x * scale:.1f},{y * scale:.1f}" for x, y in poly)
        return f"M {pts} Z"

    out: list[str] = []
    add = out.append

    add(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" '
        f'height="{total_h:.0f}" viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f"font-family=\"Georgia, 'Times New Roman', serif\">"
    )

    # ---- defs: paper grain, coastal halo -------------------------------
    add("<defs>")
    add(
        # Grain as a small tiled pattern: filtering the whole canvas with
        # feTurbulence is correct but ruinously slow to rasterise.
        '<filter id="grainf" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="2"'
        ' seed="7"/>'
        '<feColorMatrix type="saturate" values="0"/></filter>'
        '<pattern id="grain" width="180" height="180" '
        'patternUnits="userSpaceOnUse">'
        '<rect width="180" height="180" filter="url(#grainf)" opacity="0.5"/>'
        "</pattern>"
    )
    add(
        '<filter id="halo" x="-25%" y="-25%" width="150%" height="150%">'
        '<feGaussianBlur stdDeviation="' + f"{2.6 * scale:.1f}" + '"/></filter>'
    )
    add(
        '<filter id="relief" x="-20%" y="-20%" width="140%" height="140%">'
        '<feDropShadow dx="0" dy="' + f"{0.8 * scale:.1f}" + '" '
        'stdDeviation="' + f"{0.9 * scale:.1f}" + '" flood-opacity="0.22"/></filter>'
    )
    add(texture_defs(textures, scale))
    add("</defs>")

    add(
        f'<rect width="{total_w:.0f}" height="{total_h:.0f}" fill="{PALETTE["paper"]}"/>'
    )
    add(f'<g transform="translate({margin},{margin})">')
    add(f'<rect width="{fw:.0f}" height="{fh:.0f}" fill="{PALETTE["sea"]}"/>')
    if "sea" in textures:
        add(
            f'<rect width="{fw:.0f}" height="{fh:.0f}" fill="url(#tex-sea)" '
            f'opacity="{TEXTURE_TILE["sea"][1]}" '
            f'style="mix-blend-mode:multiply"/>'
        )

    # ---- coastal halo: soft light ring around every landmass -----------
    add(f'<g filter="url(#halo)" fill="{PALETTE["sea_deep"]}" opacity="0.85">')
    for poly in geo["coastlines"]:
        add(f'<path d="{path_of(poly)}"/>')
    add("</g>")

    # ---- land -----------------------------------------------------------
    add('<g filter="url(#relief)">')
    for poly in geo["coastlines"]:
        add(f'<path d="{path_of(poly)}" fill="{PALETTE["plain"]}"/>')
    add("</g>")
    for name in ("plain", "forest", "swamp", "desert", "hills", "mountains"):
        polys = geo["terrain"].get(name, [])
        if not polys:
            continue
        shapes = "".join(f'<path d="{path_of(p)}"/>' for p in polys)
        add(f'<g fill="{PALETTE[name]}">{shapes}</g>')
        # Surface texture multiplies over the flat colour, so the palette is
        # unchanged and only the tooth of the ground comes from the tile.
        if name in textures:
            add(
                f'<g fill="url(#tex-{name})" opacity="{TEXTURE_TILE[name][1]}" '
                f'style="mix-blend-mode:multiply">{shapes}</g>'
            )

    # ---- rivers and coastline ink --------------------------------------
    add(
        f'<g fill="{PALETTE["river"]}" opacity="0.9">'
        + "".join(
            f'<path d="{d}"/>'
            for d in [path_of(q, smooth=False) for q in geo.get("rivers", [])]
        )
        + "</g>"
    )
    add(
        f'<g fill="none" stroke="{PALETTE["coast"]}" stroke-width="{1.1:.1f}" '
        f'stroke-linejoin="round" opacity="0.75">'
        + "".join(f'<path d="{path_of(p)}"/>' for p in geo["coastlines"])
        + "</g>"
    )

    # ---- graticule -------------------------------------------------------
    add(f'<g stroke="{PALETTE["ink"]}" stroke-width="0.5" opacity="0.18">')
    for col in range(1, geo["grid"]["cols"]):
        gx = col * geo["grid"]["cell_miles"] * scale
        add(f'<line x1="{gx:.1f}" y1="0" x2="{gx:.1f}" y2="{fh:.0f}"/>')
    for row in range(1, rows):
        gy = row * geo["grid"]["cell_miles"] * scale
        add(f'<line x1="0" y1="{gy:.1f}" x2="{fw:.0f}" y2="{gy:.1f}"/>')
    add("</g>")

    # ---- routes ----------------------------------------------------------
    cities = {c["id"]: c for c in world["cities"]}
    for quality in ("sea", "poor", "fair", "good", "excellent"):
        colour, width, dash = ROAD_STYLE[quality]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        opacity = 0.75 if quality == "sea" else 0.9
        add(
            f'<g stroke="{colour}" stroke-width="{width * scale / 1.6:.2f}" '
            f'fill="none" stroke-linecap="round" opacity="{opacity}"{dash_attr}>'
        )
        for road in world["roads"]:
            if road["quality"] != quality:
                continue
            a, b = cities[road["from"]], cities[road["to"]]
            ax, ay = to_xy(a["x_miles"], a["y_miles"])
            bx, by = to_xy(b["x_miles"], b["y_miles"])
            add(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}"/>')
        add("</g>")

    # ---- towns -----------------------------------------------------------
    add("<g>")
    for city in world["cities"]:
        x, y = to_xy(city["x_miles"], city["y_miles"])
        radius, kind = tier_for(city)
        r = radius * scale / 1.6
        if kind == "ruin":
            add(
                f'<g transform="translate({x:.1f},{y:.1f})" '
                f'stroke="{PALETTE["ink"]}" stroke-width="{0.9 * scale / 1.6:.2f}" '
                f'fill="none" opacity="0.85">'
                f'<path d="M {-r:.1f},{-r:.1f} L {r:.1f},{r:.1f} '
                f'M {-r:.1f},{r:.1f} L {r:.1f},{-r:.1f}"/></g>'
            )
        else:
            add(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" '
                f'fill="{PALETTE["paper"]}" stroke="{PALETTE["ink"]}" '
                f'stroke-width="{1.0 * scale / 1.6:.2f}"/>'
            )
            if city["population"] >= 100_000:
                add(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.45:.2f}" '
                    f'fill="{PALETTE["ink"]}"/>'
                )
    add("</g>")

    town_labels = place_labels(world["cities"], to_xy, fw, fh)

    # ---- region names ----------------------------------------------------
    # Drawn where the original painted them, and drawn first, so the town
    # labels' paper halos cut through anywhere the two meet.
    add(f'<g fill="{PALETTE["ink"]}" opacity="0.38" text-anchor="middle">')
    for name, box, _certain in REGION_LABELS:
        mx, my = label_anchor_miles(box)
        rx, ry = to_xy(mx, my)
        fs = 19 * scale / 1.6
        # Letter-spaced capitals run much wider than the original's label,
        # so nudge the ones near an edge back inside the frame.
        half = len(name) * fs * 0.42
        rx = min(max(rx, half + fs), fw - half - fs)
        # A town label's halo would eat into the region name, so drop the
        # region name clear of any town label sitting across it.
        while any(
            abs(ly - ry) < fs * 0.8 and rx - half < lx < rx + half
            for _city, lx, ly, _anchor, _size in town_labels
        ):
            ry += fs * 1.2
        add(
            f'<text x="{rx:.1f}" y="{ry:.1f}" font-size="{fs:.1f}" '
            f'letter-spacing="{fs * 0.22:.2f}" font-weight="600">'
            f"{esc(name.upper())}</text>"
        )
    add("</g>")

    # ---- labels ----------------------------------------------------------
    add("<g>")
    for city, lx, ly, anchor, size in town_labels:
        fs = size * scale / 1.6
        add(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'font-size="{fs:.1f}" fill="{label_colour(city)}" '
            f'stroke="{PALETTE["paper"]}" stroke-width="{fs * 0.28:.2f}" '
            f'paint-order="stroke" stroke-linejoin="round">{esc(city["name"])}</text>'
        )
    add("</g>")

    add(
        f'<rect width="{fw:.0f}" height="{fh:.0f}" fill="none" '
        f'stroke="{PALETTE["ink"]}" stroke-width="2"/>'
    )
    add("</g>")

    # ---- grid gutter labels ---------------------------------------------
    add(
        f'<g font-size="{16 * scale / 1.6:.1f}" fill="{PALETTE["ink"]}" opacity="0.75">'
    )
    for col in range(geo["grid"]["cols"]):
        gx = margin + (col + 0.5) * geo["grid"]["cell_miles"] * scale
        add(
            f'<text x="{gx:.1f}" y="{margin - 12:.1f}" text-anchor="middle">'
            f"{col + 1}</text>"
        )
    for row in range(rows):
        gy = margin + (row + 0.5) * geo["grid"]["cell_miles"] * scale
        add(
            f'<text x="{margin - 14:.1f}" y="{gy + 6:.1f}" text-anchor="middle">'
            f"{ROW_LETTERS[row]}</text>"
        )
    add("</g>")

    add(render_band(world, geo, scale, margin, fw, fh, band))
    paper_fill = "url(#tex-paper)" if "paper" in textures else "url(#grain)"
    paper_opacity = TEXTURE_TILE["paper"][1] if "paper" in textures else 0.22
    add(
        f'<rect width="{total_w:.0f}" height="{total_h:.0f}" '
        f'fill="{paper_fill}" opacity="{paper_opacity}" '
        f'style="mix-blend-mode:multiply" pointer-events="none"/>'
    )
    add("</svg>")
    return "\n".join(out)


def render_band(world, geo, scale, margin, fw, fh, band) -> str:
    """Title, scale bar and legend beneath the map."""
    top = margin * 2 + fh
    out = [f'<g transform="translate({margin},{top - 20})">']
    ink = PALETTE["ink"]

    out.append(
        f'<text x="0" y="34" font-size="{34 * scale / 1.6:.0f}" fill="{ink}" '
        f'letter-spacing="2">Spoils of Empire</text>'
    )
    out.append(
        f'<text x="0" y="60" font-size="{13 * scale / 1.6:.0f}" fill="{ink}" '
        f'opacity="0.7">The known world &#183; '
        f"{len(world['cities'])} towns &#183; {len(world['roads'])} routes &#183; "
        f"after the map by Rick Morneau</text>"
    )

    # scale bar: 400 miles, matching the original
    bar_y = 108
    bar_len = 400 * scale
    out.append(
        f'<g stroke="{ink}" stroke-width="1.6" fill="none">'
        f'<line x1="0" y1="{bar_y}" x2="{bar_len:.1f}" y2="{bar_y}"/>'
    )
    for i in range(5):
        tx = i * bar_len / 4
        out.append(
            f'<line x1="{tx:.1f}" y1="{bar_y - 6}" x2="{tx:.1f}" y2="{bar_y + 6}"/>'
        )
    out.append("</g>")
    for i in range(5):
        tx = i * bar_len / 4
        out.append(
            f'<text x="{tx:.1f}" y="{bar_y - 12}" text-anchor="middle" '
            f'font-size="{12 * scale / 1.6:.0f}" fill="{ink}">{i * 100}</text>'
        )
    out.append(
        f'<text x="{bar_len / 2:.1f}" y="{bar_y + 24}" text-anchor="middle" '
        f'font-size="{12 * scale / 1.6:.0f}" fill="{ink}" opacity="0.75">miles '
        f"&#183; one grid square = 100 miles</text>"
    )

    fs = 12 * scale / 1.6
    col_x = bar_len + 90 * scale / 1.6

    # road quality
    out.append(
        f'<text x="{col_x:.0f}" y="8" font-size="{fs * 1.15:.1f}" fill="{ink}" '
        f'letter-spacing="1">ROAD QUALITY</text>'
    )
    for i, quality in enumerate(("excellent", "good", "fair", "poor", "sea")):
        colour, width, dash = ROAD_STYLE[quality]
        y = 28 + i * 20
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(
            f'<line x1="{col_x:.0f}" y1="{y}" x2="{col_x + 54:.0f}" y2="{y}" '
            f'stroke="{colour}" stroke-width="{width}"{dash_attr}/>'
        )
        name = "sea lane" if quality == "sea" else quality
        out.append(
            f'<text x="{col_x + 64:.0f}" y="{y + 4}" font-size="{fs:.1f}" '
            f'fill="{ink}">{esc(name)}</text>'
        )

    # population
    pop_x = col_x + 190 * scale / 1.6
    out.append(
        f'<text x="{pop_x:.0f}" y="8" font-size="{fs * 1.15:.1f}" fill="{ink}" '
        f'letter-spacing="1">POPULATION</text>'
    )
    for i, (_low, _high, radius, label) in enumerate(TIERS):
        y = 28 + i * 20
        out.append(
            f'<circle cx="{pop_x + 14:.0f}" cy="{y}" r="{radius:.1f}" '
            f'fill="{PALETTE["paper"]}" stroke="{ink}" stroke-width="1"/>'
        )
        if i == 0:
            out.append(
                f'<circle cx="{pop_x + 14:.0f}" cy="{y}" r="{radius * 0.45:.1f}" '
                f'fill="{ink}"/>'
            )
        out.append(
            f'<text x="{pop_x + 34:.0f}" y="{y + 4}" font-size="{fs:.1f}" '
            f'fill="{ink}">{esc(label)}</text>'
        )
    y = 28 + len(TIERS) * 20
    out.append(
        f'<path d="M {pop_x + 14 - RUIN_RADIUS:.1f},{y - RUIN_RADIUS:.1f} '
        f"l {RUIN_RADIUS * 2:.1f},{RUIN_RADIUS * 2:.1f} "
        f"M {pop_x + 14 - RUIN_RADIUS:.1f},{y + RUIN_RADIUS:.1f} "
        f'l {RUIN_RADIUS * 2:.1f},{-RUIN_RADIUS * 2:.1f}" '
        f'stroke="{ink}" stroke-width="1"/>'
    )
    ruins = sum(1 for c in world["cities"] if c["is_ruin"])
    out.append(
        f'<text x="{pop_x + 34:.0f}" y="{y + 4}" font-size="{fs:.1f}" '
        f'fill="{ink}">uninhabited ruin ({ruins})</text>'
    )

    # town-name colour key
    key_x = pop_x + 250 * scale / 1.6
    out.append(
        f'<text x="{key_x:.0f}" y="8" font-size="{fs * 1.15:.1f}" fill="{ink}" '
        f'letter-spacing="1">TOWN NAMES</text>'
    )
    ports = sum(1 for c in world["cities"] if c["is_port"])
    free = sum(1 for c in world["cities"] if c["is_magic_free"])
    for i, (colour, text) in enumerate(
        (
            (PALETTE["ink"], "inland town"),
            (PALETTE["seaport"], f"seaport ({ports})"),
            (PALETTE["magicfree"], f"magic-free town ({free})"),
        )
    ):
        out.append(
            f'<text x="{key_x:.0f}" y="{32 + i * 20}" font-size="{fs:.1f}" '
            f'fill="{colour}">{esc(text)}</text>'
        )

    out.append("</g>")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=DEFAULT_WORLD)
    parser.add_argument("--geography", type=Path, default=DEFAULT_GEO)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--scale", type=float, default=1.6, help="pixels per mile")
    parser.add_argument(
        "--rows",
        type=int,
        default=0,
        help="grid rows to draw (0 = auto, drop empty ocean)",
    )
    parser.add_argument("--textures", type=Path, default=DEFAULT_TEXTURES)
    parser.add_argument(
        "--no-textures", action="store_true", help="render flat colour only"
    )
    args = parser.parse_args()

    world = json.loads(args.world.read_text(encoding="utf-8"))
    if "x_miles" not in world["cities"][0]:
        raise SystemExit("run scripts/solve_positions.py first")
    geo = json.loads(args.geography.read_text(encoding="utf-8"))

    rows = args.rows or occupied_rows(world, geo)
    textures = {} if args.no_textures else load_textures(args.textures)
    svg = render(world, geo, args.scale, rows, textures)
    args.out.write_text(svg, encoding="utf-8")
    print(
        f"wrote {args.out} ({len(svg) / 1024:.0f} KB, {len(textures)} surface textures)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
