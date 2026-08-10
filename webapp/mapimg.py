"""
SVG -> PNG rasterisation for the AI map endpoint.

Backends, tried in order:

1. ``cairosvg`` — fast, but needs the native cairo library.
2. ``playwright`` (chromium) — heavier (~1-2s per render) but needs no native
   cairo install; used automatically when cairosvg is unavailable.

When neither is usable the endpoint reports 501 instead of failing silently.
"""

from __future__ import annotations

import re

_VIEWBOX_RE = re.compile(r'viewBox="\s*[\d.]+[\s,]+[\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)"')


class PngBackendUnavailable(RuntimeError):
    """No usable SVG->PNG backend (cairosvg or playwright) is installed."""


def svg_to_png(svg: str) -> bytes:
    try:
        return _cairosvg(svg)
    except Exception:  # noqa: BLE001 - fall through to playwright
        pass
    try:
        return _playwright(svg)
    except PngBackendUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - surface as backend failure
        raise PngBackendUnavailable(
            f"playwright PNG render failed: {type(exc).__name__}"
        ) from exc


def _cairosvg(svg: str) -> bytes:
    import cairosvg  # type: ignore[import-untyped]  # noqa: F401 - ImportError or OSError (missing libcairo) on some hosts

    return cairosvg.svg2png(bytestring=svg.encode("utf-8"))


def _playwright(svg: str) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PngBackendUnavailable(
            "PNG conversion unavailable: install cairosvg or playwright."
        ) from exc
    width, height = _map_size(svg)
    with sync_playwright() as play:
        browser = play.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page.set_content(svg)
            element = page.locator("svg")
            return element.screenshot()
        finally:
            browser.close()


def _map_size(svg: str) -> tuple[int, int]:
    match = _VIEWBOX_RE.search(svg)
    if match:
        return max(64, int(float(match.group(1)))), max(64, int(float(match.group(2))))
    return 1200, 800
