"""The public replay file: schema, sanitiser, and leakage validator.

`MARKETING_CLOSED_ALPHA.md` allows exactly one game artefact on the public
poster: a static `soe.public_replay.v1` JSON. The page never calls the live
server and never reads an arena bundle, so everything a stranger can see about
a match has to survive this module first.

Three things live here rather than in the exporter script so that the test
suite can import them without touching `games/arena/`:

``build``
    Turn a reconstruction (a list of per-turn positions) into the file.
``validate``
    The leakage test. Fails on anything outside the allowlist, on order or
    report text, on hashes, seeds, keys and paths, and on an `official-gate`
    label attached to a match that nobody would want to watch.
``visual_bar``
    Movement, contact, and territorial change, scored from the exported file
    alone. The exporter uses it to rank candidates; `validate` uses it to
    refuse a dishonest label.

The forbidden list is the point of the module. `turns.jsonl` stores state
hashes and seeds, `decisions/` stores model traces, and `orders/` stores the
raw doctrine output -- none of it is publishable, and none of it can reach the
file through this path.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "soe.public_replay.v1"

#: The only labels a public replay may carry. `official-gate` is a claim about
#: provenance -- it means the match came out of the 7,200-turn gate -- so it is
#: gated on the visual bar as well as on the source bundle.
LABELS = ("exhibition", "official-gate")

#: `kind` values a piece may take. Anything finer (elite units, ships, summons)
#: would start describing force composition, which is a faction secret.
PIECE_KINDS = ("character", "stack")

# ---------------------------------------------------------------------------
# allowlist
# ---------------------------------------------------------------------------

#: Nested key allowlist. A key not named here is a leak, whatever it holds.
#: `None` marks a leaf; a tuple marks a list of objects with their own keys.
ALLOWLIST: dict[str, Any] = {
    "schema": None,
    "map": None,
    "match_id": None,
    "label": None,
    "turns": None,
    "seats": ("[]", {"id": None, "label": None}),
    "result": {"winner_seat": None, "decided_by": None},
    "frames": (
        "[]",
        {
            "turn": None,
            "pieces": ("[]", {"id": None, "seat": None, "city_id": None, "kind": None}),
            "cities": (
                "[]",
                {"id": None, "occupied_by": None, "secured_by": None},
            ),
        },
    ),
}

# ---------------------------------------------------------------------------
# forbidden shapes
# ---------------------------------------------------------------------------

#: Order verbs, matched on a word boundary. The engine's command language is
#: capitalised in reports and lowercase in prose, so the check is case
#: insensitive: no public field has a legitimate reason to say "recruit".
_ORDER_VERBS = (
    "recruit", "attack", "tax", "move", "march", "hire", "train", "buy",
    "sell", "invest", "steal", "assassinate", "besiege", "siege", "capture",
    "garrison", "fortify", "explore", "search", "post", "give", "drop",
    "pillage", "raid", "defend", "retreat", "wait", "seize", "secure", "go",
)
_ORDER_VERB_RE = re.compile(
    r"\b(" + "|".join(_ORDER_VERBS) + r")\b", re.IGNORECASE
)

#: A public string is an id or a label. Several words closed by a full stop is
#: a sentence, and the only sentences near this data are order lines and report
#: prose. Catching the shape rather than the vocabulary means an order the verb
#: list has never seen still fails.
_SENTENCE_RE = re.compile(r"\S+\s+\S+.*[.!?]\s*$")

#: Section banners the report and order formats use.
_REPORT_MARKER_RE = re.compile(
    r"(-{2,}\s*[A-Z][A-Z ]+\s*-{2,}|^\s*(TURN|ORDERS|REPORT)\b)", re.MULTILINE
)

_SHA256_RE = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
_SHA_LIKE_RE = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)
_API_KEY_RE = re.compile(r"\b(sk-|pk-|api[_-]?key|bearer\s|xox[baprs]-)", re.IGNORECASE)
_PATH_RE = re.compile(r"(^|[\s\"'])([A-Za-z]:[\\/]|\.{1,2}[\\/]|[\\/])|[\\/]{1}[\w.-]+[\\/]")
_PROVIDER_RE = re.compile(
    r"\b(openai|anthropic|gpt-|claude|gemini|mistral|llama|openrouter|"
    r"deepseek|qwen|azure|bedrock|vertex)\b",
    re.IGNORECASE,
)

#: Any integer at or above this is a seed or a hash-derived number, not a
#: count. Turn indices, piece counts and city counts are all far below it.
SEED_FLOOR = 2 ** 32

#: A public string field is a label or an id. Anything longer is prose, and
#: prose on this file is a report.
MAX_STRING = 80

#: Below this the match is not worth watching, and `official-gate` becomes a
#: claim the file cannot support. The doctrine bundle recorded zero attacks
#: and zero eliminations in 80 games, which is exactly the case this catches.
MIN_MOVES = 4
MIN_TERRITORY_CHANGES = 1


class LeakageError(ValueError):
    """The replay carries something the public page must never show."""

    def __init__(self, violations: Sequence[str]) -> None:
        self.violations = list(violations)
        joined = "\n  - ".join(self.violations)
        super().__init__(f"public replay failed the leakage test:\n  - {joined}")


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def sanitise_seat_label(raw: str) -> str:
    """A seat's public label, with provider and model identity removed.

    Arena seats are recorded as `llm:<provider>/<model>:<blueprint>` or
    `scripted:<style>`. The blueprint is a doctrine name -- the interesting,
    publishable half -- while the provider and model are infrastructure the
    poster does not sell and the offer promises is identical for everyone.
    """
    text = str(raw or "").strip()
    if text.startswith("llm:"):
        parts = text.split(":")
        # llm:<provider/model>:<blueprint> -- keep the last segment only.
        label = parts[-1] if len(parts) >= 3 else "doctrine"
        return label if not _PROVIDER_RE.search(label) else "doctrine"
    if text.startswith("scripted:"):
        return f"scripted ({text.split(':', 1)[1]})"
    if _PROVIDER_RE.search(text):
        return "doctrine"
    return text or "seat"


class _PieceRegistry:
    """Stable opaque ids for pieces, in first-seen order.

    Engine ids can carry a character's personal name, which the contract
    forbids when it encodes a player handle. Rather than guess which names are
    safe, every piece gets `c1`, `c2`, `s1`... The page only needs the id to be
    stable across frames so a piece can be animated between cities.
    """

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}
        self._counts: dict[str, int] = {"character": 0, "stack": 0}

    def opaque(self, engine_id: str, kind: str) -> str:
        if engine_id not in self._seen:
            self._counts[kind] += 1
            self._seen[engine_id] = f"{kind[0]}{self._counts[kind]}"
        return self._seen[engine_id]


def frame_from_state(state: Any, turn: int, registry: _PieceRegistry) -> dict:
    """One public frame from an engine `GameState`.

    Pieces are living, non-prisoner characters and unit stacks. Everything
    else the state holds -- gold, health, morale, items, skills, messages,
    order queues -- is dropped here and never reaches the file.
    """
    pieces: list[dict] = []
    occupied: dict[str, set[str]] = {}

    for char in sorted(state.characters.values(), key=lambda c: c.id):
        if char.is_dead or char.is_prisoner or char.faction_id == "independent":
            continue
        pieces.append(
            {
                "id": registry.opaque(char.id, "character"),
                "seat": char.faction_id,
                "city_id": char.location_city_id,
                "kind": "character",
            }
        )
        occupied.setdefault(char.location_city_id, set()).add(char.faction_id)

    for stack in sorted(state.unit_stacks.values(), key=lambda s: s.id):
        if stack.count <= 0 or stack.faction_id == "independent":
            continue
        pieces.append(
            {
                "id": registry.opaque(stack.id, "stack"),
                "seat": stack.faction_id,
                "city_id": stack.location_city_id,
                "kind": "stack",
            }
        )
        occupied.setdefault(stack.location_city_id, set()).add(stack.faction_id)

    secured_by: dict[str, str] = {}
    for faction in state.factions.values():
        for city_id in getattr(faction, "secured_city_ids", set()) or ():
            secured_by[city_id] = faction.id

    cities = [
        {
            "id": city_id,
            "occupied_by": sorted(occupied.get(city_id, ())),
            "secured_by": secured_by.get(city_id),
        }
        for city_id in sorted(state.world_map.cities)
    ]
    return {"turn": turn, "pieces": pieces, "cities": cities}


def build(
    *,
    map_file: str,
    match_id: str,
    label: str,
    seats: Mapping[str, str],
    frames: Sequence[Mapping[str, Any]],
    winner_seat: str | None,
    decided_by: str,
) -> dict:
    """Assemble the file. Does not validate -- callers run `validate`."""
    if label not in LABELS:
        raise ValueError(f"label must be one of {LABELS}, got {label!r}")
    return {
        "schema": SCHEMA,
        "map": Path(str(map_file)).name,
        "match_id": match_id,
        "label": label,
        "turns": len(frames) - 1 if frames else 0,
        "seats": [
            {"id": seat_id, "label": sanitise_seat_label(raw)}
            for seat_id, raw in sorted(seats.items())
        ],
        "result": {"winner_seat": winner_seat, "decided_by": decided_by},
        "frames": [dict(frame) for frame in frames],
    }


# ---------------------------------------------------------------------------
# visual bar
# ---------------------------------------------------------------------------


def visual_bar(replay: Mapping[str, Any]) -> dict:
    """Score a replay on what a stranger would actually see.

    Returns `moves`, `contacts`, `territory_changes`, and `passes`. A match
    with no movement and no territorial change is a behavioural result, not a
    watchable war, and must not be posted as `official-gate`.
    """
    frames = list(replay.get("frames") or [])
    moves = 0
    contacts = 0
    territory_changes = 0
    prev_pieces: dict[str, str] = {}
    prev_secured: dict[str, str | None] = {}

    for frame in frames:
        pieces = {p["id"]: p["city_id"] for p in frame.get("pieces", [])}
        for piece_id, city_id in pieces.items():
            if piece_id in prev_pieces and prev_pieces[piece_id] != city_id:
                moves += 1
        prev_pieces = pieces

        secured: dict[str, str | None] = {}
        for city in frame.get("cities", []):
            secured[city["id"]] = city.get("secured_by")
            if len(city.get("occupied_by") or ()) > 1:
                contacts += 1
        for city_id, holder in secured.items():
            if city_id in prev_secured and prev_secured[city_id] != holder:
                territory_changes += 1
        prev_secured = secured

    passes = moves >= MIN_MOVES and territory_changes >= MIN_TERRITORY_CHANGES
    return {
        "moves": moves,
        "contacts": contacts,
        "territory_changes": territory_changes,
        "passes": passes,
    }


# ---------------------------------------------------------------------------
# leakage test
# ---------------------------------------------------------------------------


def _walk_keys(node: Any, spec: Any, path: str, out: list[str]) -> None:
    """Depth-first key check against `ALLOWLIST`."""
    if isinstance(spec, tuple):
        if not isinstance(node, list):
            out.append(f"{path}: expected a list")
            return
        for index, item in enumerate(node):
            _walk_keys(item, spec[1], f"{path}[{index}]", out)
        return
    if isinstance(spec, dict):
        if not isinstance(node, dict):
            out.append(f"{path}: expected an object")
            return
        for key in node:
            if key not in spec:
                out.append(f"{path}.{key}: key is not on the allowlist")
                continue
            child = spec[key]
            if child is not None:
                _walk_keys(node[key], child, f"{path}.{key}", out)
        for key in spec:
            if key not in node:
                out.append(f"{path}.{key}: required key is missing")


def _check_scalar(value: Any, path: str, out: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) >= SEED_FLOOR:
            out.append(f"{path}: integer {value} is seed-sized")
        return
    if isinstance(value, float):
        out.append(f"{path}: floats are not on the allowlist")
        return
    if not isinstance(value, str):
        return

    text = value
    if len(text) > MAX_STRING:
        out.append(f"{path}: string is {len(text)} chars, prose is not publishable")
    if "\n" in text:
        out.append(f"{path}: multi-line string looks like a report")
    if _SHA256_RE.search(text) or _SHA_LIKE_RE.search(text):
        out.append(f"{path}: value looks like a hash")
    if _API_KEY_RE.search(text):
        out.append(f"{path}: value looks like an API key")
    if _PATH_RE.search(text):
        out.append(f"{path}: value looks like a filesystem path")
    if "games/arena" in text.replace("\\", "/"):
        out.append(f"{path}: value names an arena bundle")
    if _PROVIDER_RE.search(text):
        out.append(f"{path}: value names a model provider")
    if _REPORT_MARKER_RE.search(text):
        out.append(f"{path}: value carries a report or orders banner")
    if _ORDER_VERB_RE.search(text):
        out.append(f"{path}: value contains an order verb")
    if _SENTENCE_RE.match(text):
        out.append(f"{path}: value is a sentence, not an id or a label")


def _walk_values(node: Any, path: str, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, child in node.items():
            _walk_values(child, f"{path}.{key}", out)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            _walk_values(child, f"{path}[{index}]", out)
    else:
        _check_scalar(node, path, out)


def validate(replay: Mapping[str, Any]) -> None:
    """The leakage test. Raises `LeakageError` listing every violation."""
    out: list[str] = []

    if replay.get("schema") != SCHEMA:
        out.append(f"$.schema: expected {SCHEMA!r}, got {replay.get('schema')!r}")

    _walk_keys(dict(replay), ALLOWLIST, "$", out)
    _walk_values(dict(replay), "$", out)

    label = replay.get("label")
    if label not in LABELS:
        out.append(f"$.label: expected one of {LABELS}, got {label!r}")

    seat_ids = {seat.get("id") for seat in replay.get("seats") or [] if isinstance(seat, dict)}
    for f_index, frame in enumerate(replay.get("frames") or []):
        if not isinstance(frame, dict):
            continue
        for p_index, piece in enumerate(frame.get("pieces") or []):
            where = f"$.frames[{f_index}].pieces[{p_index}]"
            if piece.get("kind") not in PIECE_KINDS:
                out.append(f"{where}.kind: expected one of {PIECE_KINDS}")
            if piece.get("seat") not in seat_ids:
                out.append(f"{where}.seat: {piece.get('seat')!r} is not a declared seat")
        for c_index, city in enumerate(frame.get("cities") or []):
            where = f"$.frames[{f_index}].cities[{c_index}]"
            occupied = city.get("occupied_by")
            if not isinstance(occupied, list):
                out.append(f"{where}.occupied_by: expected a list")
            elif any(seat not in seat_ids for seat in occupied):
                out.append(f"{where}.occupied_by: contains an undeclared seat")
            secured = city.get("secured_by")
            if secured is not None and secured not in seat_ids:
                out.append(f"{where}.secured_by: {secured!r} is not a declared seat")

    winner = (replay.get("result") or {}).get("winner_seat")
    if winner is not None and winner not in seat_ids:
        out.append(f"$.result.winner_seat: {winner!r} is not a declared seat")

    # An `official-gate` label claims the match came out of the 7,200-turn
    # gate AND is worth watching. The first half is the exporter's job; the
    # second half is checkable here, from the file alone.
    if label == "official-gate":
        bar = visual_bar(replay)
        if not bar["passes"]:
            out.append(
                "$.label: 'official-gate' on a match that fails the visual bar "
                f"(moves={bar['moves']}, territory_changes={bar['territory_changes']}); "
                "label it 'exhibition' or pick another match"
            )

    if out:
        raise LeakageError(out)


def validate_file(path: str | Path) -> dict:
    """Load a replay JSON, run the leakage test, return the parsed file."""
    with open(path, encoding="utf-8") as handle:
        replay = json.load(handle)
    validate(replay)
    return replay


__all__ = [
    "SCHEMA",
    "LABELS",
    "PIECE_KINDS",
    "ALLOWLIST",
    "LeakageError",
    "build",
    "frame_from_state",
    "sanitise_seat_label",
    "validate",
    "validate_file",
    "visual_bar",
    "_PieceRegistry",
]
