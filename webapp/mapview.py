"""
Map rendering: deterministic layouts and SVG output for the web UI.

Maps may carry optional ``x``/``y`` per city (0..1 fractions of the map field);
when they don't, a deterministic force-directed layout places the cities.

When a paired geography file is present (e.g. ``soe_world.json`` →
``soe_geography.json``), land is drawn from the same traced coastlines the
poster uses — not from road-connected convex hulls. City fractions and
geography miles share one transform over the gazetteer field (1300×1000 mi).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from soe.config import get_hop_cost
from soe.models import Road, RoadQuality

# Fallback canvas when no geography field is available (sample / toy maps).
WIDTH = 1400
HEIGHT = 880
PAD_X = 110
PAD_Y = 100

# Default gazetteer field (matches maps/soe_geography.json).
_DEFAULT_FIELD_MI = (1300.0, 1000.0)

# Cartographic priority for which names stay visible on dense maps.
_BAND_RANK = {
    "100k+": 4,
    "10k-99k": 3,
    "1k-9k": 2,
    "< 1k": 1,
}

# Above this city count we drop permanent secondary chrome (mile labels,
# every-city meta, on-map landmass roster) so the board stays readable.
_DENSE_CITY_COUNT = 24
_VERY_DENSE_CITY_COUNT = 80

# Landmass fills (fill, coastline stroke) — cycled per land body.
_LAND_PALETTE = [
    ("#1a2820", "#5a7a64"),  # continent green
    ("#1a2632", "#5a7a96"),  # island blue
    ("#2a2418", "#8a7a54"),  # arid / secondary
    ("#241a28", "#7a5a8a"),  # violet alternate
]


@dataclass(frozen=True)
class MapLayout:
    """Shared SVG frame + miles/fraction projection for one render."""

    width: float
    height: float
    pad_x: float
    pad_y: float
    pad_bottom: float
    map_w: float
    map_h: float
    field_w_mi: float
    field_h_mi: float
    has_geography: bool = False

    def project_fraction(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.pad_x + min(1.0, max(0.0, float(x))) * self.map_w,
            self.pad_y + min(1.0, max(0.0, float(y))) * self.map_h,
        )

    def project_miles(self, mx: float, my: float) -> tuple[float, float]:
        return (
            self.pad_x + (float(mx) / self.field_w_mi) * self.map_w,
            self.pad_y + (float(my) / self.field_h_mi) * self.map_h,
        )


# Road stroke: (color, width, dasharray)
# Roads are ink laid on the ground, so quality is carried by weight, dash and
# lightness within one warm family -- never by hue. The previous set was a
# green, a blue-grey, an orange and a salmon, chosen when the land was a
# single flat fill and nothing competed with them. With terrain painted
# underneath, the green road disappeared into forest and the orange and salmon
# fought the desert and the hills, so the network read as four unrelated
# things instead of one network in four states.
#
# Sea keeps its blue. That one is not a hue chosen for contrast; it is water.
_ROAD_STYLES = {
    RoadQuality.EXCELLENT: ("#f4ead6", 3.6, "none"),
    RoadQuality.GOOD: ("#d6c9ae", 3.0, "none"),
    RoadQuality.FAIR: ("#b0a488", 2.6, "10 6"),
    RoadQuality.POOR: ("#8d8369", 2.2, "3 5"),
    # Thinner and more broken than it looks like it should be, because a lane
    # is long: nineteen of them, 9% of the routes, were carrying 41% of the
    # network's stroke ink and reading as the subject of the map. Measured
    # again after, they sit near 22%.
    RoadQuality.SEA: ("#5ba7d0", 2.0, "10 12"),
}

_BAND_RADIUS = {
    "< 1k": 6.0,
    "1k-9k": 8.5,
    "10k-99k": 11.5,
    "100k+": 15.0,
}

_BAND_COLORS = {
    "< 1k": "#7a8494",
    "1k-9k": "#b0bac8",
    "10k-99k": "#e0d4b8",
    "100k+": "#d4a84a",
}

# Soft terrain tint blended into the city marker fill.
_TERRAIN_TINT = {
    "forest": "#3d6b4f",
    "woods": "#3d6b4f",
    "desert": "#b08a4a",
    "mountains": "#6a7080",
    "hills": "#7a6e58",
    "coastal": "#4a7a8a",
    "river": "#4a6e8a",
    "plains": "#8a8468",
    "swamp": "#4a5e48",
}


def load_raw_map(map_file: str) -> dict:
    path = _map_path(map_file)
    if not path.exists():
        raise FileNotFoundError(map_file)
    return json.loads(path.read_text(encoding="utf-8"))


def _map_path(map_file: str) -> Path:
    """A path inside ``maps/`` or nothing.

    The name reaches here from a URL segment. ``{name}`` cannot contain a raw
    slash, but percent-encoded separators survive routing and ``..%5C`` walks
    out of the directory on Windows, so confine it twice: the name must be a
    bare filename, and the resolved path must still sit under ``maps/``.
    """
    from webapp.service import _MAPS_DIR

    name = str(map_file or "")
    if not name or name != Path(name).name or name in (".", ".."):
        raise FileNotFoundError(map_file)
    maps_dir = _MAPS_DIR.resolve()
    path = (maps_dir / name).resolve()
    if not path.is_relative_to(maps_dir):
        raise FileNotFoundError(map_file)
    return path


def _maps_dir() -> Path:
    from webapp.service import _MAPS_DIR

    return _MAPS_DIR


def geography_path_for(map_file: str) -> Optional[Path]:
    """Paired coastline file for a world map, if any.

    ``soe_world.json`` → ``soe_geography.json`` (same pair ``render_map.py`` uses).
    """
    stem = Path(map_file).stem
    maps = _maps_dir()
    candidates = [
        maps / f"{stem.replace('_world', '_geography')}.json",
        maps / f"{stem}_geography.json",
    ]
    for path in candidates:
        if path.exists() and path.name != Path(map_file).name:
            return path
    return None


def load_geography(map_file: str) -> Optional[dict]:
    """Load traced coastlines for ``map_file``, or None when absent/invalid."""
    path = geography_path_for(map_file)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("coastlines"):
        return None
    return data


def layout_for_map(
    map_file: str,
    data: Optional[dict] = None,
    geo: Optional[dict] = None,
) -> MapLayout:
    """Canvas sized to the geography field aspect (or the sparse fallback)."""
    if data is None:
        data = load_raw_map(map_file)
    if geo is None:
        geo = load_geography(map_file)

    if geo and geo.get("coastlines"):
        field = geo.get("field_miles") or list(_DEFAULT_FIELD_MI)
        fw = float(field[0])
        fh = float(field[1])
        # 1 SVG unit ≈ 1 mile so the viewBox matches the poster field aspect.
        map_w, map_h = fw, fh
        pad_x = 36.0
        pad_y = 78.0
        pad_bottom = 32.0
        return MapLayout(
            width=map_w + 2 * pad_x,
            height=map_h + pad_y + pad_bottom,
            pad_x=pad_x,
            pad_y=pad_y,
            pad_bottom=pad_bottom,
            map_w=map_w,
            map_h=map_h,
            field_w_mi=fw,
            field_h_mi=fh,
            has_geography=True,
        )

    # Toy / sample maps: fixed frame, fraction coords only.
    return MapLayout(
        width=float(WIDTH),
        height=float(HEIGHT),
        pad_x=float(PAD_X),
        pad_y=float(PAD_Y),
        pad_bottom=float(PAD_Y),
        map_w=float(WIDTH - 2 * PAD_X),
        map_h=float(HEIGHT - 2 * PAD_Y),
        field_w_mi=_DEFAULT_FIELD_MI[0],
        field_h_mi=_DEFAULT_FIELD_MI[1],
        has_geography=False,
    )


def city_miles(city: dict, layout: MapLayout) -> tuple[float, float]:
    """Town position in field miles (authoritative for geography alignment)."""
    xm, ym = city.get("x_miles"), city.get("y_miles")
    if isinstance(xm, (int, float)) and isinstance(ym, (int, float)):
        return float(xm), float(ym)
    x, y = city.get("x"), city.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(x) * layout.field_w_mi, float(y) * layout.field_h_mi
    return 0.0, 0.0


def positions(map_file: str) -> dict[str, tuple[float, float]]:
    """City id -> (x, y) in SVG coordinates. Hand-placed x/y (or miles) wins."""
    data = load_raw_map(map_file)
    layout = layout_for_map(map_file, data)
    cities = data.get("cities") or []
    roads = data.get("roads") or []

    have_coords = all(
        (isinstance(c.get("x"), (int, float)) and isinstance(c.get("y"), (int, float)))
        or (
            isinstance(c.get("x_miles"), (int, float))
            and isinstance(c.get("y_miles"), (int, float))
        )
        for c in cities
    )
    if have_coords and cities:
        out: dict[str, tuple[float, float]] = {}
        for c in cities:
            cid = c.get("id")
            if not cid:
                continue
            mx, my = city_miles(c, layout)
            out[cid] = layout.project_miles(mx, my)
        return out
    return _force_layout(cities, roads, layout)


def _force_layout(
    cities: list[dict],
    roads: list[dict],
    layout: MapLayout,
) -> dict[str, tuple[float, float]]:
    ids = [c["id"] for c in cities if c.get("id")]
    n = len(ids)
    if n == 0:
        return {}
    idx = {cid: i for i, cid in enumerate(ids)}

    pos = []
    for i, _cid in enumerate(ids):
        ang = 2 * math.pi * i / n
        pos.append([math.cos(ang) * 1.6, math.sin(ang) * 1.2])

    adj: list[set[int]] = [set() for _ in range(n)]
    for r in roads:
        a, b = idx.get(r.get("from")), idx.get(r.get("to"))
        if a is not None and b is not None:
            adj[a].add(b)
            adj[b].add(a)

    for _ in range(400):
        for i in range(n):
            for j in range(i + 1, n):
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                dist = math.hypot(dx, dy) + 1e-6
                rep = 0.16 / (dist * dist)
                fx, fy = rep * dx / dist, rep * dy / dist
                pos[i][0] += fx
                pos[i][1] += fy
                pos[j][0] -= fx
                pos[j][1] -= fy
        for i in range(n):
            for j in adj[i]:
                if j <= i:
                    continue
                dx = pos[i][0] - pos[j][0]
                dy = pos[i][1] - pos[j][1]
                dist = math.hypot(dx, dy) + 1e-6
                f = (dist - 1.7) * 0.08
                fx, fy = f * dx / dist, f * dy / dist
                pos[i][0] -= fx
                pos[i][1] -= fy
                pos[j][0] += fx
                pos[j][1] += fy
        for i in range(n):
            pos[i][0] *= 0.992
            pos[i][1] *= 0.992

    xs = [p[0] for p in pos]
    ys = [p[1] for p in pos]
    lo_x, hi_x = min(xs), max(xs)
    lo_y, hi_y = min(ys), max(ys)

    def scale(v, lo, hi, out_lo, out_hi):
        if hi - lo < 1e-9:
            return (out_lo + out_hi) / 2
        return out_lo + (v - lo) * (out_hi - out_lo) / (hi - lo)

    x0 = layout.pad_x
    x1 = layout.pad_x + layout.map_w
    y0 = layout.pad_y
    y1 = layout.pad_y + layout.map_h
    return {
        cid: (
            scale(pos[i][0], lo_x, hi_x, x0, x1),
            scale(pos[i][1], lo_y, hi_y, y0, y1),
        )
        for i, cid in enumerate(ids)
    }


def map_stats(map_file: str) -> dict:
    """Counts for the map chrome (cities, roads, sea lanes, ports, landmasses…)."""
    data = load_raw_map(map_file)
    cities = data.get("cities") or []
    roads = data.get("roads") or []
    layout = layout_for_map(map_file, data)
    geo = load_geography(map_file) if layout.has_geography else None
    pos = positions(map_file)
    if geo and geo.get("coastlines"):
        masses = landmasses_from_geography(geo, cities, layout)
    else:
        masses = compute_landmasses(cities, roads, pos)
    islands = [m for m in masses if m["kind"] == "island"]
    return {
        "cities": len(cities),
        "roads": sum(1 for r in roads if r.get("quality") != "sea"),
        "sea_lanes": sum(1 for r in roads if r.get("quality") == "sea"),
        "ports": sum(1 for c in cities if c.get("is_port")),
        "magic_free": sum(1 for c in cities if c.get("is_magic_free")),
        "ruins": sum(1 for c in cities if c.get("is_ruin")),
        "landmasses": len(masses),
        "islands": len(islands),
        "title": _map_title(map_file, cities, masses),
        "masses": masses,
        "layout": layout,
    }


def _map_title(map_file: str, cities: list[dict], masses: Optional[list] = None) -> str:
    name = Path(map_file).stem.replace("_", " ").replace("-", " ").title()
    if masses is None:
        regions = sorted({c.get("region") for c in cities if c.get("region")})
        if len(regions) == 1:
            return f"{name} — {regions[0]}"
        if regions:
            return f"{name} — {len(regions)} regions"
        return name
    n = len(masses)
    islands = sum(1 for m in masses if m["kind"] == "island")
    if n == 1:
        return f"{name} — {masses[0]['name']}"
    if islands:
        return (
            f"{name} — {n} landmasses ({islands} island{'s' if islands != 1 else ''})"
        )
    return f"{name} — {n} landmasses"


def _chaikin(
    poly: list[list[float]] | list[tuple[float, float]],
    iterations: int = 2,
) -> list[tuple[float, float]]:
    """Corner-cut a closed ring (same smoothing as ``scripts/render_map.py``)."""
    pts: list[list[float]] = [[float(p[0]), float(p[1])] for p in poly]
    for _ in range(iterations):
        if len(pts) < 4:
            break
        smoothed: list[list[float]] = []
        for i, point in enumerate(pts):
            nxt = pts[(i + 1) % len(pts)]
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
        pts = smoothed
    return [(p[0], p[1]) for p in pts]


def _point_in_poly(x: float, y: float, poly: list) -> bool:
    """Ray-cast point-in-polygon (closed ring; last point need not repeat)."""
    n = len(poly)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi
        ):
            inside = not inside
        j = i
    return inside


def _dist_to_poly(mx: float, my: float, poly: list) -> float:
    """0 if inside; else min distance to any edge."""
    if _point_in_poly(mx, my, poly):
        return 0.0
    best = float("inf")
    n = len(poly)
    for i in range(n):
        x1, y1 = float(poly[i][0]), float(poly[i][1])
        x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            d = math.hypot(mx - x1, my - y1)
        else:
            t = max(
                0.0, min(1.0, ((mx - x1) * dx + (my - y1) * dy) / (dx * dx + dy * dy))
            )
            d = math.hypot(mx - (x1 + t * dx), my - (y1 + t * dy))
        if d < best:
            best = d
    return best


def _poly_area_miles(poly: list) -> float:
    """Absolute shoelace area in square miles."""
    n = len(poly)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n):
        x1, y1 = float(poly[i][0]), float(poly[i][1])
        x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
        acc += x1 * y2 - x2 * y1
    return abs(acc) * 0.5


def _disambiguate_names(masses: list[dict]) -> None:
    """No two landmasses may answer to the same name.

    A mass is named for the region most of its towns belong to, and a region
    can straddle water: on world2 the mainland and a one-town islet were both
    "Fenavale fold", so the roster listed the same place twice and a tooltip
    could not say which was meant. The largest keeps the bare name, since it
    is the one people mean; the rest are numbered in the order they are
    already sorted, largest first.
    """
    seen: dict[str, int] = {}
    for mass in masses:
        name = mass["name"]
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            mass["name"] = f"{name} {_ROMAN[min(seen[name], len(_ROMAN)) - 1]}"


_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def _majority_region(cities: list[dict], by_id: dict) -> Optional[str]:
    regions = [
        by_id[c].get("region") for c in cities if c in by_id and by_id[c].get("region")
    ]
    if not regions:
        return None
    return max(set(regions), key=regions.count)


def landmasses_from_geography(
    geo: dict,
    cities: list[dict],
    layout: MapLayout,
) -> list[dict]:
    """
    One landmass per traced coastline polygon (poster geography).

    Towns are assigned to the containing polygon, or the nearest edge when they
    sit just offshore (raster coastline vs gazetteer positions).
    """
    coastlines = geo.get("coastlines") or []
    by_id = {c["id"]: c for c in cities if c.get("id")}
    if not coastlines:
        return []

    # city_id -> coastline index
    assign: dict[str, int] = {}
    for c in cities:
        cid = c.get("id")
        if not cid:
            continue
        mx, my = city_miles(c, layout)
        best_i, best_d = 0, float("inf")
        for i, poly in enumerate(coastlines):
            d = _dist_to_poly(mx, my, poly)
            if d < best_d:
                best_d = d
                best_i = i
                if d == 0.0:
                    break
        assign[cid] = best_i

    masses: list[dict] = []
    for i, poly in enumerate(coastlines):
        cids = sorted(cid for cid, pi in assign.items() if pi == i)
        regions = [by_id[cid].get("region") for cid in cids if cid in by_id]
        regions = [r for r in regions if r]
        if regions:
            name = max(set(regions), key=regions.count)
        elif cids and cids[0] in by_id:
            name = by_id[cids[0]].get("name") or cids[0]
        else:
            name = f"Landmass {i + 1}"

        area = _poly_area_miles(poly)
        # Small land bodies read as islands; large ones as continents.
        kind = "island" if (len(cids) <= 8 or area < 12_000) else "continent"
        if "island" in name.lower():
            kind = "island"

        smoothed = _chaikin(poly)
        hull = [layout.project_miles(x, y) for x, y in smoothed]
        pts = [
            layout.project_miles(*city_miles(by_id[cid], layout))
            for cid in cids
            if cid in by_id
        ]
        masses.append(
            {
                "name": name,
                "kind": kind,
                "city_ids": cids,
                "city_names": [
                    by_id[cid].get("name") or cid for cid in cids if cid in by_id
                ],
                "points": pts,
                "hull": hull,
                "source": "geography",
                "area_miles": area,
            }
        )

    masses.sort(key=lambda m: (-len(m["city_ids"]), m["name"]))
    _disambiguate_names(masses)
    for i, m in enumerate(masses):
        m["index"] = i + 1
        m["fill"], m["stroke"] = _LAND_PALETTE[i % len(_LAND_PALETTE)]
    return masses


def compute_landmasses(
    cities: list[dict],
    roads: list[dict],
    pos: dict[str, tuple[float, float]],
) -> list[dict]:
    """
    Fallback landmasses from road connectivity (sea lanes do **not** join land).

    Used when no geography file is paired with the map (e.g. starter_map.json).
    Each entry: name, kind (continent|island), city_ids, city_names, points, hull.
    """
    by_id = {c["id"]: c for c in cities if c.get("id")}
    ids = [c["id"] for c in cities if c.get("id") in pos]
    if not ids:
        return []

    adj: dict[str, set[str]] = {cid: set() for cid in ids}
    for r in roads:
        if r.get("quality") == "sea":
            continue
        a, b = r.get("from"), r.get("to")
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)

    seen: set[str] = set()
    components: list[list[str]] = []
    for start in ids:
        if start in seen:
            continue
        stack = [start]
        comp: list[str] = []
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            comp.append(u)
            stack.extend(adj[u] - seen)
        components.append(sorted(comp))

    # Stable order: largest first, then name.
    masses: list[dict] = []
    for comp in components:
        pts = [pos[cid] for cid in comp if cid in pos]
        regions = [by_id[cid].get("region") for cid in comp if by_id.get(cid)]
        regions = [r for r in regions if r]
        if regions and len(set(regions)) == 1:
            name = regions[0]
        elif regions:
            name = max(set(regions), key=regions.count)
        elif len(comp) == 1:
            name = by_id[comp[0]].get("name") or comp[0]
        else:
            name = f"Landmass {len(masses) + 1}"

        kind = "island" if len(comp) == 1 else "continent"
        if "island" in name.lower():
            kind = "island"

        masses.append(
            {
                "name": name,
                "kind": kind,
                "city_ids": comp,
                "city_names": [
                    by_id[cid].get("name") or cid for cid in comp if cid in by_id
                ],
                "points": pts,
                "hull": _landmass_hull(pts),
                "source": "roads",
            }
        )

    masses.sort(key=lambda m: (-len(m["city_ids"]), m["name"]))
    _disambiguate_names(masses)
    for i, m in enumerate(masses):
        m["index"] = i + 1
        m["fill"], m["stroke"] = _LAND_PALETTE[i % len(_LAND_PALETTE)]
    return masses


def _landmass_hull(
    points: list[tuple[float, float]], pad: float = 72.0
) -> list[tuple[float, float]]:
    """Convex hull expanded outward for a readable shoreline confine."""
    if not points:
        return []
    if len(points) == 1:
        x, y = points[0]
        # Circular island confine.
        return [
            (x + pad * math.cos(t), y + pad * 0.78 * math.sin(t))
            for t in [i * 2 * math.pi / 16 for i in range(16)]
        ]
    hull = _convex_hull(points)
    if len(hull) == 2:
        (x1, y1), (x2, y2) = hull
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length * pad, dx / length * pad
        ux, uy = dx / length * pad * 0.55, dy / length * pad * 0.55
        return [
            (x1 - ux + nx, y1 - uy + ny),
            (x2 + ux + nx, y2 + uy + ny),
            (x2 + ux - nx, y2 + uy - ny),
            (x1 - ux - nx, y1 - uy - ny),
        ]
    cx = sum(p[0] for p in hull) / len(hull)
    cy = sum(p[1] for p in hull) / len(hull)
    out: list[tuple[float, float]] = []
    for x, y in hull:
        dx, dy = x - cx, y - cy
        dist = math.hypot(dx, dy) or 1.0
        out.append((x + pad * dx / dist, y + pad * dy / dist))
    return out


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain; returns CCW hull without repeating first point."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# Faction colours for the in-game overlay. Distinct hues that read against the
# parchment/sea palette and stay apart for the common red/green colour blindness.
FACTION_COLORS = [
    "#d4553f",  # vermilion
    "#4a90d9",  # steel blue
    "#c9a24b",  # gold
    "#8a6fc4",  # violet
    "#3f9e83",  # teal
    "#c96fa8",  # rose
]


def faction_color(slot: int) -> str:
    return FACTION_COLORS[slot % len(FACTION_COLORS)]


def render_svg(map_file: str, overlay: Optional[dict] = None) -> str:
    """
    Full map SVG with landmass confines, roads, cities (crisp, no blur filters).

    With an `overlay` from ``service.map_overlay`` the same map becomes the
    live board: who holds which city, where this player's own people stand,
    and nothing about ground the player cannot see.

    Dense maps (dozens/hundreds of cities) auto-declutter: only major names
    stay on permanently, the rest appear on hover, and road mile labels move
    into tooltips so the board stays readable.

    When geography is present, land is the traced coastlines from
    ``soe_geography.json`` and the viewBox matches the field aspect so the
    whole world fits without clipping or forced panning.
    """
    data = load_raw_map(map_file)
    stats = map_stats(map_file)
    layout: MapLayout = stats["layout"]
    pos = positions(map_file)
    cities = data.get("cities") or []
    roads = data.get("roads") or []
    by_id = {c["id"]: c for c in cities}
    masses = stats["masses"]
    marks = (overlay or {}).get("cities") or {}
    dense = len(cities) >= _DENSE_CITY_COUNT
    density = _density_class(len(cities))
    geo_class = " soe-map-geo" if layout.has_geography else ""

    w, h = layout.width, layout.height
    parts: list[str] = []
    parts.append(
        f'<svg class="soe-map soe-map-{density}{geo_class}" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'width="{w:.0f}" height="{h:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'shape-rendering="geometricPrecision" text-rendering="geometricPrecision" '
        f'aria-label="{_esc(stats["title"])}">'
    )
    parts.append(_defs())
    parts.append(_background(layout))
    geo = load_geography(map_file)
    parts.append(
        _landmasses_svg(
            masses, dense=dense, traced=layout.has_geography, frame_w=layout.width
        )
    )
    parts.append(_terrain_svg(geo, layout))
    parts.append(_compass(w - 48, h - 48))
    # The roster only exists on sparse maps; its panel is what the bar clears.
    roster_h = 0.0 if dense else (len(masses) * 18 + 36 + 14)
    parts.append(_scale_bar(layout, reserved_bottom=roster_h))
    parts.append(_title_block(stats, dense=dense))
    # On-map landmass roster only for small maps; dense maps use the HTML index.
    if not dense:
        parts.append(_island_index_svg(masses, layout))
    if overlay:
        parts.append(_overlay_key_svg(overlay))

    parts.append('<g class="map-routes">')
    sea_routes = (geo or {}).get("sea_routes") or {}
    for r in roads:
        a, b = pos.get(r.get("from")), pos.get(r.get("to"))
        if not a or not b:
            continue
        sailed = sea_routes.get(r.get("id"))
        parts.append(
            _route_svg(
                r, a, b, dense=dense,
                sailed=(
                    [layout.project_miles(px, py) for px, py in sailed]
                    if sailed else None
                ),
            )
        )
    parts.append("</g>")

    parts.append('<g class="map-cities">')
    label_plan = _plan_city_labels(cities, pos)
    ordered = sorted(
        pos.items(),
        key=lambda item: (
            -_BAND_RADIUS.get(by_id.get(item[0], {}).get("population_band"), 8)
        ),
    )
    for cid, (x, y) in ordered:
        city = by_id.get(cid)
        if not city:
            continue
        plan = label_plan.get(cid) or _default_label_plan(city, dense)
        parts.append(_city_svg(city, x, y, marks.get(cid), plan))
    parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def _density_class(city_count: int) -> str:
    if city_count >= _VERY_DENSE_CITY_COUNT:
        return "very-dense"
    if city_count >= _DENSE_CITY_COUNT:
        return "dense"
    return "sparse"


@dataclass(frozen=True)
class CityLabelPlan:
    """How a city is labelled on the SVG."""

    name_mode: str = "always"  # always | hover | never
    meta_mode: str = "always"  # always | hover | never
    name_size: float = 15.0
    radius_scale: float = 1.0
    show_rings: bool = True
    # Label anchor relative to the city marker (0, negative = above).
    label_dx: float = 0.0
    label_dy: float = -10.0
    # Optional shorter display string when the full name would not fit.
    display_name: Optional[str] = None
    # text-anchor for the label (middle | start | end).
    text_anchor: str = "middle"


def _default_label_plan(city: dict, dense: bool) -> CityLabelPlan:
    if not dense:
        return CityLabelPlan()
    band = city.get("population_band") or ""
    rank = _BAND_RANK.get(band, 1)
    size = {4: 11.0, 3: 9.5, 2: 8.5}.get(rank, 7.5)
    return CityLabelPlan(
        name_mode="always",
        meta_mode="hover",
        name_size=size,
        radius_scale=0.48 if rank >= 3 else 0.4,
        show_rings=rank >= 3,
        label_dy=-(size + 4),
    )


def _city_priority(city: dict) -> tuple:
    """Higher first: large populations, ports, named capitals."""
    band = city.get("population_band") or "10k-99k"
    pop = city.get("population")
    try:
        pop_n = int(pop) if pop is not None else 0
    except (TypeError, ValueError):
        pop_n = 0
    return (
        _BAND_RANK.get(band, 0),
        1 if city.get("is_port") else 0,
        pop_n,
        -(len(str(city.get("name") or ""))),  # shorter names slightly preferred
    )


def _short_city_name(name: str, max_len: int = 12) -> str:
    """Compress a long gazetteer name for a tight label slot."""
    name = (name or "").strip()
    if len(name) <= max_len:
        return name
    # Prefer first token if it's still informative (e.g. "Al Katib" → "Al Katib"
    # already short; "Highfell" stays; "Something Very Long" → first word).
    parts = name.replace("-", " ").split()
    if len(parts) >= 2:
        first_two = f"{parts[0]} {parts[1]}"
        if len(first_two) <= max_len:
            return first_two
        if len(parts[0]) <= max_len:
            return parts[0]
    if len(name) > max_len:
        return name[: max_len - 1] + "…"
    return name


def _label_box_at(
    lx: float,
    ly: float,
    name: str,
    font_size: float,
    anchor: str = "middle",
) -> tuple[float, float, float, float]:
    """Axis-aligned box for a label whose baseline is at (lx, ly)."""
    # ~0.52em average glyph width for Georgia-ish faces at small sizes.
    w = max(14.0, len(name) * font_size * 0.52)
    h = font_size + 3.0
    if anchor == "start":
        left = lx
    elif anchor == "end":
        left = lx - w
    else:
        left = lx - w / 2
    # Baseline ≈ 0.8 of em from top of ink.
    top = ly - font_size * 0.85
    return (left, top, left + w, top + h)


def _boxes_overlap(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    pad: float = 2.0,
) -> bool:
    return not (
        a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1]
    )


def _label_candidates(
    x: float, y: float, radius: float, font_size: float
) -> list[tuple[float, float, str]]:
    """(label_x, label_y, text_anchor) slots around a marker, preferred first."""
    gap = max(3.0, font_size * 0.35)
    r = radius + gap
    return [
        (x, y - r - font_size * 0.15, "middle"),  # above
        (x, y + r + font_size * 0.75, "middle"),  # below
        (x + r + 2, y + font_size * 0.3, "start"),  # right
        (x - r - 2, y + font_size * 0.3, "end"),  # left
        (x + r * 0.7, y - r * 0.7 - font_size * 0.1, "start"),  # NE
        (x - r * 0.7, y - r * 0.7 - font_size * 0.1, "end"),  # NW
        (x + r * 0.7, y + r * 0.7 + font_size * 0.55, "start"),  # SE
        (x - r * 0.7, y + r * 0.7 + font_size * 0.55, "end"),  # SW
    ]


def _font_for_band(band: str, dense: bool, very_dense: bool) -> float:
    if not dense:
        return 15.0
    rank = _BAND_RANK.get(band, 1)
    if very_dense:
        return {4: 10.5, 3: 9.0, 2: 7.8, 1: 7.0}.get(rank, 7.0)
    return {4: 12.0, 3: 10.5, 2: 9.0, 1: 8.0}.get(rank, 8.0)


def _plan_city_labels(
    cities: list[dict], pos: dict[str, tuple[float, float]]
) -> dict[str, CityLabelPlan]:
    """
    Place a permanent name on every city.

    Sparse maps: large labels + meta under the marker.
    Dense maps: tiered font sizes, multi-slot collision resolution, short
    names when the full string will not fit. Meta (pop/grid) stays hover-only
    so the board stays a map of named towns, not a wall of stats.
    """
    n = len(cities)
    dense = n >= _DENSE_CITY_COUNT
    very_dense = n >= _VERY_DENSE_CITY_COUNT
    radius_scale = 1.0 if not dense else (0.40 if very_dense else 0.50)

    ranked = sorted(cities, key=_city_priority, reverse=True)
    plan: dict[str, CityLabelPlan] = {}
    placed_boxes: list[tuple[float, float, float, float]] = []
    # Reserve space around every marker so labels don't sit on other dots.
    for city in cities:
        cid = city.get("id")
        if not cid or cid not in pos:
            continue
        x, y = pos[cid]
        band = city.get("population_band") or "10k-99k"
        r = max(3.0, _BAND_RADIUS.get(band, 8.5) * radius_scale)
        placed_boxes.append((x - r, y - r, x + r, y + r))

    for city in ranked:
        cid = city.get("id")
        if not cid or cid not in pos:
            continue
        x, y = pos[cid]
        band = city.get("population_band") or "10k-99k"
        base_r = max(3.0, _BAND_RADIUS.get(band, 8.5) * radius_scale)
        full_name = str(city.get("name") or cid)
        font = _font_for_band(band, dense, very_dense)
        rings = (not dense) or _BAND_RANK.get(band, 0) >= 3

        if not dense:
            plan[cid] = CityLabelPlan(
                name_mode="always",
                meta_mode="always",
                name_size=font,
                radius_scale=1.0,
                show_rings=True,
                label_dx=0.0,
                label_dy=-(base_r + 10),
                display_name=full_name,
                text_anchor="middle",
            )
            # Still track the box so dense path isn't the only one that cares.
            box = _label_box_at(x, y - base_r - 10, full_name, font, "middle")
            placed_boxes.append(box)
            continue

        # Dense: try full name at several slots, then a shortened form.
        placed = False
        for use_name, use_font in (
            (full_name, font),
            (_short_city_name(full_name, 14), font),
            (_short_city_name(full_name, 10), max(6.5, font - 1.0)),
            (_short_city_name(full_name, 8), max(6.0, font - 1.5)),
        ):
            for lx, ly, anchor in _label_candidates(x, y, base_r, use_font):
                box = _label_box_at(lx, ly, use_name, use_font, anchor)
                if any(_boxes_overlap(box, other, pad=1.2) for other in placed_boxes):
                    continue
                plan[cid] = CityLabelPlan(
                    name_mode="always",
                    meta_mode="hover",
                    name_size=use_font,
                    radius_scale=radius_scale,
                    show_rings=rings,
                    label_dx=lx - x,
                    label_dy=ly - y,
                    display_name=use_name,
                    text_anchor=anchor,
                )
                placed_boxes.append(box)
                placed = True
                break
            if placed:
                break

        if not placed:
            # Last resort: always show a tiny name above; slight opacity via size.
            tiny = max(6.0, font - 2.0)
            short = _short_city_name(full_name, 8)
            plan[cid] = CityLabelPlan(
                name_mode="always",
                meta_mode="hover",
                name_size=tiny,
                radius_scale=radius_scale * 0.95,
                show_rings=False,
                label_dx=0.0,
                label_dy=-(base_r + tiny * 0.9),
                display_name=short,
                text_anchor="middle",
            )
            box = _label_box_at(x, y - (base_r + tiny * 0.9), short, tiny, "middle")
            placed_boxes.append(box)

    return plan


def render_map_fragment(map_file: str, overlay: Optional[dict] = None) -> str:
    """SVG + HTML island index for HTMX swaps."""
    return (
        f'<div class="map-panel-inner">'
        f"{render_svg(map_file, overlay)}"
        f"{islands_html(map_file)}"
        f"</div>"
    )


def islands_html(map_file: str) -> str:
    """HTML roster: how many landmasses/islands and which cities each confines."""
    stats = map_stats(map_file)
    masses = stats["masses"]
    if not masses:
        return '<div class="island-index muted">No landmasses on this map.</div>'
    rows = []
    for m in masses:
        kind = m["kind"]
        n = len(m["city_ids"])
        names = list(m["city_names"])
        # Dense continents list hundreds of towns — show a sample, not a wall.
        if n > 14:
            shown = ", ".join(names[:10])
            cities = f"{shown}, … (+{n - 10} more)"
        else:
            cities = ", ".join(names)
        rows.append(
            f'<li class="island-row kind-{_esc(kind)}">'
            f'<span class="island-swatch" style="background:{m["fill"]};border-color:{m["stroke"]}"></span>'
            f'<span class="island-name">{_esc(m["name"])}</span>'
            f'<span class="island-kind">{kind}</span>'
            f'<span class="island-cities">{n} cit{"ies" if n != 1 else "y"}: {_esc(cities)}</span>'
            f"</li>"
        )
    n_islands = stats["islands"]
    summary = (
        f"{stats['landmasses']} landmass"
        f"{'es' if stats['landmasses'] != 1 else ''}"
        f" · {n_islands} island{'s' if n_islands != 1 else ''}"
        f" (sea lanes do not join land)"
    )
    return (
        f'<div class="island-index" aria-label="Landmasses and islands">'
        f'<div class="legend-title">Landmasses</div>'
        f'<p class="island-summary muted">{_esc(summary)}</p>'
        f'<ol class="island-list">{"".join(rows)}</ol>'
        f"</div>"
    )


def legend_svg() -> str:
    """Compact SVG legend (kept for callers that still embed it).

    Read out of `_ROAD_STYLES` rather than restated. A legend is a promise
    about the map, and the only way to keep it is to not have a second copy
    of the palette to forget.
    """
    items = [
        (_ROAD_STYLES[quality][0], _ROAD_STYLES[quality][2], label)
        for quality, label in (
            (RoadQuality.EXCELLENT, "excellent"),
            (RoadQuality.GOOD, "good"),
            (RoadQuality.FAIR, "fair"),
            (RoadQuality.POOR, "poor"),
            (RoadQuality.SEA, "sea lane"),
        )
    ]
    parts = [
        '<svg class="legend-svg" width="220" height="210" viewBox="0 0 220 210" '
        'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    ]
    parts.append(
        '<text x="4" y="12" fill="#7f8794" font-size="9.5" letter-spacing="1.2">'
        "ROUTES</text>"
    )
    for i, (color, dash, label) in enumerate(items):
        y = 28 + i * 18
        parts.append(
            f'<line x1="6" y1="{y}" x2="44" y2="{y}" stroke="{color}" stroke-width="3" '
            f'stroke-dasharray="{dash}" stroke-linecap="round"/>'
        )
        parts.append(
            f'<text x="54" y="{y + 4}" fill="#9aa7b8" font-size="11">{label}</text>'
        )

    y_mf = 28 + 5 * 18 + 6
    parts.append(
        f'<circle cx="24" cy="{y_mf}" r="7" fill="none" stroke="#a06ee0" '
        f'stroke-width="1.5" stroke-dasharray="3 3"/>'
    )
    parts.append(
        f'<text x="54" y="{y_mf + 4}" fill="#9aa7b8" font-size="11">magic-free</text>'
    )
    y_port = y_mf + 18
    parts.append(
        f'<path d="M 16 {y_port + 4} a 10 10 0 0 1 16 0" fill="none" '
        f'stroke="#5ba7d0" stroke-width="1.5"/>'
    )
    parts.append(
        f'<text x="54" y="{y_port + 4}" fill="#9aa7b8" font-size="11">port</text>'
    )

    y0 = y_port + 28
    parts.append(
        f'<text x="4" y="{y0 - 8}" fill="#7f8794" font-size="9.5" letter-spacing="1.2">'
        "CITY SIZE</text>"
    )
    bands = [
        ("&lt;1k", 5.5, "#7a8494"),
        ("1k–9k", 7.5, "#b0bac8"),
        ("10k–99k", 10, "#e0d4b8"),
        ("100k+", 13, "#d4a84a"),
    ]
    for i, (label, radius, color) in enumerate(bands):
        x = 18 + i * 50
        y = y0 + 10
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}" '
            f'stroke="#10131a" stroke-width="1.8"/>'
        )
        parts.append(
            f'<text x="{x}" y="{y + 24}" fill="#7f8794" font-size="8.5" '
            f'text-anchor="middle">{label}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def legend_html() -> str:
    """HTML legend for the landing page (richer than the SVG strip)."""
    return """
