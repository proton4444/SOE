"""Open the poster in a real browser and check the board actually drew.

`check_poster.py` reads files. It cannot see a board that throws, renders
black, or quietly shows "The replay could not be loaded." — and all three
have happened:

  - `renderOnIdleChange` called `controls.update()` from inside the OrbitControls
    `change` handler, which dispatches `change`, which called it again. Every
    visitor with reduce-motion set got a stack overflow on load, surfacing in
    the replay promise's catch as a load failure that had nothing to do with
    loading.
  - The texture loader had no completion callback, so a parked board kept the
    frame it painted before the jpgs decoded: untextured mounds, forever.

Neither is visible in the bundle. Both are obvious the moment something opens
the page, which is what this does:

    python -m scripts.smoke_poster

It serves the bundle on a loopback port, loads it in Chromium twice -- once
with animation, once with `prefers-reduced-motion: reduce`, because that is
the path that broke -- and fails on a console error, an error banner, or a
canvas with nothing on it.

Needs `playwright` and a Chromium; it is skipped, not failed, where there is
none. Exit code 0 = the board drew, 1 = it did not.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import io
import socket
import socketserver
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = REPO_ROOT / "webapp" / "static" / "public"

#: Where the pre-installed browser lives in this image. Playwright's own
#: resolution is tried first; this is the fallback.
CHROMIUM_HINTS = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]

#: A board that drew has structure. One that did not is a single flat colour,
#: whatever that colour is, so the test is variety rather than brightness.
MIN_DISTINCT_COLOURS = 40

# The canvas is read by screenshotting the element, not by `toDataURL`. The
# renderer runs without `preserveDrawingBuffer`, so its backing store is gone
# once the frame is composited: `toDataURL` returns a blank image for a board
# that is on screen and perfectly fine, which is a false alarm on exactly the
# parked path this exists to watch.


def serve(bundle: Path) -> tuple[str, socketserver.TCPServer]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(bundle))

    class Quiet(socketserver.TCPServer):
        allow_reuse_address = True

        def handle_error(self, request, client_address):  # noqa: ARG002
            pass

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = Quiet(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}/index.html", server


def chromium_path() -> str | None:
    for hint in CHROMIUM_HINTS:
        if Path(hint).exists():
            return hint
    return None


def distinct_colours(png: bytes) -> int:
    """How many different pixels the canvas holds, sampled on a coarse grid."""
    try:
        from PIL import Image
    except ImportError:
        return MIN_DISTINCT_COLOURS  # cannot judge; do not fail on it

    image = Image.open(io.BytesIO(png)).convert("RGB")
    step = max(1, min(image.size) // 60)
    seen = set()
    for y in range(0, image.size[1], step):
        for x in range(0, image.size[0], step):
            seen.add(image.getpixel((x, y)))
    return len(seen)


#: Every visible label on the board, with the box it actually occupies.
#: Read from the page because the board places them by projecting each anchor
#: through the live camera -- there is no static answer to check against.
LABEL_JS = """() => {
  const host = document.querySelector('.atlas-labels');
  if (!host) { return null; }
  const hb = host.getBoundingClientRect();
  const labels = [];
  Array.from(host.children).forEach(function (n) {
    const cs = getComputedStyle(n);
    if (cs.display === 'none' || cs.visibility === 'hidden') { return; }
    if (parseFloat(cs.opacity || '1') < 0.05) { return; }
    const b = n.getBoundingClientRect();
    if (b.width <= 0 || b.height <= 0) { return; }
    labels.push({text: n.textContent.trim(), cls: n.className || '',
                 left: b.left, top: b.top, right: b.right, bottom: b.bottom});
  });
  return {frame: {left: hb.left, top: hb.top, right: hb.right, bottom: hb.bottom},
          labels: labels};
}"""

#: A label narrower than this never had its width measured. `place()` caches
#: `offsetWidth || 1` once, so a label measured while it was hidden keeps a
#: one-pixel box -- which collides with nothing and is therefore always
#: "placed". The collision pass would look like it works and do nothing.
MIN_LABEL_WIDTH = 8.0


def check_labels(page, label: str) -> list[str]:
    """The board's own label planner, checked against what it drew.

    board3d.js ranks the labels, tries several boxes each, clamps them into
    the frame and drops what will not fit. None of that is tested anywhere:
    the data behind the board has fifteen tests and the placement has none,
    because it only exists once a browser has run the projection.
    """
    problems: list[str] = []
    data = page.evaluate(LABEL_JS)
    if data is None:
        return [f"{label}: the board has no label layer"]

    labels = data["labels"]
    frame = data["frame"]
    if not any("atlas-label" in one["cls"] for one in labels):
        return [f"{label}: the board is drawn but not one city is named"]

    for one in labels:
        if one["right"] - one["left"] < MIN_LABEL_WIDTH:
            problems.append(
                f"{label}: {one['text']!r} is "
                f"{one['right'] - one['left']:.0f}px wide — it was measured "
                f"while it was hidden, so it collides with nothing"
            )

    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            if (
                a["right"] <= b["left"]
                or b["right"] <= a["left"]
                or a["bottom"] <= b["top"]
                or b["bottom"] <= a["top"]
            ):
                continue
            problems.append(
                f"{label}: {a['text']!r} prints over {b['text']!r}"
            )

    # `.atlas-labels` clips at overflow:hidden, so a label the clamp did not
    # bring inside is not merely close to the edge: it is cut in half and
    # reads as a different, shorter word.
    for one in labels:
        if (
            one["left"] < frame["left"] - 0.5
            or one["right"] > frame["right"] + 0.5
            or one["top"] < frame["top"] - 0.5
            or one["bottom"] > frame["bottom"] + 0.5
        ):
            problems.append(
                f"{label}: {one['text']!r} runs outside the board frame and "
                f"is clipped mid-word"
            )
    return problems


def check_page(
    browser,
    url: str,
    reduced: bool,
    out_dir: Path | None,
    viewport: tuple[int, int] = (1440, 900),
    tag: str = "",
) -> list[str]:
    problems: list[str] = []
    label = "reduced-motion" if reduced else "animated"
    if tag:
        label = f"{label} {tag}"

    page = browser.new_page(
        viewport={"width": viewport[0], "height": viewport[1]},
        device_scale_factor=1,
        reduced_motion="reduce" if reduced else "no-preference",
    )
    console: list[str] = []
    page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console.append(str(e)))

    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(4000)

    for message in console:
        problems.append(f"{label}: console error: {message.splitlines()[0]}")

    status = page.eval_on_selector(
        "#board-status", "e => ({ text: e.textContent.trim(), hidden: e.hidden })"
    )
    if not status["hidden"] and status["text"]:
        problems.append(f"{label}: the board is showing an error: {status['text']!r}")

    meta = page.eval_on_selector("#replay-meta", "e => e.textContent.trim()")
    if not meta:
        problems.append(f"{label}: the replay meta line is empty, so no replay was read")

    # A still board is the whole of what a reduce-motion reader sees, and it
    # opened on turn 0 -- two lone commanders, the emptiest frame of a match
    # whose argument is movement. "It drew" was true and not enough.
    if reduced:
        turn = page.eval_on_selector("#turn-label", "e => e.textContent.trim()")
        outcome = page.eval_on_selector("#replay-outcome", "e => e.textContent.trim()")
        if turn in ("", "00"):
            problems.append(
                f"{label}: the board that will not move opened on turn "
                f"{turn or '(none)'} — the frame with the least on it"
            )
        if not outcome:
            problems.append(
                f"{label}: the still board does not say how the match ended"
            )

    canvas = page.query_selector("#atlas")
    if canvas is None:
        problems.append(f"{label}: there is no board canvas on the page")
    else:
        png = canvas.screenshot(timeout=15000)
        colours = distinct_colours(png)
        if colours < MIN_DISTINCT_COLOURS:
            problems.append(
                f"{label}: the board canvas is effectively blank "
                f"({colours} distinct sampled colours)"
            )
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            safe = label.replace(" ", "-")
            (out_dir / f"board-{safe}.png").write_bytes(png)

    problems += check_labels(page, label)

    page.close()
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--out", type=Path, help="write the captured board frames here")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("skipped: playwright is not installed (pip install playwright)")
        return 0

    chromium = chromium_path()
    url, server = serve(args.bundle)
    problems: list[str] = []
    try:
        with sync_playwright() as p:
            launch = {"executable_path": chromium} if chromium else {}
            try:
                browser = p.chromium.launch(**launch)
            except Exception as exc:  # noqa: BLE001 - no browser is a skip, not a failure
                print(f"skipped: no Chromium to drive ({exc})")
                return 0
            for reduced in (False, True):
                problems += check_page(browser, url, reduced, args.out)
            # The phone is a different board, not a smaller one: the CSS
            # drops the road readings and half of every data row at 640px,
            # and the frame changes aspect, which moves every projected
            # label. Checking only the desktop checks one of two layouts.
            problems += check_page(
                browser, url, False, args.out, viewport=(390, 844), tag="phone"
            )
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    for problem in problems:
        print(f"FAIL  {problem}")
    if problems:
        print(f"\n{len(problems)} problem(s). The board does not draw. Do not publish.")
        return 1

    print(
        "ok    the board drew on desktop and phone, animated and "
        "reduced-motion, with no console error, no label printing over "
        "another or clipped by the frame, and the still one opened on the "
        "finished match"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
