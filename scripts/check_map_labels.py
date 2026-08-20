"""Audit what the map visualiser prints, and whether any of it is unreadable.

    python -m scripts.check_map_labels            # every playable map
    python -m scripts.check_map_labels --map calib_12_fbm.json
    python -m scripts.check_map_labels --browser  # measure real text metrics
    python -m scripts.check_map_labels --json

The map draws four families of permanent text: town names, the caption under
a town, the mile/movement label on a route, and the chrome (title, scale bar,
roster, compass). Before 2026-08-18 none of them was laid out against the
others -- nine pairs collided on `calib_12_fbm`, and "167 mi · 53.4 mv" over
"0 · C4 · ruin · port · plain" was one line nobody could read.

`webapp.mapview` now plans them, and `tests/test_map_chrome.py` holds the
invariant. This is the same audit as a report you can read: what each map
prints, what it had to drop, and what -- if anything -- still overlaps.

Two numbers matter per map:

    overlaps    pairs of permanent labels whose boxes intersect. One
                exception is licensed, and only on a crowded map: a town
                whose name fits in none of its eight slots gets it anyway,
                because an unnamed town is worse than a crowded one. That
                licenses two *names* touching and nothing else.
    dropped     mile labels the planner could not seat. Those distances
                stay in the route's tooltip. Some dropping is healthy --
                `calib_12_s2` puts seventeen roads on twelve towns and
                cannot print them all -- but a map dropping most of them is
                telling you it is too crowded to label at all.

**--browser measures instead of estimating.** The check normally uses the
renderer's own box model, and that model is where the first attempt at this
fix went wrong: it assumed one glyph width for both faces, so monospace
captions measured about 15% narrower than they draw and labels that overlap
came out clean. With Playwright and Chromium available, `--browser` loads
each SVG and reads `getBoundingClientRect()` off every label -- real face,
real metrics, real transforms -- and reports both. Where they disagree, the
browser is right and `LABEL_EM_MONO` / `LABEL_EM_SERIF` need re-measuring.

Exit code 0 = every map's labels are readable, 1 = at least one is not.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from webapp import mapview  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MAPS_DIR = REPO_ROOT / "maps"

#: A crowded map may leave two town names touching; see the module docstring.
CROWDED_CITY_COUNT = 24


@dataclass
class MapReport:
    map_file: str
    cities: int
    dense: bool
    labels: int
    mile_printed: int
    mile_total: int
    overlaps: list[tuple[str, str]] = field(default_factory=list)
    licensed: list[tuple[str, str]] = field(default_factory=list)
    measured_overlaps: list[tuple[str, str]] | None = None

    @property
    def dropped(self) -> int:
        """Distances the planner could not seat. Nil on a dense map, which
        moves every mile label into tooltips by design rather than for want
        of room."""
        if self.dense:
            return 0
        return self.mile_total - self.mile_printed

    @property
    def ok(self) -> bool:
        if self.overlaps:
            return False
        return not self.measured_overlaps

    def as_dict(self) -> dict:
        out = {
            "map": self.map_file,
            "cities": self.cities,
            "dense": self.dense,
            "labels": self.labels,
            "mile_labels_printed": self.mile_printed,
            "mile_labels_total": self.mile_total,
            "dropped": self.dropped,
            "overlaps": self.overlaps,
            "licensed_name_crowding": self.licensed,
            "ok": self.ok,
        }
        if self.measured_overlaps is not None:
            out["measured_overlaps"] = self.measured_overlaps
        return out


def playable_maps() -> list[str]:
    """Every map file in ``maps/`` the renderer can draw, geography aside."""
    found = []
    for path in sorted(MAPS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("cities"):
            found.append(path.name)
    return found


def audit(map_file: str) -> MapReport:
    svg = mapview.render_svg(map_file)
    data = mapview.load_raw_map(map_file)
    cities = data.get("cities") or []
    roads = data.get("roads") or []
    boxes = mapview.occupied_label_boxes(svg)

    overlaps: list[tuple[str, str]] = []
    licensed: list[tuple[str, str]] = []
    crowded = len(cities) >= CROWDED_CITY_COUNT
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            if not mapview._boxes_overlap(a, b, pad=0.0):
                continue
            names_only = "city-name" in a.cls and "city-name" in b.cls
            (licensed if crowded and names_only else overlaps).append((a.text, b.text))

    mile_total = sum(1 for r in roads if mapview.road_label_text(r))
    mile_printed = sum(
        1 for box in boxes if box.cls == "map-meta" and box.text.endswith("mv")
    )
    return MapReport(
        map_file=map_file,
        cities=len(cities),
        dense=len(cities) >= mapview._DENSE_CITY_COUNT,
        labels=len(boxes),
        mile_printed=mile_printed,
        mile_total=mile_total,
        overlaps=overlaps,
        licensed=licensed,
    )


# ---------------------------------------------------------------------------
# browser measurement
# ---------------------------------------------------------------------------

_MEASURE_JS = """() => Array.from(document.querySelectorAll('text')).filter(t => {
    const c = t.getAttribute('class') || '';
    if (c.includes('hover') || c.includes('land-label')) return false;
    return t.textContent.trim().length > 0;
}).map(t => {
    const b = t.getBoundingClientRect();
    return {text: t.textContent.trim(), cls: t.getAttribute('class') || '',
            left: b.left, top: b.top, right: b.right, bottom: b.bottom};
})"""


def measure_in_browser(map_files: list[str], tmp: Path) -> dict[str, list[dict]]:
    """Real boxes for every permanent label, or raise if no browser is here."""
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    chromium = _chromium_path()
    out: dict[str, list[dict]] = {}
    tmp.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        launch = {"executable_path": str(chromium)} if chromium else {}
        browser = pw.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        for map_file in map_files:
            path = tmp / (Path(map_file).stem + ".svg")
            path.write_text(mapview.render_svg(map_file), encoding="utf-8")
            page.goto(path.resolve().as_uri())
            page.wait_for_timeout(250)
            out[map_file] = page.evaluate(_MEASURE_JS)
        browser.close()
    return out


def _chromium_path() -> Path | None:
    """The pre-installed browser, if this machine has one where we expect."""
    root = Path("/opt/pw-browsers")
    if not root.is_dir():
        return None
    for candidate in sorted(root.glob("chromium-*/chrome-linux/chrome")):
        return candidate
    return None


def measured_overlaps(rows: list[dict], crowded: bool) -> list[tuple[str, str]]:
    found = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if (
                a["right"] < b["left"]
                or b["right"] < a["left"]
                or a["bottom"] < b["top"]
                or b["bottom"] < a["top"]
            ):
                continue
            if crowded and "city-name" in a["cls"] and "city-name" in b["cls"]:
                continue
            found.append((a["text"], b["text"]))
    return found


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def render_report(reports: list[MapReport], browser: bool) -> str:
    lines = []
    head = f"{'map':22} {'towns':>5} {'labels':>6} {'mile labels':>12} {'overlaps':>8}"
    lines.append(head)
    lines.append("-" * len(head))
    for r in reports:
        if r.dense:
            miles = "off (dense)"
        elif r.mile_total:
            miles = f"{r.mile_printed}/{r.mile_total}"
        else:
            miles = "--"
        mark = "" if r.ok else "  FAIL"
        lines.append(
            f"{r.map_file:22} {r.cities:5} {r.labels:6} {miles:>12} "
            f"{len(r.overlaps):8}{mark}"
        )
    lines.append("")

    for r in reports:
        for a, b in r.overlaps:
            lines.append(f"FAIL  {r.map_file}: {a!r} prints over {b!r}")
        if r.measured_overlaps:
            for a, b in r.measured_overlaps:
                lines.append(f"FAIL  {r.map_file}: browser says {a!r} over {b!r}")
        if r.licensed:
            for a, b in r.licensed:
                lines.append(
                    f"note  {r.map_file}: {a!r} and {b!r} touch — licensed, "
                    f"{r.cities} towns"
                )
        if not r.dense and r.mile_total and r.dropped > r.mile_total / 2:
            lines.append(
                f"note  {r.map_file}: {r.dropped} of {r.mile_total} distances "
                f"went to tooltips — this map is crowded for its size"
            )

    if browser:
        lines.append("")
        lines.append(
            "Measured in Chromium against real text metrics, not the "
            "renderer's box model."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--map", action="append", dest="maps", help="one map file; repeatable"
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="also measure every label in Chromium and report the disagreement",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable")
    parser.add_argument(
        "--tmp",
        type=Path,
        default=Path(".map-label-audit"),
        help="where --browser writes the SVGs it loads",
    )
    args = parser.parse_args(argv)

    map_files = args.maps or playable_maps()
    if not map_files:
        print("no playable maps found under maps/", file=sys.stderr)
        return 1

    reports = [audit(m) for m in map_files]

    if args.browser:
        try:
            measured = measure_in_browser(map_files, args.tmp)
        except Exception as exc:  # noqa: BLE001 - report, do not mask
            print(f"browser measurement unavailable: {exc}", file=sys.stderr)
            return 1
        for report in reports:
            report.measured_overlaps = measured_overlaps(
                measured[report.map_file], report.cities >= CROWDED_CITY_COUNT
            )

    if args.json:
        print(json.dumps([r.as_dict() for r in reports], indent=2))
    else:
        print(render_report(reports, args.browser))

    failed = [r for r in reports if not r.ok]
    if failed:
        if not args.json:
            print()
            print(f"{len(failed)} map(s) print unreadable labels.")
        return 1
    if not args.json:
        print("Every map's labels are readable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
