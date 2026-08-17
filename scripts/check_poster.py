"""Publish preflight for the poster bundle: run it before the page goes live.

`webapp/static/public/` is dragged onto a static host by hand. Nothing between
the working tree and a stranger's browser checks it, so this does, and it is
the last repo-side gate in the field plan:

    python -m scripts.check_poster

Eight checks, each one a rule that already exists in prose somewhere in
docs/MARKETING_CLOSED_ALPHA.md or docs/LAUNCH_OPERATIONS.md and has never been
mechanical:

    inventory   the bundle is exactly the files the plan lists, and sea.jpg is
                not among them -- there is no sea, and shipping the texture
                invites its use
    gate        data-endpoint and data-contact are filled, so the page cannot
                go live with the form disabled or silently swallowing an
                application
    copy        the locked sentence, the seven offer bullets, the proof line,
                the privacy notice and the reply promise are present and
                unedited, and no off-card word (leaderboard, play now, prize
                pool) crept in
    replay      replay.json passes the leakage test and every city it names
                exists on the board that has to draw it
    board       board.js still matches maps/calib_12.json -- a map edit that
                never reached the poster is a poster that misrepresents the
                world
    token       every ?v= in the bundle is the same token, and that token was
                bumped after the versioned assets last changed
    isolation   nothing in the bundle points at the live server, a port, or
                an operator route; the page fetches replay.json and posts to
                the form vendor, and that is all
    weight      the gzipped bundle is under the 1.5 MB gate, measured the way
                a phone on a link would download it

Stages. `publish` is the default and is what the operator runs: an unfilled
placeholder is a blocker. `--stage build` downgrades those two to notes, for
CI and for the test suite, which runs this whole file against the tree before
either gate has been closed by a human.

The cache token is hardcoded by hand (see LAUNCH_OPERATIONS.md, "The page"),
so staleness is not detectable from the files alone. configs/poster.json
records the token and a digest of the assets that carried it. When the assets
change under an unchanged token, this refuses:

    python -m scripts.check_poster --accept-token          after bumping ?v=
    python -m scripts.check_poster --accept-token --force  same token on
                                                           purpose (nothing is
                                                           cached yet)

Exit code 0 = clear to publish, 1 = at least one blocker.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import html as html_mod
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_public_board import build_board  # noqa: E402
from soe.public_replay import LeakageError, validate_file, visual_bar  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = REPO_ROOT / "webapp" / "static" / "public"
MAP_SOURCE = REPO_ROOT / "maps" / "calib_12.json"
MANIFEST = REPO_ROOT / "configs" / "poster.json"

#: The deployable, file by file, from LAUNCH_OPERATIONS.md "The page". The
#: textures are not listed here: which ones are required follows from the
#: terrain labels on the board, plus the printed ground sheet.
REQUIRED_FILES = [
    "index.html",
    "atlas.css",
    "atlas.js",
    "board.js",
    "board3d.js",
    "replay.json",
    "vendor/three.module.js",
    "vendor/OrbitControls.js",
]

#: Shipping this is how the atlas board grows an ocean it does not have.
FORBIDDEN_FILES = {"textures/sea.jpg", "sea.jpg"}

#: Wire weight, not disk weight. A phone opening the poster from a link
#: downloads the compressed size, and Pages serves text assets compressed.
WEIGHT_GATE = 1.5 * 1024 * 1024

# --------------------------------------------------------------------------
# locked copy
# --------------------------------------------------------------------------

LOCKED_SENTENCE = (
    "You don't play the empire. You write its doctrine, freeze it, and watch "
    "an agent try to rule a world you cannot touch."
)

PROOF_LINE = "The official gate completed 7,200 model turns across two 40-pair tests."

OFFER_BULLETS = [
    "Invite only. Cap 30.",
    "Same model and limits for everyone.",
    "You write a structured doctrine. You do not write code. You do not issue "
    "orders during an official match.",
    "Three training matches per frozen version.",
    "Then paired duels and one observable final.",
    "No payment, no prize, no public ranking.",
    "Apply with: name, X or Discord, one sentence of doctrine, and an email if "
    "you want the invite code sent there.",
]

#: The privacy notice as amended (Amendment 1 added `email` to the first
#: sentence and changed nothing else), checked in pieces so the amended
#: sentence can be checked for its own content rather than verbatim.
PRIVACY_FRAGMENTS = [
    "only to decide Closed Coach Alpha invites",
    "The operator of this experiment reads them.",
    "They are not sold, not published, and not used as marketing quotes "
    "without your later consent.",
    "We keep a row until the closed alpha ends, then 90 days, unless you ask "
    "us to delete it sooner.",
    "To delete, write to the operator contact on this page.",
]

REPLY_PROMISE = "You will hear back within 7 days, either way."

#: Words that are off-card on every surface. "prize" and "ranking" are not
#: here: the offer says "no payment, no prize, no public ranking", and a
#: substring check cannot tell the promise from the breach.
OFF_CARD = [
    "leaderboard",
    "play now",
    "sign up",
    "free trial",
    "coming soon",
    "prize pool",
    "early access",
]

#: The page talks to exactly two places: replay.json, sitting beside it, and
#: the form vendor named in data-endpoint. Anything else is the live server
#: leaking onto a static poster.
LIVE_SERVER_PATTERNS = [
    (r"localhost", "a localhost address"),
    (r"127\.0\.0\.1", "a loopback address"),
    (r":8000\b", "the engine's port"),
    (r"/ops/", "an operator route"),
    (r"/rooms?/", "a live room route"),
]

#: Namespace URLs are declarations, not requests. Nothing fetches them.
ALLOWED_URLS = [r"http://www\.w3\.org/"]

BLOCKER = "BLOCK"
NOTE = "note"


class Finding:
    """One result. `level` is BLOCKER or NOTE; only BLOCKER fails the run."""

    def __init__(self, check: str, level: str, message: str) -> None:
        self.check = check
        self.level = level
        self.message = message


def display(path: Path) -> str:
    """A path as the operator would type it, or absolute if it is elsewhere."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def blocker(check: str, message: str) -> Finding:
    return Finding(check, BLOCKER, message)


