"""
Agent registry — managed AI players for the war-room dashboard.

A room slot is played by a human or an external agent (seat holders, tracked in
``rooms.json``). A faction may additionally carry an *agent profile* here that
says **how** that seat plays: model, persona, temperature, enablement, and the
orchestrator's runtime state. Profiles are not credentials — the seat holder's
key still authorises orders.

State lives in ``server_data/agents.json`` — one file, atomic writes, same
file-based ethos as the room registry.
"""

from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
AGENTS_FILE = SERVER_DATA / "agents.json"

DEFAULT_MODEL = os.environ.get("SOE_LLM_MODEL", "").strip()

# Orchestrator states, in lifecycle order.
STATE_IDLE = "idle"
STATE_THINKING = "thinking"
STATE_SUBMITTED = "submitted"
STATE_DONE = "done"
STATE_ERROR = "error"


class AgentRegistryError(RuntimeError):
    """The persisted agent registry cannot be trusted for startup."""


@dataclass
class AgentProfile:
    model: str = DEFAULT_MODEL
    persona: str = ""
    temperature: float = 0.0
    enabled: bool = False
    state: str = STATE_IDLE
    last_error: str = ""
    last_run_at: str = ""
    # The frozen blueprint version this seat entered the match with: id,
    # number and hash, never the text. The seat reads the strategy back
    # through ``webapp.blueprints.resolve``, which refuses a version that has
    # moved since. Empty means the pre-Phase-1 arrangement, where ``persona``
    # and ``model`` on this profile are themselves the agent.
    blueprint_id: str = ""
    blueprint_version: int = 0
    blueprint_hash: str = ""

    def blueprint_ref(self):
        """The enrolled reference, or None for a seat with no blueprint."""
        if not self.blueprint_id:
            return None
        from webapp.blueprints import BlueprintRef

        return BlueprintRef(self.blueprint_id, self.blueprint_version, self.blueprint_hash)


class AgentRegistry:
    """Thread-safe, file-backed registry of per-faction agent profiles."""

    def __init__(self, path: Path = AGENTS_FILE):
        self.path = path
        self._lock = threading.RLock()
        # room_code -> {faction_id: AgentProfile}
        self._profiles: dict[str, dict[str, AgentProfile]] = {}
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
            raise AgentRegistryError(
                "The persisted agent registry is unreadable; restore a backup before starting."
            ) from exc
        for room_code, factions in data.get("agents", {}).items():
            for faction_id, raw in factions.items():
                self._profiles.setdefault(room_code, {})[faction_id] = AgentProfile(
                    **raw
                )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "agents": {
                room_code: {
                    faction_id: asdict(profile)
                    for faction_id, profile in factions.items()
                }
                for room_code, factions in self._profiles.items()
            },
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self):
        """Serialise a read-modify-write of the registry with its own save.

        Same reason as ``RoomStore.transaction``: sync FastAPI routes run in a
        threadpool, so two seats can be reconfigured at once.
        """
        with self._lock:
            yield self

    def get(self, room_code: str, faction_id: str) -> AgentProfile | None:
        with self._lock:
            return self._profiles.get(room_code.upper(), {}).get(faction_id)

    def all_profiles(self) -> dict[str, dict[str, AgentProfile]]:
        """Every seat profile, keyed room code -> faction id.

        The profiles are the live objects, not copies: a caller holding
        ``transaction()`` may edit them and then ``save()``.
        """
        with self._lock:
            return {code: dict(factions) for code, factions in self._profiles.items()}

    def for_room(self, room_code: str) -> dict[str, AgentProfile]:
        with self._lock:
            return dict(self._profiles.get(room_code.upper(), {}))

    def is_bot(self, room_code: str, faction_id: str) -> bool:
        profile = self.get(room_code, faction_id)
        return bool(profile and profile.enabled)

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def set(
        self,
        room_code: str,
        faction_id: str,
        profile: AgentProfile,
    ) -> AgentProfile:
        with self._lock:
            self._profiles.setdefault(room_code.upper(), {})[faction_id] = profile
            self.save()
            return profile

    def enroll_blueprint(self, room_code: str, faction_id: str, ref) -> AgentProfile:
        """Bind a seat to a frozen blueprint version, or clear the binding.

        ``ref`` is a ``webapp.blueprints.BlueprintRef``, or None to go back to
        the profile's own persona and model. The seat must already have a
        profile: enrolling an agent is a change to how a seat plays, not a way
        to create one.
        """
        with self._lock:
            profile = self.get(room_code, faction_id)
            if profile is None:
                raise KeyError(f"No agent profile for {faction_id} in room {room_code}.")
            profile.blueprint_id = ref.blueprint_id if ref else ""
            profile.blueprint_version = ref.version if ref else 0
            profile.blueprint_hash = ref.content_hash if ref else ""
            self._profiles[room_code.upper()][faction_id] = profile
            self.save()
            return profile

    def delete(self, room_code: str, faction_id: str) -> bool:
        with self._lock:
            factions = self._profiles.get(room_code.upper())
            if not factions or faction_id not in factions:
                return False
            del factions[faction_id]
            if not factions:
                self._profiles.pop(room_code.upper(), None)
            self.save()
            return True


_registry: AgentRegistry | None = None


def default_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
