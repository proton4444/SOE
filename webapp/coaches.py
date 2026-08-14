"""
Coach identity — the minimal account an agent blueprint belongs to.

Phase 0 had no owner: a blueprint was a file in ``configs/blueprints`` and
whoever ran the arena owned all of them. Phase 1 makes the blueprint an object
somebody holds, so it needs somebody to hold it. This is the smallest identity
that supports that: a name, an id, and a key.

A coach key is a bearer credential, like the room host key and the seat agent
key. Unlike those it is stored hashed: rooms are short-lived link games, but a
coach account outlives every room it plays in, and its key unlocks every
blueprint the coach owns. Only the SHA-256 is persisted, so a leaked
``coaches.json`` does not hand over the accounts.

State lives in ``server_data/coaches.json`` — one file, atomic writes, same
file-based ethos as the room and agent registries.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
COACHES_FILE = SERVER_DATA / "coaches.json"

#: Long enough that guessing is not a strategy, short enough to paste.
_KEY_BYTES = 24
MAX_DISPLAY_NAME = 64


class CoachRegistryError(RuntimeError):
    """The persisted coach registry cannot be trusted for startup."""


class CoachError(Exception):
    """A coach request cannot be honoured as asked."""


class CoachAuthError(CoachError):
    """The presented key belongs to no coach."""


@dataclass
class Coach:
    id: str
    display_name: str
    key_sha256: str
    created_at: str


def key_digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class CoachStore:
    """Thread-safe, file-backed registry of coach accounts."""

    def __init__(self, path: Path = COACHES_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._coaches: dict[str, Coach] = {}
        # key_sha256 -> coach_id, so authentication is a lookup, not a scan.
        self._by_digest: dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            # Starting empty would orphan every blueprint on disk and let a
            # new account claim an id that is already inscribed in a match.
            raise CoachRegistryError(
                "The persisted coach registry is unreadable; restore a backup "
                "before starting."
            ) from exc
        for raw in data.get("coaches", []):
            try:
                coach = Coach(**raw)
            except TypeError:
                continue
            self._coaches[coach.id] = coach
            self._by_digest[coach.key_sha256] = coach.id

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"coaches": [asdict(c) for c in self._coaches.values()]}
            tmp = self.path.with_name(
                f"{self.path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
            )
            try:
                tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            finally:
                tmp.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def get(self, coach_id: str) -> Coach | None:
        with self._lock:
            return self._coaches.get(coach_id)

    def all(self) -> list[Coach]:
        with self._lock:
            return list(self._coaches.values())

    def authenticate(self, key: str) -> Coach | None:
        """The coach holding ``key``, or None."""
        if not key:
            return None
        with self._lock:
            coach_id = self._by_digest.get(key_digest(key))
            return self._coaches.get(coach_id) if coach_id else None

    def require(self, key: str) -> Coach:
        coach = self.authenticate(key)
        if not coach:
            raise CoachAuthError("Unknown coach key.")
        return coach

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def create(self, display_name: str) -> tuple[Coach, str]:
        """Register a coach. Returns the account and its key, shown once."""
        display_name = (display_name or "").strip()[:MAX_DISPLAY_NAME]
        if not display_name:
            raise CoachError("Give the coach a name.")
        with self._lock:
            key = "coach_" + secrets.token_hex(_KEY_BYTES)
            coach = Coach(
                id="c_" + secrets.token_hex(8),
                display_name=display_name,
                key_sha256=key_digest(key),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._coaches[coach.id] = coach
            self._by_digest[coach.key_sha256] = coach.id
            self.save()
            return coach, key


_store: CoachStore | None = None


def default_store() -> CoachStore:
    global _store
    if _store is None:
        _store = CoachStore()
    return _store