<div class="map-legend" aria-label="Map legend">
  <div class="legend-col">
    <div class="legend-title">Routes</div>
    <div class="legend-row"><span class="swatch road excellent"></span> excellent</div>
    <div class="legend-row"><span class="swatch road good"></span> good</div>
    <div class="legend-row"><span class="swatch road fair"></span> fair</div>
    <div class="legend-row"><span class="swatch road poor"></span> poor</div>
    <div class="legend-row"><span class="swatch road sea"></span> sea lane</div>
  </div>
  <div class="legend-col">
    <div class="legend-title">Places</div>
    <div class="legend-row"><span class="swatch city tiny"></span> &lt;1k</div>
    <div class="legend-row"><span class="swatch city small"></span> 1k–9k</div>
    <div class="legend-row"><span class="swatch city medium"></span> 10k–99k</div>
    <div class="legend-row"><span class="swatch city large"></span> 100k+</div>
    <div class="legend-row"><span class="swatch magic"></span> magic-free</div>
    <div class="legend-row"><span class="swatch port"></span> port</div>
    <div class="legend-row"><span class="swatch ruin"></span> ruin</div>
  </div>
  <div class="legend-col">
    <div class="legend-title">Land</div>
    <div class="legend-row"><span class="swatch land continent"></span> continent</div>
    <div class="legend-row"><span class="swatch land island"></span> island</div>
    <div class="legend-row muted" style="font-size:0.75rem;max-width:11rem">
      Sea lanes never join landmasses.
    </div>
  </div>
