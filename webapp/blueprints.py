"""
Agent blueprints — the coach's agent as an owned, versioned object.

Phase 0 proved a model can play; its blueprint was a frozen file in
``configs/blueprints`` chosen on the command line. Phase 1 turns that file into
an entity a coach owns, edits, clones, freezes and retires, and that a match
can bind to by hash rather than by copying text.

Three parts of a version, kept apart on purpose:

* **strategic** — ``persona`` and ``doctrine``. This is the only part the model
  ever reads, and the only part a rival's result depends on.
* **runtime configuration** — ``runtime``: model, temperature, token ceiling.
  Not prompt text, but a different model plays a different game, so a result is
  only reproducible if this is pinned too.
* **editorial** — ``name``, ``notes``, ``state``, timestamps, ``visibility``.
  Bookkeeping for the coach. Deliberately outside the hash, so renaming a
  blueprint or writing a changelog does not invalidate a match already played
  against it.

The hash covers the first two, plus the blueprint id and version number. Two
versions with identical text therefore stay distinguishable, and so do a
blueprint and its clone: what a match inscribes is *this* version of *this*
agent, not "some text that reads like this".

Freezing is the line between the two lives of a version. A draft is the coach's
to change; a frozen version is nobody's, including the coach's and the
operator's. A match may only enroll a frozen version, and at every turn the
runtime re-derives the hash and refuses to play if it moved.

State lives in ``server_data/blueprints.json`` — one file, atomic writes, same
file-based ethos as the room and coach registries.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from webapp.coaches import Coach

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
BLUEPRINTS_FILE = SERVER_DATA / "blueprints.json"

#: Editorial state of one version.
STATE_DRAFT = "draft"
STATE_FROZEN = "frozen"

#: The strategic sections, in the order ``webapp.ai.context.doctrine_section``
#: renders them. A blueprint that names other keys does not get a louder voice:
#: unknown keys are dropped, so every agent is described on the same axes.
DOCTRINE_SECTIONS = ("objective", "economy", "risk", "diplomacy")

#: Runtime configuration keys and their coercions.
RUNTIME_DEFAULTS: dict[str, object] = {
    "model": "",
    "temperature": 0.0,
    "max_tokens": 1500,
}

#: Same cap the prompt renderer applies. Storing more would let a coach believe
#: text is in play that the model never sees.
MAX_SECTION_CHARS = 400
MAX_PERSONA_CHARS = 2000
MAX_NOTES_CHARS = 4000
MAX_NAME_CHARS = 80

VISIBILITY_PRIVATE = "private"
VISIBILITY_PUBLIC = "public"

_NAME_OK = re.compile(r"^[\w \-'.,:()/]+$", re.UNICODE)


class BlueprintRegistryError(RuntimeError):
    """The persisted blueprint registry cannot be trusted for startup."""


class BlueprintError(Exception):
    """A blueprint request cannot be honoured as asked."""


class BlueprintAccessError(BlueprintError):
    """This coach may not see or touch this blueprint."""


class BlueprintIntegrityError(BlueprintError):
    """A frozen version no longer hashes to what the match inscribed."""


# ======================================================================
# model
# ======================================================================


@dataclass
class BlueprintVersion:
    version: int
    state: str = STATE_DRAFT
    # strategic
    persona: str = ""
    doctrine: dict[str, str] = field(default_factory=dict)
    # runtime configuration
    runtime: dict = field(default_factory=dict)
    # editorial
    notes: str = ""
    created_at: str = ""
    frozen_at: str = ""
    content_hash: str = ""

    @property
    def frozen(self) -> bool:
        return self.state == STATE_FROZEN


@dataclass
class AgentBlueprint:
    id: str
    coach_id: str
    name: str
    visibility: str = VISIBILITY_PRIVATE
    created_at: str = ""
    updated_at: str = ""
    retired_at: str = ""
    versions: list[BlueprintVersion] = field(default_factory=list)

    @property
    def retired(self) -> bool:
        return bool(self.retired_at)

    def version(self, number: int) -> BlueprintVersion:
        for candidate in self.versions:
            if candidate.version == int(number):
                return candidate
        raise BlueprintError(f"Blueprint {self.id} has no version {number}.")

    def latest(self) -> BlueprintVersion:
        if not self.versions:
            raise BlueprintError(f"Blueprint {self.id} has no versions.")
        return max(self.versions, key=lambda v: v.version)

    def latest_frozen(self) -> BlueprintVersion | None:
        frozen = [v for v in self.versions if v.frozen]
        return max(frozen, key=lambda v: v.version) if frozen else None

    def readable_by(self, coach: Coach) -> bool:
        return coach.id == self.coach_id or self.visibility == VISIBILITY_PUBLIC

    def writable_by(self, coach: Coach) -> bool:
        return coach.id == self.coach_id


@dataclass(frozen=True)
class BlueprintRef:
    """What a match inscribes: which version, and what it hashed to.

    Holds no strategy text. The seat that plays this blueprint reads it back
    through :func:`resolve`, which will refuse a version that has moved.
    """

    blueprint_id: str
    version: int
    content_hash: str

    def as_dict(self) -> dict:
        return {
            "blueprint_id": self.blueprint_id,
            "version": self.version,
            "content_hash": self.content_hash,
        }


# ======================================================================
# hashing
# ======================================================================


def canonical_payload(blueprint_id: str, version: BlueprintVersion) -> dict:
    """The exact object the content hash is taken over.

    Only the strategic and runtime sections, plus the identity of the version
    itself. Editorial fields are absent by design.
    """
    return {
        "blueprint_id": blueprint_id,
        "version": int(version.version),
        "strategy": {
            "persona": version.persona,
            "doctrine": {key: version.doctrine.get(key, "") for key in DOCTRINE_SECTIONS},
        },
        "runtime": {key: version.runtime.get(key, RUNTIME_DEFAULTS[key]) for key in RUNTIME_DEFAULTS},
    }


def content_hash(blueprint_id: str, version: BlueprintVersion) -> str:
    """SHA-256 of the canonical payload.

    ``sort_keys`` and a fixed separator make this stable across processes and
    Python versions; ``ensure_ascii=False`` keeps a non-ASCII doctrine hashing
    to the same value as the text the model is shown.
    """
    canonical = json.dumps(
        canonical_payload(blueprint_id, version),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def runtime_blueprint(blueprint_id: str, version: BlueprintVersion) -> dict:
    """The prompt-facing shape, identical to a ``configs/blueprints`` file.

    ``webapp.ai.context.doctrine_section`` reads exactly these keys, so a
    store blueprint and a Phase 0 file blueprint render — and hash — the same.
    """
    return {
        "id": blueprint_id,
        "version": int(version.version),
        "doctrine": {key: version.doctrine.get(key, "") for key in DOCTRINE_SECTIONS},
    }


# ======================================================================
# validation
# ======================================================================


def clean_name(name: str) -> str:
    name = (name or "").strip()[:MAX_NAME_CHARS]
    if not name:
        raise BlueprintError("Give the blueprint a name.")
    if not _NAME_OK.fullmatch(name):
        raise BlueprintError("A blueprint name may not contain control or markup characters.")
    return name


def clean_doctrine(doctrine: dict | None) -> dict[str, str]:
    """Keep the known sections, as strings, capped at the rendered length."""
    source = doctrine if isinstance(doctrine, dict) else {}
    return {
        key: str(source.get(key, "") or "").strip()[:MAX_SECTION_CHARS]
        for key in DOCTRINE_SECTIONS
    }


def clean_runtime(runtime: dict | None) -> dict:
    source = runtime if isinstance(runtime, dict) else {}
    cleaned: dict = {}
    for key, default in RUNTIME_DEFAULTS.items():
        value = source.get(key, default)
        try:
            if isinstance(default, float):
                cleaned[key] = float(value)
            elif isinstance(default, int):
                cleaned[key] = int(value)
            else:
                cleaned[key] = str(value or "").strip()
        except (TypeError, ValueError):
            raise BlueprintError(f"Blueprint runtime field '{key}' is not a {type(default).__name__}.")
    if not 0.0 <= cleaned["temperature"] <= 2.0:
        raise BlueprintError("Blueprint temperature must be between 0.0 and 2.0.")
    if not 1 <= cleaned["max_tokens"] <= 32000:
        raise BlueprintError("Blueprint max_tokens must be between 1 and 32000.")
    return cleaned


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ======================================================================
# store
# ======================================================================


class BlueprintStore:
    """Thread-safe, file-backed registry of agent blueprints."""

    def __init__(self, path: Path = BLUEPRINTS_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._blueprints: dict[str, AgentBlueprint] = {}
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
            # A blueprint id is inscribed in played matches. Starting empty
            # would let a new blueprint take an id whose results already exist.
            raise BlueprintRegistryError(
                "The persisted blueprint registry is unreadable; restore a "
                "backup before starting."
            ) from exc
        for raw in data.get("blueprints", []):
            blueprint = _blueprint_from_dict(raw)
            if blueprint:
                self._blueprints[blueprint.id] = blueprint

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "blueprints": [asdict(b) for b in self._blueprints.values()],
            }
            tmp = self.path.with_name(
                f"{self.path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
            )
            try:
                tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                tmp.replace(self.path)
            finally:
                tmp.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------

    def get(self, coach: Coach, blueprint_id: str) -> AgentBlueprint:
        """A blueprint this coach may read.

        A private blueprint of another coach is reported as missing, not as
        forbidden: "403" on an id is itself a disclosure that the id exists.
        """
        with self._lock:
            blueprint = self._blueprints.get(blueprint_id)
            if not blueprint or not blueprint.readable_by(coach):
                raise BlueprintAccessError(f"No blueprint '{blueprint_id}'.")
            return blueprint

    def get_for_write(self, coach: Coach, blueprint_id: str) -> AgentBlueprint:
        blueprint = self.get(coach, blueprint_id)
        if not blueprint.writable_by(coach):
            raise BlueprintAccessError("This blueprint belongs to another coach.")
        return blueprint

    def owned_by(self, coach: Coach) -> list[AgentBlueprint]:
        with self._lock:
            return [b for b in self._blueprints.values() if b.coach_id == coach.id]

    def visible_to(self, coach: Coach) -> list[AgentBlueprint]:
        """The coach's own blueprints, plus everyone's public ones."""
        with self._lock:
            return [b for b in self._blueprints.values() if b.readable_by(coach)]

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def create(
        self,
        coach: Coach,
        name: str,
        *,
        persona: str = "",
        doctrine: dict | None = None,
        runtime: dict | None = None,
        notes: str = "",
        visibility: str = VISIBILITY_PRIVATE,
    ) -> AgentBlueprint:
        """A new blueprint owned by ``coach``, with version 1 as a draft."""
        name = clean_name(name)
        if visibility not in (VISIBILITY_PRIVATE, VISIBILITY_PUBLIC):
            raise BlueprintError("Visibility is 'private' or 'public'.")
        now = _now()
        with self._lock:
            blueprint = AgentBlueprint(
                id="bp_" + secrets.token_hex(8),
                coach_id=coach.id,
                name=name,
                visibility=visibility,
                created_at=now,
                updated_at=now,
                versions=[
                    BlueprintVersion(
                        version=1,
                        state=STATE_DRAFT,
                        persona=str(persona or "").strip()[:MAX_PERSONA_CHARS],
                        doctrine=clean_doctrine(doctrine),
                        runtime=clean_runtime(runtime),
                        notes=str(notes or "")[:MAX_NOTES_CHARS],
                        created_at=now,
                    )
                ],
            )
            self._blueprints[blueprint.id] = blueprint
            self.save()
            return blueprint

    def edit(
        self,
        coach: Coach,
        blueprint_id: str,
        version_number: int,
        *,
        persona: str | None = None,
        doctrine: dict | None = None,
        runtime: dict | None = None,
        notes: str | None = None,
        name: str | None = None,
        visibility: str | None = None,
    ) -> BlueprintVersion:
        """Change a version.

        Strategic and runtime fields are only editable while the version is a
        draft. Editorial fields — the blueprint's name, its visibility, the
        version's notes — stay editable after freezing, because they are
        outside the hash and no result depends on them.
        """
        with self._lock:
            blueprint = self.get_for_write(coach, blueprint_id)
            version = blueprint.version(version_number)
            content_change = persona is not None or doctrine is not None or runtime is not None
            if content_change and version.frozen:
                raise BlueprintError(
                    f"Version {version.version} of '{blueprint.name}' is frozen and "
                    "cannot be altered. Open a new version instead."
                )
            if persona is not None:
                version.persona = str(persona).strip()[:MAX_PERSONA_CHARS]
            if doctrine is not None:
                version.doctrine = clean_doctrine(doctrine)
            if runtime is not None:
                version.runtime = clean_runtime(runtime)
            if notes is not None:
                version.notes = str(notes)[:MAX_NOTES_CHARS]
            if name is not None:
                blueprint.name = clean_name(name)
            if visibility is not None:
                if visibility not in (VISIBILITY_PRIVATE, VISIBILITY_PUBLIC):
                    raise BlueprintError("Visibility is 'private' or 'public'.")
                blueprint.visibility = visibility
            blueprint.updated_at = _now()
            self.save()
            return version

    def freeze(self, coach: Coach, blueprint_id: str, version_number: int) -> BlueprintVersion:
        """Seal a draft and give it its content hash.

        Freezing twice is not an error and does not re-hash: the second call
        returns the version already sealed, so a retried request cannot change
        what a match inscribed.
        """
        with self._lock:
            blueprint = self.get_for_write(coach, blueprint_id)
            version = blueprint.version(version_number)
            if version.frozen:
                return version
            version.content_hash = content_hash(blueprint.id, version)
            version.state = STATE_FROZEN
            version.frozen_at = _now()
            blueprint.updated_at = version.frozen_at
            self.save()
            return version

    def new_version(
        self, coach: Coach, blueprint_id: str, *, from_version: int | None = None
    ) -> BlueprintVersion:
        """Open a new draft version, copying an existing one's content.

        The way to change a frozen agent: the old version stays exactly as it
        was played, and the new one starts from its text.
        """
        with self._lock:
            blueprint = self.get_for_write(coach, blueprint_id)
            if blueprint.retired:
                raise BlueprintError(f"'{blueprint.name}' is retired.")
            source = (
                blueprint.version(from_version)
                if from_version is not None
                else blueprint.latest()
            )
            if not source.frozen and source.version == blueprint.latest().version:
                raise BlueprintError(
                    f"Version {source.version} is still a draft; edit it instead of "
                    "opening another."
                )
            now = _now()
            version = BlueprintVersion(
                version=blueprint.latest().version + 1,
                state=STATE_DRAFT,
                persona=source.persona,
                doctrine=dict(source.doctrine),
                runtime=dict(source.runtime),
                notes=source.notes,
                created_at=now,
            )
            blueprint.versions.append(version)
            blueprint.updated_at = now
            self.save()
            return version

    def clone(
        self,
        coach: Coach,
        blueprint_id: str,
        *,
        from_version: int | None = None,
        name: str = "",
    ) -> AgentBlueprint:
        """Copy a readable blueprint into a new one owned by ``coach``.

        The copy starts at version 1, as a draft, and is private whatever the
        source was: cloning somebody's public agent does not republish it.
        """
        with self._lock:
            source_bp = self.get(coach, blueprint_id)
            source = (
                source_bp.version(from_version)
                if from_version is not None
                else (source_bp.latest_frozen() or source_bp.latest())
            )
            return self.create(
                coach,
                name or f"{source_bp.name} (copy)",
                persona=source.persona,
                doctrine=dict(source.doctrine),
                runtime=dict(source.runtime),
                notes=source.notes,
            )

    def retire(self, coach: Coach, blueprint_id: str) -> AgentBlueprint:
        """Take a blueprint out of circulation.

        Retiring is not deleting. Matches already played against a version keep
        resolving it, so a league's record stays readable; what stops is new
        enrollment.
        """
        with self._lock:
            blueprint = self.get_for_write(coach, blueprint_id)
            if not blueprint.retired:
                blueprint.retired_at = _now()
                blueprint.updated_at = blueprint.retired_at
                self.save()
            return blueprint

    # ------------------------------------------------------------------
    # binding a version to a match
    # ------------------------------------------------------------------

    def enroll(self, coach: Coach, blueprint_id: str, version_number: int | None = None) -> BlueprintRef:
        """The reference a seat records: id, version, hash. No text.

        Only a frozen version of a live blueprint may be enrolled — a draft
        could change under a running match, and that is exactly what the hash
        exists to prevent.
        """
        with self._lock:
            blueprint = self.get(coach, blueprint_id)
            if blueprint.retired:
                raise BlueprintError(f"'{blueprint.name}' is retired and cannot be entered.")
            version = (
                blueprint.version(version_number)
                if version_number is not None
                else blueprint.latest_frozen()
            )
            if version is None:
                raise BlueprintError(f"'{blueprint.name}' has no frozen version to enter.")
            if not version.frozen:
                raise BlueprintError(
                    f"Version {version.version} of '{blueprint.name}' is a draft. "
                    "Freeze it before entering a match."
                )
            return BlueprintRef(blueprint.id, version.version, version.content_hash)

    def resolve(self, ref: BlueprintRef) -> BlueprintVersion:
        """Read back an enrolled version, or refuse.

        This is the runtime's side of the contract: the seat plays the hash the
        match inscribed, not whatever now sits under that id and number. The
        hash is recomputed rather than compared to the stored one, so a version
        edited straight in ``blueprints.json`` is caught too.
        """
        with self._lock:
            blueprint = self._blueprints.get(ref.blueprint_id)
            if not blueprint:
                raise BlueprintIntegrityError(
                    f"Blueprint '{ref.blueprint_id}' entered in this match is gone."
                )
            try:
                version = blueprint.version(ref.version)
            except BlueprintError as exc:
                raise BlueprintIntegrityError(str(exc)) from exc
            actual = content_hash(blueprint.id, version)
            if not secrets.compare_digest(actual, ref.content_hash or ""):
                raise BlueprintIntegrityError(
                    f"Blueprint '{blueprint.id}' v{version.version} no longer matches "
                    f"the hash entered in this match (entered={ref.content_hash[:12]}, "
                    f"current={actual[:12]})."
                )
            return version


# ======================================================================
# migration
# ======================================================================


def migrate_personas(coach: Coach, *, store: "BlueprintStore | None" = None) -> list[dict]:
    """Lift every seat's free-text persona into a blueprint owned by ``coach``.

    Before Phase 1 a seat's agent *was* its ``AgentProfile``: a persona string,
    a model and a temperature, living inside one room and dying with it. This
    gives each of those an object of its own — persona as the strategic
    section, model and temperature as the runtime section — freezes version 1
    so the seat keeps playing exactly the text it was playing, and enrolls it.

    The profile's ``persona`` is cleared once the seat is enrolled: leaving it
    would give the same seat two sources of strategy that could later disagree.
    Seats already carrying a blueprint, and seats with no persona at all, are
    left alone, so running this twice changes nothing the second time.
    """
    from webapp.ai.registry import default_registry

    store = store or default_store()
    registry = default_registry()
    migrated: list[dict] = []
    with registry.transaction():  # one pass, no seat changing under us
        for room_code, factions in registry.all_profiles().items():
            for faction_id, profile in factions.items():
                if profile.blueprint_id or not profile.persona.strip():
                    continue
                blueprint = store.create(
                    coach,
                    f"{room_code} {faction_id}",
                    persona=profile.persona,
                    runtime={
                        "model": profile.model,
                        "temperature": max(0.0, min(2.0, float(profile.temperature or 0.0))),
                    },
                    notes=(
                        f"Migrated from the {room_code} agent profile for {faction_id}."
                    ),
                )
                version = store.freeze(coach, blueprint.id, 1)
                profile.blueprint_id = blueprint.id
                profile.blueprint_version = version.version
                profile.blueprint_hash = version.content_hash
                profile.persona = ""
                migrated.append(
                    {
                        "room_code": room_code,
                        "faction_id": faction_id,
                        "blueprint_id": blueprint.id,
                        "version": version.version,
                        "content_hash": version.content_hash,
                    }
                )
        if migrated:
            registry.save()
    return migrated


_store: BlueprintStore | None = None


def default_store() -> BlueprintStore:
    global _store
    if _store is None:
        _store = BlueprintStore()
    return _store


def _blueprint_from_dict(raw: dict) -> AgentBlueprint | None:
    try:
        raw = dict(raw)
        versions = [BlueprintVersion(**v) for v in raw.pop("versions", [])]
        blueprint = AgentBlueprint(**raw)
        blueprint.versions = versions
        return blueprint
    except (AttributeError, TypeError, KeyError, ValueError):
        return None
