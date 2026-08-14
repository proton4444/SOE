"""
Closed Coach Alpha — invite a field, measure whether they iterate.

Phase 3 can run a league. This phase asks whether people will come back and
change a doctrine. The answers are rates, not features: activation, iteration,
completion, return, a concrete willingness to pay or bring a key, and whether
anyone shared a result without being asked.

The go criteria live in ``configs/alpha/closed.json``. This module does not
declare them passed. It keeps the roster, the three-training cap, the share
link, the pay/key choice, and a funnel anyone can recompute from the ledger.

There is no permanent ranking. A season table is that season. A final is one
observable match, not a rating.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import statistics
import threading
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from webapp.coaches import Coach

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
LEDGER_FILE = SERVER_DATA / "alpha.json"
FORMAT_FILE = _REPO_ROOT / "configs" / "alpha" / "closed.json"

STATUS_IDLE = "idle"
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"

INTENT_PAY = "pay"
INTENT_BYOK = "byok"
_INTENTS = {INTENT_PAY, INTENT_BYOK}


class AlphaRegistryError(RuntimeError):
    """The persisted alpha ledger cannot be trusted for startup."""


class AlphaError(Exception):
    """An alpha request cannot be honoured as asked."""


@dataclass(frozen=True)
class Format:
    id: str
    name: str
    capacity: int
    minimum_invites: int
    training_per_version: int
    gates: dict


def load_format() -> Format:
    try:
        data = json.loads(FORMAT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AlphaRegistryError(f"The alpha format is unreadable: {FORMAT_FILE}") from exc
    gates = dict(data.get("gates") or {})
    return Format(
        id=str(data.get("id") or "closed_alpha"),
        name=str(data.get("name") or "Closed Coach Alpha"),
        capacity=int(data.get("capacity") or 30),
        minimum_invites=int(data.get("minimum_invites") or 20),
        training_per_version=int(data.get("training_per_version") or 3),
        gates={
            "activation": float(gates.get("activation", 0.6)),
            "iteration": float(gates.get("iteration", 0.4)),
            "match_completion": float(gates.get("match_completion", 0.9)),
            "return": float(gates.get("return", 0.3)),
            "willingness": float(gates.get("willingness", 0.2)),
            "sharing": float(gates.get("sharing", 0.25)),
        },
    )


@dataclass
class Invite:
    id: str
    name: str
    code_sha256: str
    created_at: str
    claimed_by: str = ""
    claimed_at: str = ""


@dataclass
class Intent:
    coach_id: str
    kind: str
    at: str
    source: str = ""


@dataclass
class Share:
    token: str
    coach_id: str
    run_id: str
    created_at: str


@dataclass
class AlphaState:
    status: str = STATUS_IDLE
    opened_at: str = ""
    closed_at: str = ""
    invites: list[Invite] = field(default_factory=list)
    intents: list[Intent] = field(default_factory=list)
    shares: list[Share] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _from_dict(cls, raw: dict):
    allowed = {item.name for item in fields(cls)}
    return cls(**{key: value for key, value in raw.items() if key in allowed})


class AlphaStore:
    """Thread-safe, file-backed roster for the closed alpha."""

    def __init__(self, path: Path = LEDGER_FILE, fmt: Format | None = None):
        self.path = path
        self.format = fmt or load_format()
        self._lock = threading.RLock()
        self._state = AlphaState()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise AlphaRegistryError(
                "The persisted alpha ledger is unreadable; restore a backup "
                "before starting."
            ) from exc
        self._state = AlphaState(
            status=str(data.get("status") or STATUS_IDLE),
            opened_at=str(data.get("opened_at") or ""),
            closed_at=str(data.get("closed_at") or ""),
            invites=[_from_dict(Invite, raw) for raw in data.get("invites", []) if isinstance(raw, dict)],
            intents=[_from_dict(Intent, raw) for raw in data.get("intents", []) if isinstance(raw, dict)],
            shares=[_from_dict(Share, raw) for raw in data.get("shares", []) if isinstance(raw, dict)],
        )

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": self._state.status,
                "opened_at": self._state.opened_at,
                "closed_at": self._state.closed_at,
                "invites": [asdict(item) for item in self._state.invites],
                "intents": [asdict(item) for item in self._state.intents],
                "shares": [asdict(item) for item in self._state.shares],
            }
            tmp = self.path.with_name(
                f"{self.path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
            )
            try:
                tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            finally:
                tmp.unlink(missing_ok=True)

    def is_open(self) -> bool:
        return self._state.status == STATUS_OPEN

    def status(self) -> str:
        return self._state.status

    def invites(self) -> list[Invite]:
        with self._lock:
            return list(self._state.invites)

    def claimed(self) -> list[Invite]:
        return [item for item in self.invites() if item.claimed_by]

    def claimed_by(self, coach_id: str) -> Invite | None:
        for item in self.invites():
            if item.claimed_by == coach_id:
                return item
        return None

    def open(self) -> None:
        with self._lock:
            if self._state.status == STATUS_OPEN:
                return
            self._state.status = STATUS_OPEN
            self._state.opened_at = _now()
            self._state.closed_at = ""
            self.save()

    def close(self) -> None:
        with self._lock:
            self._state.status = STATUS_CLOSED
            self._state.closed_at = _now()
            self.save()

    def issue(self, name: str) -> tuple[Invite, str]:
        name = (name or "").strip()[:64]
        if not name:
            raise AlphaError("Give the invitee a name.")
        with self._lock:
            if len(self._state.invites) >= self.format.capacity:
                raise AlphaError(
                    f"The alpha is full ({self.format.capacity} invitations)."
                )
            code = "inv_" + secrets.token_hex(8)
            invite = Invite(
                id="in_" + secrets.token_hex(8),
                name=name,
                code_sha256=_digest(code),
                created_at=_now(),
            )
            self._state.invites.append(invite)
            self.save()
            return invite, code

    def peek(self, code: str) -> Invite:
        digest = _digest((code or "").strip())
        with self._lock:
            for item in self._state.invites:
                if secrets.compare_digest(item.code_sha256, digest):
                    if item.claimed_by:
                        raise AlphaError("That invitation has already been used.")
                    return item
        raise AlphaError("That invitation is not recognised.")

    def claim(self, code: str, coach: Coach) -> Invite:
        if not self.is_open():
            raise AlphaError("The closed alpha is not open for registration.")
        if self.claimed_by(coach.id):
            raise AlphaError("This coach already used an invitation.")
        invite = self.peek(code)
        with self._lock:
            invite.claimed_by = coach.id
            invite.claimed_at = _now()
            self.save()
            return invite

    def record_intent(self, coach: Coach, kind: str, *, source: str = "") -> Intent:
        kind = (kind or "").strip()
        if kind not in _INTENTS:
            raise AlphaError("Choose 'pay' or 'byok'.")
        with self._lock:
            self._state.intents = [
                item for item in self._state.intents if item.coach_id != coach.id
            ]
            intent = Intent(coach_id=coach.id, kind=kind, at=_now(), source=source)
            self._state.intents.append(intent)
            self.save()
            return intent

    def intent_for(self, coach: Coach) -> Intent | None:
        for item in self._state.intents:
            if item.coach_id == coach.id:
                return item
        return None

    def share(self, coach: Coach, run_id: str) -> Share:
        token = "sh_" + secrets.token_hex(8)
        with self._lock:
            existing = next(
                (
                    item
                    for item in self._state.shares
                    if item.coach_id == coach.id and item.run_id == run_id
                ),
                None,
            )
            if existing:
                return existing
            item = Share(
                token=token, coach_id=coach.id, run_id=run_id, created_at=_now()
            )
            self._state.shares.append(item)
            self.save()
            return item

    def share_for(self, coach: Coach, run_id: str) -> Share | None:
        with self._lock:
            for item in self._state.shares:
                if item.coach_id == coach.id and item.run_id == run_id:
                    return item
        return None

    def share_by_token(self, token: str) -> Share:
        with self._lock:
            for item in self._state.shares:
                if item.token == token:
                    return item
        raise AlphaError("No shared result with that link.")


def version_limit_for(coach: Coach) -> int | None:
    """Three trainings per version for an invited coach. None means use the default."""
    try:
        store = default_store()
    except AlphaRegistryError:
        return None
    if store.claimed_by(coach.id):
        return store.format.training_per_version
    return None


def funnel(
    alpha: AlphaStore,
    *,
    coaches=None,
    blueprints=None,
    training=None,
    competition=None,
) -> dict:
    """The eight Phase 4 numbers, each recomputable from the stores."""
    issued = alpha.invites()
    claimed = alpha.claimed()
    claimed_ids = {item.claimed_by for item in claimed}
    activated_ids: set[str] = set()
    iterated_ids: set[str] = set()
    freeze_waits: list[float] = []

    if blueprints is not None:
        for coach_id in claimed_ids:
            coach = _coach(coaches, coach_id)
            owned = blueprints.owned_by(coach) if coach is not None else []
            first_freeze = None
            for item in owned:
                frozen = item.latest_frozen()
                if frozen is None:
                    continue
                activated_ids.add(coach_id)
                stamp = frozen.frozen_at or frozen.created_at
                if stamp and (first_freeze is None or stamp < first_freeze):
                    first_freeze = stamp
            if first_freeze and coach and coach.created_at:
                wait = _seconds(coach.created_at, first_freeze)
                if wait is not None:
                    freeze_waits.append(wait)

        if training is not None:
            for coach_id in activated_ids:
                coach = _coach(coaches, coach_id)
                if coach is None:
                    continue
                runs = [
                    run
                    for run in training.for_coach(coach)
                    if run.status == "complete" and run.finished_at
                ]
                if not runs:
                    continue
                first = min(runs, key=lambda run: run.finished_at)
                for item in blueprints.owned_by(coach):
                    for version in item.versions:
                        if (
                            version.version > first.blueprint_version
                            and (version.created_at or "") >= first.finished_at
                        ):
                            iterated_ids.add(coach_id)

    trained_ids: set[str] = set()
    if training is not None:
        for invite in claimed:
            coach = _coach(coaches, invite.claimed_by)
            if coach is None:
                continue
            if any(run.status == "complete" for run in training.for_coach(coach)):
                trained_ids.add(coach.id)

    returned_ids: set[str] = set()
    match_total = 0
    match_complete = 0
    cost_values: list[float] = []
    if competition is not None:
        seasons = competition.seasons()
        by_coach: dict[str, set[str]] = {}
        for season in seasons:
            for entry in competition.entries(season.id):
                by_coach.setdefault(entry.coach_id, set()).add(season.id)
            from webapp.competition import completion

            report = completion(competition, season.id)
            match_total += int(report["total"])
            match_complete += int(report["complete"])
            for match in competition.matches(season.id):
                usd = _match_cost(match)
                if usd is not None:
                    cost_values.append(usd)
        returned_ids = {coach_id for coach_id, seen in by_coach.items() if len(seen) >= 2}

    willing = {item.coach_id for item in alpha._state.intents if item.kind in _INTENTS}
    shared = {item.coach_id for item in alpha._state.shares}

    invited_n = len(issued)
    claimed_n = len(claimed)
    trained_n = len(trained_ids) or len(activated_ids)
    rates = {
        "activation": _rate(len(activated_ids), invited_n),
        "iteration": _rate(len(iterated_ids), len(trained_ids) or len(activated_ids)),
        "match_completion": _rate(match_complete, match_total),
        "return": _rate(len(returned_ids), claimed_n),
        "willingness": _rate(len(willing & claimed_ids), claimed_n),
        "sharing": _rate(len(shared & claimed_ids), claimed_n),
    }
    gates = alpha.format.gates
    return {
        "status": alpha.status(),
        "issued": invited_n,
        "claimed": claimed_n,
        "activated": len(activated_ids),
        "iterated": len(iterated_ids),
        "trained": trained_n,
        "returned": len(returned_ids),
        "willing": len(willing & claimed_ids),
        "shared": len(shared & claimed_ids),
        "matches": {"complete": match_complete, "total": match_total},
        "cost_per_match": (
            round(sum(cost_values) / len(cost_values), 6) if cost_values else None
        ),
        "median_seconds_to_freeze": (
            statistics.median(freeze_waits) if freeze_waits else None
        ),
        "rates": rates,
        "gates": gates,
        "verdict": {
            key: {
                "value": rates[key],
                "gate": gates[key],
                "pass": rates[key] is not None and rates[key] >= gates[key],
            }
            for key in gates
        },
    }


def _coach(store, coach_id: str):
    if store is None:
        return None
    getter = getattr(store, "get", None)
    if callable(getter):
        return getter(coach_id)
    return None


def _rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return num / den


def _seconds(start: str, end: str) -> float | None:
    try:
        a = datetime.fromisoformat(start)
        b = datetime.fromisoformat(end)
    except (TypeError, ValueError):
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return max(0.0, (b - a).total_seconds())


def _match_cost(match) -> float | None:
    if not getattr(match, "run_dir", ""):
        return None
    root = Path(match.run_dir)
    for path in (root.parent / "arena_results.json", root / "arena_results.json"):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        reliability = data.get("reliability") or {}
        total = 0.0
        found = False
        if isinstance(reliability, dict):
            for value in reliability.values():
                if isinstance(value, dict) and value.get("cost") is not None:
                    total += float(value["cost"])
                    found = True
        if found:
            return total
    return None


def public_card(run, view, *, blueprint_name: str) -> dict:
    """What a shared link may say: outcome, cost, version. No opponent orders."""
    from webapp import coach_ui

    error = coach_ui.main_error(view.errors)
    return {
        "blueprint": blueprint_name,
        "version": run.blueprint_version,
        "outcome": coach_ui.outcome_line(view.headline),
        "cost": coach_ui.cost_line(view.cost),
        "main_error": error["title"],
        "notice": "This season's result. Not a ranking.",
    }


_store: AlphaStore | None = None


def default_store() -> AlphaStore:
    global _store
    if _store is None:
        _store = AlphaStore()
    return _store