def note(check: str, message: str) -> Finding:
    return Finding(check, NOTE, message)


# --------------------------------------------------------------------------
# reading the bundle
# --------------------------------------------------------------------------


def bundle_files(bundle: Path) -> list[str]:
    """Every file in the bundle, as posix-relative paths."""
    return sorted(
        p.relative_to(bundle).as_posix()
        for p in bundle.rglob("*")
        if p.is_file()
    )


def read_text(bundle: Path, name: str) -> str:
    return (bundle / name).read_text(encoding="utf-8")


def parse_board(bundle: Path) -> dict | None:
    """The topology baked into board.js, back out of its JS constant."""
    try:
        source = read_text(bundle, "board.js")
    except OSError:
        return None
    try:
        start = source.index("{")
        end = source.rindex("}")
        return json.loads(source[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return None


def normalise_copy(raw: str) -> str:
    """Page text, comparable to the card's text.

    Strips markup, resolves entities, folds the typographic apostrophes and
    quotes the page uses back to straight ones, and collapses the line breaks
    that only exist because the HTML is wrapped at 80 columns.
    """
    text = re.sub(r"<!--.*?-->", " ", raw, flags=re.DOTALL)
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_mod.unescape(text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("—", "--").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip()


def strip_comments(html: str) -> str:
    """HTML with its comments gone.

    index.html documents both placeholders in a comment at the top, naming the
    very tags they sit on. Reading an attribute off the first textual match
    reads the documentation instead of the form.
    """
    return re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)


def attribute(html: str, tag: str, element_id: str, attr: str) -> str | None:
    """One attribute off one identified element, or None if it is not there."""
    html = strip_comments(html)
    match = re.search(rf"<{tag}\b[^>]*\bid=\"{re.escape(element_id)}\"[^>]*>", html)
    if not match:
        return None
    found = re.search(rf'\b{re.escape(attr)}="([^"]*)"', match.group(0))
    return found.group(1) if found else None


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


def check_inventory(bundle: Path, board: dict | None) -> list[Finding]:
    out: list[Finding] = []
    present = set(bundle_files(bundle))

    for name in REQUIRED_FILES:
        if name not in present:
            out.append(blocker("inventory", f"missing from the bundle: {name}"))

    for name in sorted(FORBIDDEN_FILES & present):
        out.append(
            blocker(
                "inventory",
                f"{name} is in the bundle. There is no sea on this board; "
                "shipping the texture invites its use.",
            )
        )

    expected = set(REQUIRED_FILES) | {"vendor/three-LICENSE.txt"}
    if board:
        terrains = sorted({city["terrain"] for city in board.get("cities", [])})
        for terrain in terrains:
            name = f"textures/{terrain}.jpg"
            expected.add(name)
            if name not in present:
                out.append(
                    blocker(
                        "inventory",
                        f"{name} is missing and {terrain} is a terrain on the board",
                    )
                )
        expected.add("textures/paper.jpg")
        if "textures/paper.jpg" not in present:
            out.append(blocker("inventory", "textures/paper.jpg is missing (the ground sheet)"))

    for name in sorted(present - expected - FORBIDDEN_FILES):
        out.append(
            note(
                "inventory",
                f"not in the plan's file list, and it will be published: {name}",
            )
        )
    return out


def check_publish_gate(html: str, stage: str) -> list[Finding]:
    out: list[Finding] = []
    level = blocker if stage == "publish" else note

    endpoint = attribute(html, "form", "apply-form", "data-endpoint")
    if endpoint is None:
        out.append(blocker("gate", "no data-endpoint attribute on <form id=\"apply-form\">"))
    elif not endpoint.strip():
        out.append(
            level(
                "gate",
                "data-endpoint is empty: the form vendor gate is not closed, so "
                "the page shows the not-published banner and the submit button "
                "is disabled",
            )
        )
    elif not endpoint.startswith("https://"):
        out.append(
            blocker(
                "gate",
                f"data-endpoint is not https: {endpoint!r}. Applications carry "
                "a name, a handle and an email.",
            )
        )

    contact = attribute(html, "span", "operator-contact", "data-contact")
    if contact is None:
        out.append(blocker("gate", "no data-contact attribute on <span id=\"operator-contact\">"))
    elif not contact.strip():
        out.append(
            level(
                "gate",
                "data-contact is empty: the privacy notice promises an operator "
                "contact on this page and there is none",
            )
        )
    elif re.search(r"@(gmail|outlook|hotmail|yahoo|proton(mail)?)\.", contact, re.IGNORECASE):
        out.append(
            note(
                "gate",
                f"data-contact looks like a personal inbox ({contact}). The card "
                "asks for a dedicated address, not one mixed with the live game.",
            )
        )
    return out


def check_copy(html: str) -> list[Finding]:
    out: list[Finding] = []
    text = normalise_copy(html)

    if LOCKED_SENTENCE not in text:
        out.append(
            blocker(
                "copy",
                "the locked sentence is not on the page, or has been edited. It "
                "is locked by MARKETING_CLOSED_ALPHA.md and is not the page's to "
                "reword.",
            )
        )
    if PROOF_LINE not in text:
        out.append(blocker("copy", "the proof line is not on the page verbatim"))

    for index, bullet in enumerate(OFFER_BULLETS, start=1):
        if bullet not in text:
            out.append(
                blocker("copy", f"offer bullet {index} is missing or edited: {bullet!r}")
            )

    for fragment in PRIVACY_FRAGMENTS:
        if fragment not in text:
            out.append(blocker("copy", f"the privacy notice is missing: {fragment!r}"))
    if "email" not in text.split("only to decide Closed Coach Alpha invites")[0][-400:]:
        out.append(
            blocker(
                "copy",
                "the privacy notice does not name the email it collects "
                "(Amendment 1 added it to the first sentence)",
            )
        )

    if REPLY_PROMISE not in text:
        out.append(
            blocker(
                "copy",
                f"the reply promise is not on the page: {REPLY_PROMISE!r}. "
                "waitlist.py due exists to keep it.",
            )
        )

    lowered = text.lower()
    for word in OFF_CARD:
        if word in lowered:
            out.append(blocker("copy", f"off-card wording on the page: {word!r}"))
    return out


def check_replay(bundle: Path, board: dict | None) -> list[Finding]:
    out: list[Finding] = []
    path = bundle / "replay.json"
    if not path.exists():
        return [blocker("replay", "replay.json is missing")]

    try:
        replay = validate_file(path)
    except LeakageError as exc:
        return [blocker("replay", f"leakage test: {problem}") for problem in exc.args[0]]
    except (OSError, json.JSONDecodeError) as exc:
        return [blocker("replay", f"replay.json will not parse: {exc}")]

    if board:
        if replay.get("map") != board.get("map"):
            out.append(
                blocker(
                    "replay",
                    f"replay is on {replay.get('map')!r} and the board draws "
                    f"{board.get('map')!r}",
                )
            )
        known = {city["id"] for city in board.get("cities", [])}
        named = {
            piece.get("city_id")
            for frame in replay.get("frames", [])
            for piece in frame.get("pieces", [])
        } | {
            city.get("id")
            for frame in replay.get("frames", [])
            for city in frame.get("cities", [])
        }
        for city_id in sorted(named - known - {None}):
            out.append(
                blocker("replay", f"the replay names city {city_id!r}, which is not on the board")
            )

    frames = replay.get("frames") or []
    if len(frames) != replay.get("turns", 0) + 1:
        out.append(
            note(
                "replay",
                f"{len(frames)} frames for {replay.get('turns')} turns; expected "
                "one frame per turn plus the opening position",
            )
        )

    bar = visual_bar(replay)
    out.append(
        note(
            "replay",
            f"{replay.get('match_id')} · {replay.get('label')} · "
            f"{replay.get('turns')} turns · moves {bar['moves']} · "
            f"contacts {bar['contacts']} · territory changes {bar['territory_changes']}",
        )
    )
    return out


def check_board(bundle: Path, board: dict | None) -> list[Finding]:
    if board is None:
        return [blocker("board", "board.js is missing, or its ATLAS_BOARD constant will not parse")]
    if not MAP_SOURCE.exists():
        return [note("board", f"{MAP_SOURCE.name} is not in the tree; drift not checked")]

    fresh = build_board(MAP_SOURCE)
    if fresh == board:
        return [
            note(
                "board",
                f"{len(board['cities'])} cities, {len(board['roads'])} roads, "
                f"in sync with maps/{MAP_SOURCE.name}",
            )
        ]
    return [
        blocker(
            "board",
            "board.js has drifted from maps/calib_12.json. The poster would draw "
            "a world the engine no longer has. Regenerate: "
            "python -m scripts.build_public_board",
        )
    ]


def token_scan(bundle: Path) -> tuple[set[str], set[str]]:
    """Every `?v=` token in the bundle, and every asset carrying one."""
    tokens: set[str] = set()
    assets: set[str] = set()
    for name in bundle_files(bundle):
        if name.startswith("vendor/") or not name.endswith((".html", ".js", ".css")):
            continue
        for match in re.finditer(r"([\w./-]+\.(?:js|css|jpg|png))\?v=([\w.-]+)", read_text(bundle, name)):
            asset = match.group(1).lstrip("./")
            tokens.add(match.group(2))
            if (bundle / asset).exists():
                assets.add(asset)
    return tokens, assets


def digest_assets(bundle: Path, assets: set[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(assets):
        digest.update(name.encode("utf-8"))
        digest.update(hashlib.sha256((bundle / name).read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def check_token(bundle: Path, manifest_path: Path) -> list[Finding]:
    out: list[Finding] = []
    tokens, assets = token_scan(bundle)

    if not tokens:
        return [note("token", "no ?v= tokens in the bundle; nothing to keep in step")]
    if len(tokens) > 1:
        out.append(
            blocker(
                "token",
                f"the bundle carries more than one cache token: {sorted(tokens)}. "
                "One bump has to move every asset, or a returning visitor gets a "
                "new atlas.js against an old board3d.js.",
            )
        )
        return out

    token = tokens.pop()
    current = digest_assets(bundle, assets)

    if not manifest_path.exists():
        return out + [
            blocker(
                "token",
                f"{display(manifest_path)} does not exist, so a "
                "stale token cannot be detected. Record it: "
                "python -m scripts.check_poster --accept-token",
            )
        ]

    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if recorded.get("cache_token") != token:
        out.append(
            note(
                "token",
                f"token moved {recorded.get('cache_token')!r} -> {token!r} since "
                "it was last recorded; re-record with --accept-token",
            )
        )
        return out

    if sorted(assets) != sorted(recorded.get("assets", [])):
        out.append(
            blocker(
                "token",
                "the set of assets carrying the cache token changed "
                f"(recorded {sorted(recorded.get('assets', []))}, found {sorted(assets)}). "
                "An asset that lost its token is an asset that will be served stale.",
            )
        )
    elif recorded.get("asset_digest") != current:
        out.append(
            blocker(
                "token",
                f"the versioned assets changed but ?v={token} did not. Returning "
                "visitors would keep the old files. Bump the token everywhere it "
                "appears, then: python -m scripts.check_poster --accept-token",
            )
        )
    else:
        out.append(note("token", f"?v={token} across {len(assets)} assets, digest current"))
    return out


def check_isolation(bundle: Path, html: str) -> list[Finding]:
    out: list[Finding] = []
    endpoint = attribute(html, "form", "apply-form", "data-endpoint") or ""

    for name in bundle_files(bundle):
        if name.startswith("vendor/") or not name.endswith((".html", ".js", ".css")):
            continue
        source = read_text(bundle, name)
        if endpoint:
            source = source.replace(endpoint, "")

        for pattern, what in LIVE_SERVER_PATTERNS:
            if re.search(pattern, source, re.IGNORECASE):
                out.append(
                    blocker(
                        "isolation",
                        f"{name} contains {what}. The poster is static and never "
                        "talks to the engine.",
                    )
                )

        for match in re.finditer(r"https?://[^\s\"'<>)]+", source):
            url = match.group(0)
            if any(re.match(allowed, url) for allowed in ALLOWED_URLS):
                continue
            out.append(
                blocker(
                    "isolation",
                    f"{name} points off the bundle: {url}. The page loads "
                    "replay.json and posts to the form vendor, and that is all.",
                )
            )

    if not out:
        out.append(note("isolation", "no live-server address or third-party fetch in the bundle"))
    return out


def check_weight(bundle: Path) -> list[Finding]:
    disk = 0
    wire = 0
    largest: list[tuple[int, str]] = []
    for name in bundle_files(bundle):
        raw = (bundle / name).read_bytes()
        disk += len(raw)
        compressed = len(gzip.compress(raw, 9))
        # A server does not gzip a jpg into something bigger than the jpg.
        compressed = min(compressed, len(raw))
        wire += compressed
        largest.append((compressed, name))

    largest.sort(reverse=True)
    top = ", ".join(f"{name} {size / 1024:.0f} KB" for size, name in largest[:3])
    line = (
        f"{disk / 1024 / 1024:.2f} MB on disk, {wire / 1024 / 1024:.2f} MB gzipped "
        f"(gate {WEIGHT_GATE / 1024 / 1024:.1f} MB). Largest on the wire: {top}"
    )
    if wire > WEIGHT_GATE:
        return [blocker("weight", line)]
    return [note("weight", line)]


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def run_checks(bundle: Path, stage: str, manifest_path: Path) -> list[Finding]:
    if not bundle.is_dir():
        return [blocker("inventory", f"no bundle at {bundle}")]

    board = parse_board(bundle)
    findings = check_inventory(bundle, board)

    index = bundle / "index.html"
    if index.exists():
        html = index.read_text(encoding="utf-8")
        findings += check_publish_gate(html, stage)
        findings += check_copy(html)
        findings += check_isolation(bundle, html)
    else:
        findings.append(blocker("gate", "index.html is missing; copy and gate not checked"))

    findings += check_replay(bundle, board)
    findings += check_board(bundle, board)
    findings += check_token(bundle, manifest_path)
    findings += check_weight(bundle)
    return findings


def accept_token(bundle: Path, manifest_path: Path, force: bool) -> int:
    tokens, assets = token_scan(bundle)
    if len(tokens) != 1:
        print(f"refusing: the bundle carries {len(tokens)} cache tokens: {sorted(tokens)}")
        return 1

    token = tokens.pop()
    current = digest_assets(bundle, assets)
    recorded = {}
    if manifest_path.exists():
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))

    same_token = recorded.get("cache_token") == token
    changed = recorded.get("asset_digest") not in (None, current)
    if same_token and changed and not force:
        print(
            f"refusing: the assets changed but ?v={token} did not.\n"
            "Bump the token everywhere it appears in the bundle, then run this "
            "again. Use --force only while nothing is published and no browser "
            "holds the old file."
        )
        return 1

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "cache_token": token,
                "asset_digest": current,
                "assets": sorted(assets),
                "recorded_at": dt.date.today().isoformat(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"recorded ?v={token} over {len(assets)} assets in {display(manifest_path)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument(
        "--stage",
        choices=("publish", "build"),
        default="publish",
        help="publish (default): an unfilled placeholder is a blocker. "
        "build: it is a note.",
    )
    parser.add_argument(
        "--accept-token",
        action="store_true",
        help="record the current cache token and asset digest, then exit",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with --accept-token, record changed assets under an unchanged token",
    )
    parser.add_argument(
        "--host",
        help="print the three tagged entry URLs for this host and exit 0 checks first",
    )
    args = parser.parse_args(argv)

    if args.accept_token:
        return accept_token(args.bundle, args.manifest, args.force)

    findings = run_checks(args.bundle, args.stage, args.manifest)
    blockers = [f for f in findings if f.level == BLOCKER]

    width = max((len(f.check) for f in findings), default=5)
    for finding in findings:
        mark = "FAIL" if finding.level == BLOCKER else "ok  "
        print(f"{mark}  {finding.check.ljust(width)}  {finding.message}")

    print()
    if blockers:
        print(f"{len(blockers)} blocker(s). Do not publish.")
        return 1

    print(f"clear to publish ({args.stage} stage).")
    if args.host:
        host = args.host.rstrip("/")
        print("\nTest one submit from each, then delete the three rows:")
        for src in ("hn", "x", "reddit"):
            print(f"  {host}/?src={src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