</div>
""".strip()


# ---------------------------------------------------------------------------
# SVG building blocks
# ---------------------------------------------------------------------------


def _defs() -> str:
    # No Gaussian blur filters — they make the whole map look soft when scaled.
    return """
<defs>
  <linearGradient id="mapSea" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#0f1824"/>
    <stop offset="100%" stop-color="#0a1018"/>
  </linearGradient>
  <pattern id="mapGrid" width="48" height="48" patternUnits="userSpaceOnUse">
    <path d="M 48 0 L 0 0 0 48" fill="none" stroke="#243040" stroke-width="0.75" opacity="0.5"/>
  </pattern>
  <style type="text/css"><![CDATA[
    .soe-map { shape-rendering: geometricPrecision; text-rendering: geometricPrecision; }
    .soe-map .map-route { transition: opacity 0.12s ease; }
    .soe-map .map-city-hit { cursor: pointer; }
    .soe-map .map-city-hit:hover .city-core { stroke: #f0ebe0; stroke-width: 2.6; }
    .soe-map .map-city-hit:hover .city-name { fill: #fff8e8; }
    /* Dense-map declutter: secondary labels appear only on hover. */
    .soe-map .city-label-hover,
    .soe-map .city-meta-hover {
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.1s ease;
    }
    .soe-map .map-city-hit:hover .city-label-hover,
    .soe-map .map-city-hit:hover .city-meta-hover,
    .soe-map .map-city-hit:focus-within .city-label-hover,
    .soe-map .map-city-hit:focus-within .city-meta-hover {
      opacity: 1;
    }
    /* Re-paint hovered city last among peers (SVG paint order ~ DOM order;
       use a filter-free scale so the name is legible over the tangle). */
    .soe-map .map-city-hit:hover .city-label-hover,
    .soe-map .map-city-hit:hover .city-name-always {
      stroke: #0c0e14;
      stroke-width: 3.2px;
    }
    .soe-map.soe-map-dense .map-routes,
    .soe-map.soe-map-very-dense .map-routes { opacity: 0.72; }
    .soe-map.soe-map-dense .land-label,
    .soe-map.soe-map-very-dense .land-label { opacity: 0.38; }
    .soe-map.soe-map-dense .land-label-meta,
    .soe-map.soe-map-very-dense .land-label-meta { opacity: 0.28; }
    .soe-map .map-landmass:hover .land-shore { stroke-width: 2.4; opacity: 1; }
    .soe-map .map-title { font-family: Georgia, "Times New Roman", serif; }
    .soe-map .map-label { font-family: Georgia, "Times New Roman", serif; }
    .soe-map .map-meta { font-family: ui-monospace, Consolas, monospace; }
    .soe-map .land-label { opacity: 0.55; pointer-events: none; }
    .soe-map .land-label-meta { opacity: 0.4; pointer-events: none; }
  ]]></style>
</defs>
""".strip()


def _background(layout: MapLayout) -> str:
    w, h = layout.width, layout.height
    return f"""
<g class="map-bg" aria-hidden="true">
  <rect width="{w:.0f}" height="{h:.0f}" fill="url(#mapSea)"/>
  <rect width="{w:.0f}" height="{h:.0f}" fill="url(#mapGrid)"/>
  <rect x="1" y="1" width="{w - 2:.0f}" height="{h - 2:.0f}"
        fill="none" stroke="#3a4252" stroke-width="1.5"/>
</g>
""".strip()


def _title_block(stats: dict, dense: bool = False) -> str:
    bits = [f"{stats['cities']} cities"]
    if stats.get("landmasses"):
        bits.append(f"{stats['landmasses']} landmasses")
    if stats.get("islands"):
        bits.append(f"{stats['islands']} island{'s' if stats['islands'] != 1 else ''}")
    if stats["roads"]:
        bits.append(f"{stats['roads']} roads")
    if stats["sea_lanes"]:
        bits.append(f"{stats['sea_lanes']} sea lanes")
    if stats["ports"]:
        bits.append(f"{stats['ports']} ports")
    meta = " · ".join(bits)
    hint = ""
    if dense:
        hint = (
            '<text class="map-meta" x="32" y="80" fill="#5a6270" font-size="11">'
            "Every town is named — hover for population, grid and terrain"
            "</text>"
        )
    return f"""
<g class="map-chrome" aria-hidden="true">
  <text class="map-title" x="32" y="40" fill="#e8e4d8" font-size="22" font-weight="bold"
        letter-spacing="0.4">{_esc(stats["title"])}</text>
  <text class="map-meta" x="32" y="62" fill="#6d7584" font-size="13">{_esc(meta)}</text>
  {hint}
</g>
""".strip()


def _compass(cx: float, cy: float) -> str:
    return f"""
<g class="map-compass" transform="translate({cx:.1f},{cy:.1f})" opacity="0.7" aria-hidden="true">
  <circle r="32" fill="#12161e" stroke="#3a4252" stroke-width="1.25"/>
  <circle r="24" fill="none" stroke="#2e3644" stroke-width="1"/>
  <path d="M0,-20 L5,0 L0,5 L-5,0 Z" fill="#c9a24b"/>
  <path d="M0,20 L5,0 L0,-5 L-5,0 Z" fill="#5a6270"/>
  <text x="0" y="-36" text-anchor="middle" fill="#9aa7b8" font-size="11"
        font-family="Georgia, serif">N</text>
</g>
""".strip()


#: Bar lengths worth printing, in miles. A scale bar is read by its number,
#: so the number has to be one a person holds in their head while looking
#: somewhere else -- never 137 miles because that was 15% of the frame.
_SCALE_STEPS = (50, 100, 200, 250, 500, 1000)


def scale_bar_miles(layout: MapLayout, target_fraction: float = 0.16) -> int:
    """The roundest bar length that lands near `target_fraction` of the map."""
    want = layout.field_w_mi * target_fraction
    return min(_SCALE_STEPS, key=lambda step: abs(step - want))


def _scale_bar(layout: MapLayout, reserved_bottom: float = 0.0) -> str:
    """A cartographic scale bar, in the units the engine prices travel in.

    The map has always been drawn to scale -- towns carry mile coordinates and
    routes are priced in miles -- and has never said so, which left every
    distance on it unreadable. Alternating segments rather than a plain rule,
    because that is what lets someone step a distance off by eye.

    Only drawn with geography, where the viewBox really is the mile field.
    Without it the frame is nominal and a bar would be a measurement invented
    for the occasion.
    """
    if not layout.has_geography or not layout.field_w_mi:
        return ""

    miles = scale_bar_miles(layout)
    units_per_mile = layout.map_w / layout.field_w_mi
    length = miles * units_per_mile
    segments = 4
    seg = length / segments
    height = 7.0

    x = layout.pad_x + 18
    # The landmass roster is drawn in this same corner on sparse maps, so the
    # bar steps up over whatever it occupies rather than through it.
    y = layout.pad_y + layout.map_h - 26 - reserved_bottom

    parts = [
        f'<g class="map-scale" aria-label="Scale bar: {miles} miles" '
        f'transform="translate({x:.1f},{y:.1f})">'
    ]
    parts.append(
        f'<rect x="-6" y="-19" width="{length + 12:.1f}" height="{height + 30:.1f}" '
        f'rx="3" fill="#0e1118" fill-opacity="0.62" stroke="#2e3644" stroke-width="0.8"/>'
    )
    for i in range(segments):
        fill = "#e8dcc2" if i % 2 == 0 else "#2a3140"
        parts.append(
            f'<rect x="{i * seg:.1f}" y="0" width="{seg:.1f}" height="{height:.1f}" '
            f'fill="{fill}" stroke="#e8dcc2" stroke-width="0.8"/>'
        )
    for i in (0, segments // 2, segments):
        label = int(miles * i / segments)
        parts.append(
            f'<text x="{i * seg:.1f}" y="-5" text-anchor="middle" fill="#c8cedb" '
            f'font-size="9.5" font-family="Georgia, serif">{label}</text>'
        )
    parts.append(
        f'<text x="{length / 2:.1f}" y="{height + 11:.1f}" text-anchor="middle" '
        f'fill="#8d97a8" font-size="8.5" letter-spacing="1.1">MILES</text>'
    )
    parts.append("</g>")
    return "\n".join(parts)


def _poly_path(pts: list[tuple[float, float]]) -> str:
    if not pts:
        return ""
    cmds = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for x, y in pts[1:]:
        cmds.append(f"L {x:.1f} {y:.1f}")
    cmds.append("Z")
    return " ".join(cmds)


#: Hypsometric tinting, the relief-map convention: lowland green through
#: upland ochre to bare rock, with arid gold and wetland grey-green off to the
#: side. Kept dark enough that roads, sea lanes and town marks stay the
#: brightest things on the board -- terrain is the ground the game is played
#: on, not the subject.
TERRAIN_FILL = {
    "plain": "#4f5f3c",
    "forest": "#33502f",
    "hills": "#6d6640",
    "mountains": "#6f6d68",
    "desert": "#8a7b4f",
    "swamp": "#3f5148",
}

LAKE_FILL = "#24435c"


def _terrain_svg(geo: Optional[dict], layout: MapLayout) -> str:
    """Terrain regions and inland water, painted over the landmass bodies.

    Without this the land is one flat fill per landmass, which is the whole
    map saying one thing: there is land here. The generator has known which
    kind of land since it placed the towns -- the towns are biased by it --
    and the sidecar carries the regions, so the map can finally show the
    ground a doctrine is arguing about.

    Drawn as outlines only. A hole in a terrain region is another terrain,
    which paints its own outline over it, or a lake, which is painted last.
    """
    if not geo:
        return ""
    parts = ['<g class="map-terrain" aria-hidden="true">']
    for kind, fill in TERRAIN_FILL.items():
        polys = (geo.get("terrain") or {}).get(kind) or []
        if not polys:
            continue
        paths = " ".join(
            _poly_path([layout.project_miles(px, py) for px, py in poly])
            for poly in polys
            if len(poly) >= 3
        )
        if paths:
            # A hairline edge in the region's own shadow. Without it two
            # adjacent greens meet on a colour change alone and the map reads
            # as camouflage; with it each region is a place with a border.
            parts.append(
                f'<path class="terrain-{kind}" d="{paths}" fill="{fill}" '
                f'fill-opacity="0.88" stroke="#161a12" stroke-width="0.7" '
                f'stroke-opacity="0.35" stroke-linejoin="round"/>'
            )
    for lake in geo.get("lakes") or []:
        if len(lake) < 3:
            continue
        path = _poly_path([layout.project_miles(px, py) for px, py in lake])
        parts.append(
            f'<path class="terrain-lake" d="{path}" fill="{LAKE_FILL}" '
            f'stroke="#8fb6cd" stroke-width="0.9" stroke-opacity="0.5"/>'
        )
    parts.append("</g>")
    return "\n".join(parts) if len(parts) > 2 else ""


def _polygon_centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    """Area centroid, which for a landmass is a point on the landmass.

    The mean of the vertices is not: it is pulled wherever the outline has the
    most detail, which on a traced coast is the fiddliest stretch of shore.
    """
    area = 0.0
    cx = 0.0
    cy = 0.0
    for i, (x1, y1) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area) < 1e-9:
        n = len(pts) or 1
        return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    area *= 0.5
    return cx / (6 * area), cy / (6 * area)


def _landmasses_svg(
    masses: list[dict],
    dense: bool = False,
    traced: bool = False,
    frame_w: float = 1e9,
) -> str:
    if not masses:
        return ""
    parts = ['<g class="map-landmasses">']
    name_size = 11 if dense else 13
    for m in masses:
        hull = m.get("hull") or []
        if len(hull) < 3:
            continue
        path = _poly_path(hull)
        cx, cy_mass = _polygon_centroid(hull)
        n = len(m["city_ids"])
        name_list = list(m["city_names"])
        if dense and n > 12:
            tip_cities = ", ".join(name_list[:8]) + f", … (+{n - 8} more)"
        else:
            tip_cities = ", ".join(name_list)
        tip = _esc(
            f"{m['name']} ({m['kind']}) — {n} cit{'ies' if n != 1 else 'y'}: "
            + tip_cities
        )
        parts.append(
            f'<g class="map-landmass kind-{_esc(m["kind"])}" '
            f'data-landmass="{_esc(m["name"])}">'
        )
        parts.append(f"<title>{tip}</title>")
        parts.append(
            f'<path class="land-body" d="{path}" fill="{m["fill"]}" fill-opacity="0.90" '
            f'stroke="none"/>'
        )
        # Traced coastlines already are the shore; hull confines get a soft ring.
        shore_w = 1.4 if traced else 1.8
        parts.append(
            f'<path class="land-shore" d="{path}" fill="none" stroke="{m["stroke"]}" '
            f'stroke-width="{shore_w}" stroke-linejoin="round" opacity="0.95"/>'
        )
        if not traced:
            parts.append(
                f'<path class="land-confine" d="{path}" fill="none" stroke="{m["stroke"]}" '
                f'stroke-width="1" stroke-dasharray="6 5" opacity="0.45"/>'
            )
        # A landmass caption is set across the body of the land it names, so
        # it only works when the land is wide enough to seat it. Drawn
        # regardless, it ran off the frame -- ZELANSTEAD HINTERLAND was
        # clipped mid-word -- and lay across open sea on the small masses.
        caption = m["name"].upper()
        hull_left = min(p[0] for p in hull)
        hull_right = max(p[0] for p in hull)
        # Set as large as the land allows, down to a floor, then give up: a
        # caption smaller than this is unreadable anyway, and an islet does
        # not need its name written across it.
        per_char = 0.96  # glyph width plus tracking, in ems
        room = (hull_right - hull_left) * 0.86
        caption_size = min(name_size * 1.25, room / max(1, len(caption)) / per_char)
        text_w = len(caption) * caption_size * per_char
        if caption_size >= 7.5:
            # Set across the body of the land, not along its northern edge:
            # the top of a hull is the sea above the widest point, and the
            # caption floated there with half of it over open water.
            label_y = cy_mass + caption_size * 0.35
            # Keep it over its own land, and inside the frame whatever the
            # centroid says.
            label_x = min(
                max(cx, hull_left + text_w / 2, text_w / 2 + 8),
                hull_right - text_w / 2,
                frame_w - text_w / 2 - 8,
            )
            # Quiet engraved type, the same on every terrain. Inheriting the
            # shore colour left it a smudge on green and a shout on grey.
            parts.append(
                f'<text class="map-label land-label" x="{label_x:.1f}" y="{label_y:.1f}" '
                f'text-anchor="middle" fill="#f4ecda" fill-opacity="0.42" '
                f'stroke="#10140e" stroke-opacity="0.38" '
                f'stroke-width="{caption_size * 0.16:.2f}" paint-order="stroke" '
                f'font-size="{caption_size:.1f}" '
                f'letter-spacing="{caption_size * 0.34:.1f}" font-weight="bold">'
                f"{_esc(caption)}</text>"
            )
            if not dense:
                parts.append(
                    f'<text class="map-meta land-label-meta" x="{label_x:.1f}" '
                    f'y="{label_y + 15:.1f}" '
                    f'text-anchor="middle" fill="#7f8794" font-size="10">'
                    f"{m['kind']} · {n} cit{'ies' if n != 1 else 'y'}</text>"
                )
        parts.append("</g>")
    parts.append("</g>")
    return "\n".join(parts)


def _island_index_svg(masses: list[dict], layout: MapLayout) -> str:
    """Compact roster drawn on the map (always visible without HTML)."""
    if not masses:
        return ""
    x0, y0 = 28.0, layout.height - 28 - (len(masses) * 18 + 36)
    parts = [
        '<g class="map-island-roster" aria-hidden="true">',
        f'<rect x="{x0 - 10}" y="{y0 - 8}" width="320" height="{len(masses) * 18 + 36}" '
        f'rx="6" fill="#0c1016" fill-opacity="0.82" stroke="#333947" stroke-width="1"/>',
        f'<text x="{x0}" y="{y0 + 10}" fill="#7f8794" font-size="11" class="map-meta" '
        f'letter-spacing="1.2">LANDMASSES ({len(masses)})</text>',
    ]
    for i, m in enumerate(masses):
        y = y0 + 28 + i * 18
        parts.append(
            f'<rect x="{x0}" y="{y - 8}" width="12" height="12" rx="2" '
            f'fill="{m["fill"]}" stroke="{m["stroke"]}" stroke-width="1.2"/>'
        )
        line = (
            f"{m['index']}. {m['name']} — {m['kind']} — "
            f"{len(m['city_ids'])} cit{'ies' if len(m['city_ids']) != 1 else 'y'}"
        )
        parts.append(
            f'<text x="{x0 + 18}" y="{y + 2}" fill="#b8c2d0" font-size="12" '
            f'class="map-meta">{_esc(line)}</text>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def _hop_cost_for_raw_road(road: dict) -> Optional[float]:
    """Movement points to cross this route (same formula as the engine)."""
    try:
        quality = RoadQuality(road.get("quality"))
    except (KeyError, ValueError, TypeError):
        return None
    miles = road.get("distance_miles")
    try:
        miles_f = float(miles) if miles is not None else None
    except (TypeError, ValueError):
        miles_f = None
    model = Road(
        id=str(road.get("id") or "r"),
        from_city_id=str(road.get("from") or ""),
        to_city_id=str(road.get("to") or ""),
        quality=quality,
        distance_miles=miles_f,
    )
    return get_hop_cost(model)


def _format_hop(cost: Optional[float]) -> str:
    if cost is None:
        return ""
    if abs(cost - round(cost)) < 1e-6:
        return f"{int(round(cost))} mv"
    return f"{cost:.1f} mv"


def _sailed_route_svg(
    road: dict,
    points: list[tuple[float, float]],
    color: str,
    width: float,
    dash: str,
) -> str:
    """One sea lane drawn along the water it actually sails through."""
    d = " ".join(
        ("M" if i == 0 else "L") + f" {x:.1f} {y:.1f}" for i, (x, y) in enumerate(points)
    )
    rid = _esc(str(road.get("id", "")))
    miles = road.get("distance_miles")
    title_bits = ["sea lane"]
    if miles is not None and miles != "":
        # The crossing is priced on the straight line; the drawn path is the
        # water it has to keep to, so the two are not the same length and the
        # tooltip says which number is which.
        title_bits.append(f"{miles} mi as the crow flies")
    return (
        f'<g class="map-route map-route-sea" data-road="{rid}">'
        f"<title>{_esc(' · '.join(title_bits))}</title>"
        f'<path d="{d}" fill="none" stroke="#1e3a4a" stroke-width="{width + 2.5}" '
        f'stroke-linecap="round" stroke-linejoin="round" opacity="0.38"/>'
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" '
        f'stroke-dasharray="{dash}" stroke-linecap="round" stroke-linejoin="round" '
        f'opacity="0.82"/>'
        f"</g>"
    )


def _route_svg(
    road: dict,
    a: tuple[float, float],
    b: tuple[float, float],
    dense: bool = False,
    sailed: Optional[list[tuple[float, float]]] = None,
) -> str:
    quality = road.get("quality")
    try:
        color, width, dash = _ROAD_STYLES[RoadQuality(quality)]
    except (KeyError, ValueError):
        color, width, dash = "#9aa7b8", 2.5, "none"

    # Slightly thinner strokes when the graph is a hairball.
    if dense:
        width = max(1.6, width * 0.72)

    if sailed and len(sailed) >= 2:
        # A sea lane sails where the water is. Straight from town to town it
        # crosses whatever lies between, which island-to-mainland means most
        # of both -- thirteen of nineteen lanes on world2 were drawn mostly
        # over land before this, one of them 78% ashore.
        return _sailed_route_svg(road, sailed, color, width, dash)

    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    # Gentle bow so parallel routes / dense maps read as paths, not a grid.
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1.0
    bow = min(28.0, length * 0.08)
    # Perpendicular offset; stable from road id (not Python's salted hash()).
    rid_key = str(road.get("id", ""))
    sign = 1.0 if (sum(ord(ch) for ch in rid_key) % 2) == 0 else -1.0
    cx = mx + sign * (-dy / length) * bow
    cy = my + sign * (dx / length) * bow
    path_d = f"M {a[0]:.1f} {a[1]:.1f} Q {cx:.1f} {cy:.1f} {b[0]:.1f} {b[1]:.1f}"

    rid = _esc(str(road.get("id", "")))
    miles = road.get("distance_miles")
    hop = _hop_cost_for_raw_road(road)
    hop_txt = _format_hop(hop)
    title_bits = [str(quality or "road")]
    if miles is not None and miles != "":
        title_bits.append(f"{miles} mi")
    if hop_txt:
        title_bits.append(hop_txt)
        title_bits.append("of 10 mv/turn")
    title = _esc(" · ".join(title_bits))

    chunks = [
        f'<g class="map-route map-route-{_esc(str(quality or "road"))}" data-road="{rid}">'
    ]
    chunks.append(f"<title>{title}</title>")

    if quality == "sea":
        # Under-glow + dashed wave path.
        chunks.append(
            f'<path d="{path_d}" fill="none" stroke="#1e3a4a" stroke-width="{width + 4}" '
            f'stroke-linecap="round" opacity="0.55"/>'
        )
        chunks.append(
            f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-dasharray="{dash}" stroke-linecap="round" opacity="0.92"/>'
        )
        if not dense:
            chunks.append(
                f'<text x="{cx:.1f}" y="{cy:.1f}" fill="{color}" font-size="14" '
                f'text-anchor="middle" opacity="0.85" class="map-meta">≈</text>'
            )
        label_dy = 12
    else:
        chunks.append(
            f'<path d="{path_d}" fill="none" stroke="#0c0e14" stroke-width="{width + 2.5}" '
            f'stroke-linecap="round" opacity="0.55"/>'
        )
        chunks.append(
            f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-dasharray="{dash}" stroke-linecap="round" opacity="0.95"/>'
        )
        label_dy = -6

    # Mile/mv labels only on sparse maps — on the world map they overlap into soup.
    if not dense and miles is not None and miles != "":
        label = f"{miles} mi"
        if hop_txt:
            label = f"{miles} mi · {hop_txt}"
        chunks.append(
            f'<text x="{cx:.1f}" y="{cy + label_dy:.1f}" fill="#6d7584" font-size="10" '
            f'text-anchor="middle" class="map-meta" paint-order="stroke" stroke="#0e1218" '
            f'stroke-width="3">{_esc(label)}</text>'
        )
    chunks.append("</g>")
    return "\n".join(chunks)


def _city_fill(city: dict) -> str:
    band = city.get("population_band") or "10k-99k"
    base = _BAND_COLORS.get(band, "#b0bac8")
    terrain = city.get("terrain") or []
    if isinstance(terrain, str):
        terrain = [terrain]
    for key in terrain:
        tint = _TERRAIN_TINT.get(str(key).lower())
        if tint:
            return _mix_hex(base, tint, 0.35)
    return base


def _mix_hex(a: str, b: str, t: float) -> str:
    """Blend two #rrggbb colors; t is weight toward b."""

    def parse(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    try:
        ar, ag, ab = parse(a)
        br, bg, bb = parse(b)
    except (ValueError, IndexError):
        return a
    r = int(ar + (br - ar) * t)
    g = int(ag + (bg - ag) * t)
    bl = int(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def _resource_labels(city: dict) -> list[str]:
    richness = city.get("resource_richness") or {}
    if not isinstance(richness, dict):
        return []
    labels = []
    for key in sorted(richness.keys()):
        try:
            val = float(richness[key])
        except (TypeError, ValueError):
            continue
        if val > 0:
            labels.append(str(key))
    return labels


def _overlay_key_svg(overlay: dict) -> str:
    """On-map key: the factions in play and how much ground each is known to hold."""
    factions = overlay.get("factions") or []
    if not factions:
        return ""
    x, y = 26.0, 118.0
    row_h = 20.0
    height = 34 + row_h * len(factions)
    chunks = [
        '<g class="map-overlay-key">',
        f'<rect x="{x - 10:.1f}" y="{y - 22:.1f}" width="248" height="{height:.1f}" '
        f'rx="8" fill="#0d1017" fill-opacity="0.80" stroke="#2b3340" stroke-width="1"/>',
        f'<text x="{x:.1f}" y="{y - 6:.1f}" fill="#c9a24b" font-size="11" '
        f'font-weight="bold" class="map-meta">TURN '
        f"{_esc(str(overlay.get('turn', 0)))} — WHO HOLDS WHAT</text>",
    ]
    for i, f in enumerate(factions):
        row_y = y + 12 + i * row_h
        is_you = f.get("id") == overlay.get("faction_id")
        label = f"{f.get('name', '?')}{' (you)' if is_you else ''}"
        held = f.get("cities", 0)
        chunks.append(
            f'<circle cx="{x + 6:.1f}" cy="{row_y - 4:.1f}" r="5.5" '
            f'fill="{f.get("color", "#888")}" stroke="#10131a" stroke-width="1.2"/>'
        )
        chunks.append(
            f'<text x="{x + 18:.1f}" y="{row_y:.1f}" fill="#e8e4d8" font-size="11.5" '
            f'class="map-meta">{_esc(label)}</text>'
        )
        chunks.append(
            f'<text x="{x + 228:.1f}" y="{row_y:.1f}" fill="#8a93a0" font-size="11" '
            f'text-anchor="end" class="map-meta">{held} cit{"ies" if held != 1 else "y"}</text>'
        )
    chunks.append("</g>")
    return "\n".join(chunks)


def _marks_svg(
    marks: dict, x: float, y: float, radius: float
) -> tuple[list[str], list[str]]:
    """
    Live-game decoration for one city: holder ring, own-force badge.

    Returns (svg_chunks, tooltip_extras). Only draws what this player is
    entitled to know -- an unobserved city keeps its geography and gives up
    nothing about who is standing on it.
    """
    chunks: list[str] = []
    tips: list[str] = []

    holder_color = marks.get("holder_color")
    holder_name = marks.get("holder_name")
    if holder_color and holder_name:
        chunks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 9:.1f}" fill="none" '
            f'stroke="{holder_color}" stroke-width="2.6" opacity="0.95"/>'
        )
        # Pennant on a staff, so the holder reads without relying on colour.
        staff_top = y - radius - 20
        chunks.append(
            f'<line x1="{x + radius + 8:.1f}" y1="{y - radius:.1f}" '
            f'x2="{x + radius + 8:.1f}" y2="{staff_top:.1f}" '
            f'stroke="#e8e4d8" stroke-width="1.4"/>'
        )
        chunks.append(
            f'<path d="M {x + radius + 8:.1f} {staff_top:.1f} '
            f'l 15 4.5 l -15 4.5 z" fill="{holder_color}" '
            f'stroke="#10131a" stroke-width="0.9"/>'
        )
        tips.append(f"held by {holder_name}")
    elif marks.get("observed"):
        tips.append("no one holds this")

    # The pennant can only show one thing, and sovereignty is not the same as
    # the right to tax or recruit here. Where this player is entitled to know,
    # the tooltip names all three so the map explains the orders that fail.
    if marks.get("administrator_name"):
        tips.append(f"sovereign: {marks['sovereign_name']}")
        tips.append(f"occupier: {marks['occupier_name']}")
        tips.append(f"administrator: {marks['administrator_name']}")
    elif marks.get("secured_by_name"):
        tips.append(f"secured by {marks['secured_by_name']}")

    chars = int(marks.get("characters") or 0)
    units = int(marks.get("units") or 0)
    ships = int(marks.get("ships") or 0)
    if chars or units or ships:
        bits = []
        if chars:
            bits.append(f"{chars}†")  # dagger: characters
        if units:
            bits.append(f"{units}▲")  # triangle: soldiers
        if ships:
            bits.append(f"{ships}⚓")  # anchor: ships
        badge = " ".join(bits)
        bx, by = x - radius - 8, y - radius - 4
        width = 11 + 15 * len(bits)
        chunks.append(
            f'<rect x="{bx - width:.1f}" y="{by - 9:.1f}" width="{width:.1f}" '
            f'height="14" rx="4" fill="#0d1017" fill-opacity="0.88" '
            f'stroke="#c9a24b" stroke-width="1"/>'
        )
        chunks.append(
            f'<text x="{bx - width / 2:.1f}" y="{by + 1.5:.1f}" fill="#e8d9a8" '
            f'font-size="10" text-anchor="middle" class="map-meta">{_esc(badge)}</text>'
        )
        detail = []
        subject = "on the board" if marks.get("master") else "of your faction"
        if chars:
            detail.append(f"{chars} characters {subject}")
        if units:
            detail.append(f"{units} soldiers {subject}")
        if ships:
            detail.append(f"{ships} ships {subject}")
        tips.append("; ".join(detail))

    return chunks, tips


def _city_svg(
    city: dict,
    x: float,
    y: float,
    marks: Optional[dict] = None,
    plan: Optional[CityLabelPlan] = None,
) -> str:
    """Draw one city marker with density-aware labels from ``CityLabelPlan``."""
    band = city.get("population_band") or "10k-99k"
    base_radius = _BAND_RADIUS.get(band, 8.5)
    if plan is None:
        plan = CityLabelPlan()
    radius = max(3.5, base_radius * plan.radius_scale)
    fill = _city_fill(city)
    name = city.get("name") or city.get("id") or "?"
    is_port = bool(city.get("is_port"))
    is_magic = bool(city.get("is_magic_free"))
    is_ruin = bool(city.get("is_ruin"))
    resources = _resource_labels(city)

    info_bits: list[str] = []
    pop = city.get("population")
    if pop is not None:
        try:
            info_bits.append(f"{int(pop):,}")
        except (TypeError, ValueError):
            info_bits.append(str(pop))
    else:
        info_bits.append(str(band))
    if city.get("grid_ref"):
        info_bits.append(str(city["grid_ref"]))
    if is_magic:
        info_bits.append("magic-free")
    if is_ruin:
        info_bits.append("ruin")
    if is_port:
        info_bits.append("port")
    if resources:
        info_bits.append("+".join(resources))
    terrain = city.get("terrain") or []
    if isinstance(terrain, (list, set, tuple)) and terrain:
        info_bits.append("/".join(sorted(str(t) for t in terrain)[:2]))
    meta = " · ".join(info_bits)

    tip_parts = [name]
    if pop is not None:
        tip_parts.append(f"pop {pop:,}" if isinstance(pop, int) else f"pop {pop}")
    if city.get("region"):
        tip_parts.append(str(city["region"]))
    if city.get("grid_ref"):
        tip_parts.append(f"grid {city['grid_ref']}")
    if is_magic:
        tip_parts.append("magic-free")
    if is_ruin:
        tip_parts.append("ruin (SEARCH)")
    if is_port:
        tip_parts.append("port")
    if resources:
        tip_parts.append("resources: " + ", ".join(resources))

    mark_chunks, mark_tips = _marks_svg(marks, x, y, radius) if marks else ([], [])
    tip_parts.extend(mark_tips)
    tip = _esc(" — ".join(tip_parts))

    label_text = plan.display_name or name
    label_x = x + plan.label_dx
    label_y = y + plan.label_dy
    # Meta sits opposite the name when the name is above; otherwise below.
    if plan.label_dy <= 0:
        meta_y = y + radius + (14 if not is_port else 18)
    else:
        meta_y = y - radius - 8
    cid = _esc(str(city.get("id", "")))
    anchor = plan.text_anchor or "middle"

    name_cls = "city-name map-label"
    if plan.name_mode == "always":
        name_cls += " city-name-always"
    elif plan.name_mode == "hover":
        name_cls += " city-label-hover"

    meta_cls = "map-meta city-meta"
    if plan.meta_mode == "hover":
        meta_cls += " city-meta-hover"

    chunks = [
        f'<g class="map-city-hit" data-city="{cid}" tabindex="0"><title>{tip}</title>'
    ]

    # Hit area (invisible) for easier hover / focus.
    chunks.append(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 12}" fill="transparent"/>'
    )

    if is_magic:
        chunks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 5}" fill="none" '
            f'stroke="#a06ee0" stroke-width="1.4" stroke-dasharray="3.5 3" opacity="0.9"/>'
        )

    if is_ruin:
        chunks.append(
            f'<circle class="city-core" cx="{x:.1f}" cy="{y:.1f}" r="{radius}" '
            f'fill="none" stroke="#9a8a70" stroke-width="2" stroke-dasharray="4 3"/>'
        )
        chunks.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{max(2.0, radius * 0.35)}" '
            f'fill="#5a5040" stroke="#10131a" stroke-width="1"/>'
        )
    else:
        if plan.show_rings and band == "100k+":
            chunks.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 3.5}" fill="none" '
                f'stroke="#c9a24b" stroke-width="1.2" opacity="0.85"/>'
            )
        elif plan.show_rings and band == "10k-99k":
            chunks.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius + 2.4}" fill="none" '
                f'stroke="#b8c2d0" stroke-width="1.0" opacity="0.5"/>'
            )
        chunks.append(
            f'<circle class="city-core" cx="{x:.1f}" cy="{y:.1f}" r="{radius}" '
            f'fill="{fill}" stroke="#10131a" stroke-width="1.8"/>'
        )
        chunks.append(
            f'<circle cx="{x - radius * 0.28:.1f}" cy="{y - radius * 0.28:.1f}" '
            f'r="{max(1.2, radius * 0.22)}" fill="#ffffff" opacity="0.18"/>'
        )

    if is_port:
        pr = radius + 5
        chunks.append(
            f'<path d="M {x - pr:.1f} {y + radius + 2:.1f} '
            f'a {pr:.1f} {pr:.1f} 0 0 1 {2 * pr:.1f} 0" '
            f'fill="none" stroke="#5ba7d0" stroke-width="1.5" opacity="0.95"/>'
        )

    if resources and plan.radius_scale >= 0.7:
        rx, ry = x + radius + 5, y - radius - 1
        chunks.append(
            f'<circle cx="{rx:.1f}" cy="{ry:.1f}" r="4.5" fill="#2a3d2e" '
            f'stroke="#6fbf73" stroke-width="1.1"/>'
        )
        chunks.append(
            f'<text x="{rx:.1f}" y="{ry + 2.8:.1f}" fill="#8fd99a" font-size="7.5" '
            f'text-anchor="middle" class="map-meta">{_esc(resources[0][:1].upper())}</text>'
        )

    chunks.extend(mark_chunks)

    if plan.name_mode != "never":
        stroke_w = (
            2.2 if plan.name_size >= 11 else (1.7 if plan.name_size >= 8.5 else 1.35)
        )
        # Slightly softer ink for the smallest labels so clusters stay legible.
        name_fill = "#e8e4d8" if plan.name_size >= 8.5 else "#c8c4b8"
        weight = "bold" if plan.name_size >= 9.0 else "normal"
        chunks.append(
            f'<text class="{name_cls}" x="{label_x:.1f}" y="{label_y:.1f}" '
            f'fill="{name_fill}" font-size="{plan.name_size:.1f}" font-weight="{weight}" '
            f'text-anchor="{_esc(anchor)}" paint-order="stroke fill" '
            f'stroke="#0c0e14" stroke-width="{stroke_w}">{_esc(label_text)}</text>'
        )

    if plan.meta_mode != "never" and meta:
        chunks.append(
            f'<text class="{meta_cls}" x="{x:.1f}" y="{meta_y:.1f}" '
            f'fill="#8a93a0" font-size="8.5" text-anchor="middle" '
            f'paint-order="stroke fill" stroke="#0c0e14" stroke-width="1.3">'
            f"{_esc(meta)}</text>"
        )

    chunks.append("</g>")
    return "\n".join(chunks)


def _esc(text: Optional[str]) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
