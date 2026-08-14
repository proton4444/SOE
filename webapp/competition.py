"""
Coach League control plane — official matches, resume, verifiable standings.

Phase 2 closed the private loop: create, try, understand, change. This is the
public one: a frozen regulation, specific blueprint versions, pairings that
swap seats, a job queue that survives a restart, and a table anyone can
recompute from the match records.

**An official match is an arena run.** Training already made that choice, and
the reason is the same: the arena persists the manifest, the decisions, the
orders, the errors and the final hashes, and it resumes. A second runner would
be a second, weaker record. This module decides *who may meet whom under what
rules*, and hands the rest to ``scripts.arena``.

**The regulation travels by hash.** Model, budget, map, turns, seed pairs,
retries and tools are copied from a catalogue when the season is opened and
frozen with it. A match always plays those values, never the coach's runtime
overrides. Vision and subagents stay off: Coach League measures the doctrine,
not the orchestration.

**One pairing is one seat-swapped batch.** Start-city luck dominates a single
game. The arena already plays every seed as a pair with the seats exchanged;
the control plane does not invent a second kind of pairing on top.

State lives in ``server_data/competitions.json``. Evidence lives under
``games/competition/<season_id>/<match_id>/``.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

from webapp import blueprints as blueprints_mod
from webapp.blueprints import BlueprintError, BlueprintRef
from webapp.coaches import Coach

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
GAMES_ROOT = Path(os.environ.get("SOE_GAMES_DIR", str(_REPO_ROOT / "games")))
LEDGER_FILE = SERVER_DATA / "competitions.json"
MATCHES_ROOT = GAMES_ROOT / "competition"
CATALOGUE_DIR = _REPO_ROOT / "configs" / "competition"

COMPETITION_COACH_LEAGUE = "coach_league"

STATUS_DRAFT = "draft"
STATUS_FROZEN = "frozen"
STATUS_SEALED = "sealed"
STATUS_COMPLETE = "complete"
STATUS_SUSPENDED = "suspended"

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_COMPLETE = "complete"
JOB_FAILED = "failed"
JOB_SUSPENDED = "suspended"

_TERMINAL_JOB = {JOB_COMPLETE, JOB_FAILED, JOB_SUSPENDED}
_LIVE_SEASON = {STATUS_FROZEN, STATUS_SEALED}


class CompetitionRegistryError(RuntimeError):
    """The persisted league ledger cannot be trusted for startup."""


class CompetitionError(Exception):
    """A league request cannot be honoured as asked."""


class CompetitionIntegrityError(CompetitionError):
    """A frozen regulation or enrolled hash no longer matches the record."""


# ======================================================================
# regulation
# ======================================================================


@dataclass(frozen=True)
class Regulation:
    """What every official match in a season is played under.

    Frozen with the season. A coach's blueprint may name a model or a token
    ceiling; the match ignores those and uses these.
    """

    model: str
    temperature: float = 0.0
    max_tokens: int = 1500
    map: str = "calib_12.json"
    turns: int = 30
    seed_pairs: int = 1
    max_spend_usd: float = 0.30
    max_retries: int = 1
    timeout_s: int = 7200
    max_concurrent: int = 1
    redact_reasoning: bool = True
    allow_vision: bool = False
    allow_subagents: bool = False


def regulation_from_mapping(data: dict | None) -> Regulation:
    source = data if isinstance(data, dict) else {}
    allowed = {item.name for item in fields(Regulation)}
    return Regulation(
        **{key: value for key, value in source.items() if key in allowed}  # type: ignore[arg-type]
    )


def regulation_payload(regulation: Regulation) -> dict:
    return asdict(regulation)


def regulation_hash(regulation: Regulation | dict) -> str:
    payload = (
        regulation_payload(regulation)
        if isinstance(regulation, Regulation)
        else regulation_payload(regulation_from_mapping(regulation))
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_catalogues() -> dict[str, dict]:
    catalogues: dict[str, dict] = {}
    if not CATALOGUE_DIR.exists():
        return catalogues
    for path in sorted(CATALOGUE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CompetitionRegistryError(
                f"The competition catalogue is unreadable: {path}"
            ) from exc
        if not isinstance(data, dict) or not data.get("id"):
            continue
        catalogues[str(data["id"])] = data
    return catalogues


_catalogues: dict[str, dict] | None = None


def catalogues() -> dict[str, dict]:
    global _catalogues
    if _catalogues is None:
        _catalogues = _load_catalogues()
    return _catalogues


def catalogue(catalogue_id: str) -> dict:
    try:
        return catalogues()[catalogue_id]
    except KeyError:
        known = ", ".join(sorted(catalogues())) or "(none)"
        raise CompetitionError(
            f"Unknown competition '{catalogue_id}'. Choose one of: {known}."
        )


# ======================================================================
# records
# ======================================================================


@dataclass
class Season:
    id: str
    competition: str
    name: str
    status: str
    regulation: dict
    regulation_hash: str = ""
    created_at: str = ""
    frozen_at: str = ""
    sealed_at: str = ""
    completed_at: str = ""
    suspended_at: str = ""
    suspend_reason: str = ""
    final_match_id: str = ""

    def rules(self) -> Regulation:
        return regulation_from_mapping(self.regulation)


@dataclass
class Entry:
    id: str
    season_id: str
    coach_id: str
    blueprint_id: str
    blueprint_version: int
    blueprint_hash: str
    name: str
    entered_at: str
    withdrawn: bool = False

    def label(self) -> str:
        return f"{self.blueprint_id}_v{self.blueprint_version}"


@dataclass
class Match:
    id: str
    season_id: str
    left_entry_id: str
    right_entry_id: str
    left_label: str
    right_label: str
    status: str = JOB_QUEUED
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    run_id: str = ""
    run_dir: str = ""
    error: str = ""
    result: dict = field(default_factory=dict)

    def bundle_dir(self) -> Path:
        return Path(self.run_dir) if self.run_dir else MATCHES_ROOT / self.season_id / self.id


@dataclass
class Job:
    id: str
    season_id: str
    match_id: str
    kind: str = "match"
    status: str = JOB_QUEUED
    attempts: int = 0
    last_error: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _from_dict(cls, raw: dict):
    allowed = {item.name for item in fields(cls)}
    return cls(**{key: value for key, value in raw.items() if key in allowed})


# ======================================================================
# store
# ======================================================================


class CompetitionStore:
    """Thread-safe, file-backed ledger of seasons, entries, matches and jobs."""

    def __init__(self, path: Path = LEDGER_FILE, matches_root: Path | None = None):
        self.path = path
        self.matches_root = matches_root or MATCHES_ROOT
        self._lock = threading.RLock()
        self._seasons: dict[str, Season] = {}
        self._entries: dict[str, Entry] = {}
        self._matches: dict[str, Match] = {}
        self._jobs: dict[str, Job] = {}
        # Jobs this process is currently executing. Recover ignores these.
        self._live: set[str] = set()
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
            raise CompetitionRegistryError(
                "The persisted competition ledger is unreadable; restore a "
                "backup before starting."
            ) from exc
        for raw in data.get("seasons", []):
            if isinstance(raw, dict):
                season = _from_dict(Season, raw)
                self._seasons[season.id] = season
        for raw in data.get("entries", []):
            if isinstance(raw, dict):
                entry = _from_dict(Entry, raw)
                self._entries[entry.id] = entry
        for raw in data.get("matches", []):
            if isinstance(raw, dict):
                match = _from_dict(Match, raw)
                self._matches[match.id] = match
        for raw in data.get("jobs", []):
            if isinstance(raw, dict):
                job = _from_dict(Job, raw)
                self._jobs[job.id] = job

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "seasons": [asdict(item) for item in self._seasons.values()],
                "entries": [asdict(item) for item in self._entries.values()],
                "matches": [asdict(item) for item in self._matches.values()],
                "jobs": [asdict(item) for item in self._jobs.values()],
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

    def season(self, season_id: str) -> Season:
        with self._lock:
            season = self._seasons.get(season_id)
            if not season:
                raise CompetitionError(f"No season '{season_id}'.")
            return season

    def seasons(self) -> list[Season]:
        with self._lock:
            return sorted(self._seasons.values(), key=lambda item: item.created_at, reverse=True)

    def entry(self, entry_id: str) -> Entry:
        with self._lock:
            entry = self._entries.get(entry_id)
            if not entry:
                raise CompetitionError(f"No entry '{entry_id}'.")
            return entry

    def entries(self, season_id: str, *, include_withdrawn: bool = False) -> list[Entry]:
        with self._lock:
            found = [
                item
                for item in self._entries.values()
                if item.season_id == season_id and (include_withdrawn or not item.withdrawn)
            ]
            return sorted(found, key=lambda item: item.entered_at)

    def entry_for_coach(self, season_id: str, coach: Coach) -> Entry | None:
        for item in self.entries(season_id):
            if item.coach_id == coach.id:
                return item
        return None

    def match(self, match_id: str) -> Match:
        with self._lock:
            match = self._matches.get(match_id)
            if not match:
                raise CompetitionError(f"No match '{match_id}'.")
            return match

    def matches(self, season_id: str) -> list[Match]:
        with self._lock:
            found = [item for item in self._matches.values() if item.season_id == season_id]
            return sorted(found, key=lambda item: item.created_at)

    def job(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise CompetitionError(f"No job '{job_id}'.")
            return job

    def jobs(self, season_id: str) -> list[Job]:
        with self._lock:
            found = [item for item in self._jobs.values() if item.season_id == season_id]
            return sorted(found, key=lambda item: item.created_at)

    def job_for_match(self, match_id: str) -> Job:
        with self._lock:
            for item in self._jobs.values():
                if item.match_id == match_id:
                    return item
        raise CompetitionError(f"No job for match '{match_id}'.")

    # ------------------------------------------------------------------
    # season lifecycle
    # ------------------------------------------------------------------

    def create_season(
        self,
        name: str,
        *,
        catalogue_id: str = COMPETITION_COACH_LEAGUE,
        regulation: Regulation | None = None,
    ) -> Season:
        name = (name or "").strip()
        if not name:
            raise CompetitionError("Give the season a name.")
        if regulation is None:
            spec = catalogue(catalogue_id)
            regulation = regulation_from_mapping(spec.get("regulation"))
            competition = str(spec.get("id") or catalogue_id)
        else:
            competition = catalogue_id
        _validate_regulation(regulation)
        with self._lock:
            season = Season(
                id="ssn_" + secrets.token_hex(8),
                competition=competition,
                name=name[:80],
                status=STATUS_DRAFT,
                regulation=regulation_payload(regulation),
                created_at=_now_iso(),
            )
            self._seasons[season.id] = season
            self.save()
            return season

    def set_regulation(self, season_id: str, regulation: Regulation) -> Season:
        _validate_regulation(regulation)
        with self._lock:
            season = self.season(season_id)
            if season.status != STATUS_DRAFT:
                raise CompetitionError(
                    f"Season '{season.name}' is {season.status}; the regulation is locked."
                )
            season.regulation = regulation_payload(regulation)
            season.regulation_hash = ""
            self.save()
            return season

    def freeze(self, season_id: str) -> Season:
        """Lock the regulation and open the season for entries."""
        with self._lock:
            season = self.season(season_id)
            if season.status == STATUS_FROZEN:
                return season
            if season.status != STATUS_DRAFT:
                raise CompetitionError(
                    f"Season '{season.name}' is {season.status} and cannot be frozen."
                )
            rules = season.rules()
            _validate_regulation(rules)
            season.regulation = regulation_payload(rules)
            season.regulation_hash = regulation_hash(rules)
            season.status = STATUS_FROZEN
            season.frozen_at = _now_iso()
            self.save()
            return season

    def suspend(self, season_id: str, reason: str = "") -> Season:
        with self._lock:
            season = self.season(season_id)
            if season.status not in _LIVE_SEASON:
                raise CompetitionError(
                    f"Season '{season.name}' is {season.status} and cannot be suspended."
                )
            season.status = STATUS_SUSPENDED
            season.suspended_at = _now_iso()
            season.suspend_reason = (reason or "").strip()[:400]
            for job in self._jobs.values():
                if job.season_id == season.id and job.status == JOB_QUEUED:
                    job.status = JOB_SUSPENDED
                    job.last_error = season.suspend_reason or "Season suspended."
            self.save()
            return season

    # ------------------------------------------------------------------
    # entries
    # ------------------------------------------------------------------

    def enter(
        self,
        coach: Coach,
        season_id: str,
        blueprint_id: str,
        version: int | None = None,
        *,
        blueprint_store: "blueprints_mod.BlueprintStore | None" = None,
    ) -> Entry:
        season = self.season(season_id)
        if season.status != STATUS_FROZEN:
            raise CompetitionError(
                f"Season '{season.name}' is {season.status}; entries are closed."
            )
        if self.entry_for_coach(season_id, coach):
            raise CompetitionError("This coach already has an entry in this season.")
        store = blueprint_store or blueprints_mod.default_store()
        ref = store.enroll(coach, blueprint_id, version)
        blueprint = store.get(coach, blueprint_id)
        pinned = blueprint.version(ref.version)
        _assert_entry_allowed(season.rules(), pinned.runtime or {})
        with self._lock:
            entry = Entry(
                id="ent_" + secrets.token_hex(8),
                season_id=season.id,
                coach_id=coach.id,
                blueprint_id=ref.blueprint_id,
                blueprint_version=ref.version,
                blueprint_hash=ref.content_hash,
                name=blueprint.name,
                entered_at=_now_iso(),
            )
            self._entries[entry.id] = entry
            self.save()
            return entry

    def withdraw(self, coach: Coach, season_id: str) -> Entry:
        season = self.season(season_id)
        if season.status != STATUS_FROZEN:
            raise CompetitionError(
                f"Season '{season.name}' is {season.status}; entries can no longer be withdrawn."
            )
        entry = self.entry_for_coach(season_id, coach)
        if entry is None:
            raise CompetitionError("This coach has no entry in this season.")
        with self._lock:
            entry.withdrawn = True
            self.save()
            return entry

    # ------------------------------------------------------------------
    # pairings and jobs
    # ------------------------------------------------------------------

    def pair(self, season_id: str) -> list[Match]:
        """Round-robin. Each pairing is one arena batch; the arena swaps seats."""
        season = self.season(season_id)
        if season.status != STATUS_FROZEN:
            raise CompetitionError(
                f"Season '{season.name}' is {season.status}; pair only a frozen open season."
            )
        field = self.entries(season_id)
        if len(field) < 2:
            raise CompetitionError("Need at least two entries before pairing.")
        ordered = sorted(field, key=lambda item: item.id)
        created: list[Match] = []
        stamp = _now_iso()
        with self._lock:
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    match = Match(
                        id="mt_" + secrets.token_hex(8),
                        season_id=season.id,
                        left_entry_id=left.id,
                        right_entry_id=right.id,
                        left_label=left.label(),
                        right_label=right.label(),
                        status=JOB_QUEUED,
                        created_at=stamp,
                    )
                    job = Job(
                        id="job_" + secrets.token_hex(8),
                        season_id=season.id,
                        match_id=match.id,
                        created_at=stamp,
                    )
                    self._matches[match.id] = match
                    self._jobs[job.id] = job
                    created.append(match)
            season.status = STATUS_SEALED
            season.sealed_at = stamp
            self.save()
        return created

    def stage_final(self, season_id: str) -> Match:
        """One observable match between the top two. Not a rating."""
        season = self.season(season_id)
        if season.status != STATUS_COMPLETE:
            raise CompetitionError(
                f"Season '{season.name}' is {season.status}; the final waits for the table."
            )
        if season.final_match_id:
            return self.match(season.final_match_id)
        table = standings(self, season_id)
        if len(table) < 2:
            raise CompetitionError("A final needs two agents in the table.")
        left = self.entry(str(table[0]["entry_id"]))
        right = self.entry(str(table[1]["entry_id"]))
        stamp = _now_iso()
        with self._lock:
            match = Match(
                id="mt_" + secrets.token_hex(8),
                season_id=season.id,
                left_entry_id=left.id,
                right_entry_id=right.id,
                left_label=left.label(),
                right_label=right.label(),
                status=JOB_QUEUED,
                created_at=stamp,
            )
            job = Job(
                id="job_" + secrets.token_hex(8),
                season_id=season.id,
                match_id=match.id,
                kind="final",
                created_at=stamp,
            )
            self._matches[match.id] = match
            self._jobs[job.id] = job
            season.final_match_id = match.id
            self.save()
            return match

    # ------------------------------------------------------------------
    # jobs
    # ------------------------------------------------------------------

    def next_job(self, season_id: str) -> Job | None:
        season = self.season(season_id)
        if season.status == STATUS_SUSPENDED:
            return None
        if season.status not in (STATUS_SEALED, STATUS_COMPLETE):
            raise CompetitionError(
                f"Season '{season.name}' is {season.status}; there is nothing to dispatch."
            )
        rules = self._checked_rules(season)
        running = sum(1 for item in self.jobs(season_id) if item.status == JOB_RUNNING)
        if running >= rules.max_concurrent:
            return None
        queued = [item for item in self.jobs(season_id) if item.status == JOB_QUEUED]
        return queued[0] if queued else None

    def retry(self, job_id: str) -> Job:
        job = self.job(job_id)
        season = self.season(job.season_id)
        if season.status == STATUS_SUSPENDED:
            raise CompetitionError("The season is suspended.")
        if job.status != JOB_FAILED:
            raise CompetitionError(f"Job '{job.id}' is {job.status}, not failed.")
        rules = self._checked_rules(season)
        if job.attempts > rules.max_retries:
            raise CompetitionError(
                f"Job '{job.id}' has used all {rules.max_retries} allowed retry(ies)."
            )
        with self._lock:
            job.status = JOB_QUEUED
            job.last_error = ""
            match = self.match(job.match_id)
            match.status = JOB_QUEUED
            match.error = ""
            if season.status == STATUS_COMPLETE:
                season.status = STATUS_SEALED
                season.completed_at = ""
            self.save()
            return job

    def suspend_job(self, job_id: str, reason: str = "") -> Job:
        job = self.job(job_id)
        if job.status != JOB_QUEUED:
            raise CompetitionError(
                f"Only a queued job can be suspended (job '{job.id}' is {job.status})."
            )
        with self._lock:
            job.status = JOB_SUSPENDED
            job.last_error = (reason or "Suspended by operator.").strip()[:400]
            match = self.match(job.match_id)
            match.status = JOB_SUSPENDED
            match.error = job.last_error
            self.save()
            return job

    def requeue_orphans(self) -> list[Job]:
        """Jobs left running when the process died. The next dispatch resumes them."""
        restored: list[Job] = []
        with self._lock:
            for job in self._jobs.values():
                if job.status != JOB_RUNNING or job.id in self._live:
                    continue
                job.status = JOB_QUEUED
                restored.append(job)
            if restored:
                self.save()
        return restored

    def audit(self, season_id: str) -> list[dict]:
        """Operator timeline, derived from the records. Not a second ledger."""
        rows: list[dict] = []
        season = self.season(season_id)
        rows.append({"at": season.created_at, "kind": "season", "detail": f"created ({season.status})"})
        if season.frozen_at:
            rows.append({"at": season.frozen_at, "kind": "season", "detail": "regulation frozen"})
        if season.sealed_at:
            rows.append({"at": season.sealed_at, "kind": "season", "detail": "pairings sealed"})
        if season.suspended_at:
            rows.append(
                {
                    "at": season.suspended_at,
                    "kind": "season",
                    "detail": "suspended"
                    + (f": {season.suspend_reason}" if season.suspend_reason else ""),
                }
            )
        if season.completed_at:
            rows.append({"at": season.completed_at, "kind": "season", "detail": "complete"})
        for entry in self.entries(season_id, include_withdrawn=True):
            rows.append(
                {
                    "at": entry.entered_at,
                    "kind": "entry",
                    "detail": f"{entry.name} v{entry.blueprint_version} ({entry.id})",
                }
            )
        for job in self.jobs(season_id):
            rows.append(
                {
                    "at": job.started_at or job.created_at,
                    "kind": "job",
                    "detail": (
                        f"{job.id} {job.status} attempt {job.attempts}"
                        + (f": {job.last_error}" if job.last_error else "")
                    ),
                }
            )
        return sorted(rows, key=lambda row: row["at"] or "")

    def _checked_rules(self, season: Season) -> Regulation:
        rules = season.rules()
        if season.status in (STATUS_FROZEN, STATUS_SEALED, STATUS_COMPLETE, STATUS_SUSPENDED):
            actual = regulation_hash(rules)
            if season.regulation_hash and not secrets.compare_digest(actual, season.regulation_hash):
                raise CompetitionIntegrityError(
                    f"Season '{season.name}' regulation no longer matches the frozen hash "
                    f"(frozen={season.regulation_hash[:12]}, current={actual[:12]})."
                )
        return rules

    def _mark_job(self, job: Job, status: str, **fields) -> Job:
        with self._lock:
            job.status = status
            for key, value in fields.items():
                setattr(job, key, value)
            stamp = _now_iso()
            if status == JOB_RUNNING and not job.started_at:
                job.started_at = stamp
            if status in _TERMINAL_JOB:
                job.finished_at = stamp
            match = self.match(job.match_id)
            match.status = status
            if status == JOB_RUNNING and not match.started_at:
                match.started_at = stamp
            if status in _TERMINAL_JOB:
                match.finished_at = stamp
            if status == JOB_FAILED:
                match.error = str(fields.get("last_error") or job.last_error)
            if status == JOB_COMPLETE:
                self._maybe_complete_season(job.season_id)
            self.save()
            return job

    def _maybe_complete_season(self, season_id: str) -> None:
        jobs = [item for item in self._jobs.values() if item.season_id == season_id]
        if jobs and all(item.status == JOB_COMPLETE for item in jobs):
            season = self._seasons[season_id]
            season.status = STATUS_COMPLETE
            season.completed_at = _now_iso()

    def _claim(self, job: Job) -> Job:
        with self._lock:
            if job.status not in (JOB_QUEUED, JOB_RUNNING):
                raise CompetitionError(f"Job '{job.id}' is {job.status} and cannot be started.")
            job.attempts += 1
            job.status = JOB_RUNNING
            if not job.started_at:
                job.started_at = _now_iso()
            match = self.match(job.match_id)
            match.status = JOB_RUNNING
            if not match.started_at:
                match.started_at = job.started_at
            self._live.add(job.id)
            self.save()
            return job


# ======================================================================
# running one match
# ======================================================================


def policy_name(model: str, label: str) -> str:
    """The name ``scripts.arena.LLMPolicy`` will give this seat."""
    return f"llm:{model}:{label}"


def match_config(
    store: CompetitionStore,
    match: Match,
    *,
    blueprint_store: "blueprints_mod.BlueprintStore | None" = None,
) -> dict:
    """The arena config for one official pairing.

    Both seats resolve through the Phase 1 store, so a version edited since
    enrollment fails here — the same refusal a training run gets — instead of
    quietly playing something else. Model, tokens, temperature and budget come
    from the frozen regulation, not from the blueprints.
    """
    season = store.season(match.season_id)
    rules = store._checked_rules(season)
    if rules.allow_vision or rules.allow_subagents:
        raise CompetitionError("Coach League matches may not enable vision or subagents.")
    blueprints = blueprint_store or blueprints_mod.default_store()
    left = store.entry(match.left_entry_id)
    right = store.entry(match.right_entry_id)
    left_version = blueprints.resolve(
        BlueprintRef(left.blueprint_id, left.blueprint_version, left.blueprint_hash)
    )
    right_version = blueprints.resolve(
        BlueprintRef(right.blueprint_id, right.blueprint_version, right.blueprint_hash)
    )
    return {
        "mode": "league",
        "map": rules.map,
        "turns": rules.turns,
        "seed_pairs": rules.seed_pairs,
        "temperature": rules.temperature,
        "max_tokens": rules.max_tokens,
        "max_spend_usd": rules.max_spend_usd,
        "redact_reasoning": bool(rules.redact_reasoning),
        "entrants": [
            _entrant(rules, left, left_version),
            _entrant(rules, right, right_version),
        ],
    }


def _entrant(rules: Regulation, entry: Entry, version: blueprints_mod.BlueprintVersion) -> dict:
    return {
        "type": "llm",
        "model": rules.model,
        "blueprint_label": entry.label(),
        "blueprint_inline": blueprints_mod.runtime_blueprint(entry.blueprint_id, version),
        "blueprint_content_hash": entry.blueprint_hash,
    }


def execute(
    job: Job,
    store: CompetitionStore,
    **kwargs,
) -> Job:
    """Play or resume one queued job and record where its evidence landed."""
    from scripts.arena import prepare_bundle, resume_bundle, run_batch

    if job.status in (JOB_COMPLETE, JOB_SUSPENDED):
        raise CompetitionError(f"Job '{job.id}' is {job.status} and cannot be started.")
    store._claim(job)
    match = store.match(job.match_id)
    try:
        config = match_config(store, match, **kwargs)
    except (BlueprintError, CompetitionError) as exc:
        store._live.discard(job.id)
        return store._mark_job(job, JOB_FAILED, last_error=str(exc))

    output = store.matches_root / match.season_id / match.id
    output.mkdir(parents=True, exist_ok=True)
    try:
        if match.run_id and match.run_dir:
            bundle = resume_bundle(Path(match.run_dir).parent, match.run_id, config)
        else:
            bundle = prepare_bundle(config, output)
            with store._lock:
                match.run_id = bundle.run_id
                match.run_dir = str(bundle.run_dir)
                store.save()
    except Exception as exc:  # noqa: BLE001 - the season owns the failure
        store._live.discard(job.id)
        return store._mark_job(job, JOB_FAILED, last_error=f"{type(exc).__name__}: {exc}")

    try:
        summary = run_batch(config, Path(match.run_dir).parent, bundle=bundle)
    except Exception as exc:  # noqa: BLE001 - the season owns the failure
        store._live.discard(job.id)
        return store._mark_job(job, JOB_FAILED, last_error=f"{type(exc).__name__}: {exc}")

    with store._lock:
        match.result = _headline(summary, match, store.season(match.season_id).rules().model)
        store.save()
    store._live.discard(job.id)
    return store._mark_job(job, JOB_COMPLETE, last_error="")


AUTO_COMPLETE_THRESHOLD = 0.95


def dispatch(store: CompetitionStore, season_id: str, **kwargs) -> Job | None:
    """Claim the next queued job, if the season's concurrency allows it."""
    job = store.next_job(season_id)
    if job is None:
        return None
    return execute(job, store, **kwargs)


def completion(store: CompetitionStore, season_id: str) -> dict:
    """How much of the season finished without an operator touching a file."""
    jobs = store.jobs(season_id)
    total = len(jobs)
    complete = sum(1 for item in jobs if item.status == JOB_COMPLETE)
    failed = sum(1 for item in jobs if item.status == JOB_FAILED)
    queued = sum(1 for item in jobs if item.status == JOB_QUEUED)
    return {
        "total": total,
        "complete": complete,
        "failed": failed,
        "queued": queued,
        "rate": (complete / total) if total else 0.0,
        "season_status": store.season(season_id).status,
    }


def run_until_idle(store: CompetitionStore, season_id: str, **kwargs) -> dict:
    """Play every queued job. The operator starts this; they do not edit the ledger."""
    store.requeue_orphans()
    ran: list[str] = []
    while True:
        job = dispatch(store, season_id, **kwargs)
        if job is None:
            break
        ran.append(job.id)
    report = completion(store, season_id)
    report["ran"] = ran
    return report


def records_agree(store: CompetitionStore, match: Match) -> dict:
    """Result, manifest and replay describe the same finished match.

    Every number the standings use must be readable back from the bundle.
    """
    if match.status != JOB_COMPLETE:
        raise CompetitionError(f"Match '{match.id}' is {match.status}, not complete.")
    if not match.run_dir:
        raise CompetitionIntegrityError(f"Match '{match.id}' has no bundle.")
    root = Path(match.run_dir)
    results_path = root.parent / "arena_results.json"
    if not results_path.exists():
        results_path = root / "arena_results.json"
    try:
        summary = json.loads(results_path.read_text(encoding="utf-8"))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompetitionIntegrityError(
            f"Match '{match.id}' bundle is unreadable: {exc}"
        ) from exc
    season = store.season(match.season_id)
    rules = store._checked_rules(season)
    left = policy_name(rules.model, match.left_label)
    right = policy_name(rules.model, match.right_label)
    wins = summary.get("wins") or {}
    replay_games = 0
    games_path = root / "games.jsonl"
    if games_path.exists():
        seen: set[str] = set()
        for line in games_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            game_id = str(record.get("game_id") or "")
            if game_id:
                seen.add(game_id)
        replay_games = len(seen)
    expected_games = int(summary.get("games") or 0)
    if int(match.result.get("games") or 0) != expected_games:
        raise CompetitionIntegrityError(
            f"Match '{match.id}' result games {match.result.get('games')} "
            f"!= bundle {expected_games}."
        )
    if replay_games and replay_games != expected_games:
        raise CompetitionIntegrityError(
            f"Match '{match.id}' replay has {replay_games} games, bundle has {expected_games}."
        )
    if int(match.result.get("left_wins") or 0) != int(wins.get(left, 0) or 0):
        raise CompetitionIntegrityError(f"Match '{match.id}' left wins do not match the bundle.")
    if int(match.result.get("right_wins") or 0) != int(wins.get(right, 0) or 0):
        raise CompetitionIntegrityError(f"Match '{match.id}' right wins do not match the bundle.")
    if str(manifest.get("mode")) != "league":
        raise CompetitionIntegrityError(f"Match '{match.id}' manifest mode is not league.")
    if str(manifest.get("map")) != rules.map:
        raise CompetitionIntegrityError(f"Match '{match.id}' manifest map drifted.")
    if int(manifest.get("turns") or 0) != rules.turns:
        raise CompetitionIntegrityError(f"Match '{match.id}' manifest turns drifted.")
    if int(manifest.get("seed_pairs") or 0) != rules.seed_pairs:
        raise CompetitionIntegrityError(f"Match '{match.id}' manifest seed_pairs drifted.")
    if str(manifest.get("status")) != "complete":
        raise CompetitionIntegrityError(f"Match '{match.id}' manifest is not complete.")
    return {
        "match_id": match.id,
        "games": expected_games,
        "manifest_status": manifest.get("status"),
        "replay_games": replay_games,
    }


def recover(store: CompetitionStore, season_id: str | None = None, **kwargs) -> list[Job]:
    """Requeue jobs the previous process left running, then dispatch one.

    Isolation is per match directory. Resume is the arena's: the same config
    opens the existing bundle and replays recorded decisions.
    """
    orphans = store.requeue_orphans()
    if season_id:
        job = dispatch(store, season_id, **kwargs)
        return orphans if job is None else orphans + [job]
    return orphans


def _headline(summary: dict, match: Match, model: str) -> dict:
    """The few numbers standings need, all of them read back from the record."""
    wins = summary.get("wins") or {}
    sweeps = summary.get("pair_sweeps") or {}
    left = policy_name(model, match.left_label)
    right = policy_name(model, match.right_label)
    return {
        "games": summary.get("games", 0),
        "left_entry_id": match.left_entry_id,
        "right_entry_id": match.right_entry_id,
        "left_wins": int(wins.get(left, 0) or 0),
        "right_wins": int(wins.get(right, 0) or 0),
        "draws": int(summary.get("draws", 0) or 0),
        "left_sweeps": int(sweeps.get(left, 0) or 0),
        "right_sweeps": int(sweeps.get(right, 0) or 0),
        "decided_by": summary.get("decided_by") or {},
    }


# ======================================================================
# standings
# ======================================================================


def standings(store: CompetitionStore, season_id: str) -> list[dict]:
    """Wins, losses, draws and pair sweeps. No rating.

    Pure in the numbers: every cell is a sum of persisted match results.
    Recomputing from the ledger must agree with the table.
    """
    store.season(season_id)
    rows: dict[str, dict] = {}
    for entry in store.entries(season_id, include_withdrawn=True):
        rows[entry.id] = {
            "entry_id": entry.id,
            "coach_id": entry.coach_id,
            "name": entry.name,
            "blueprint_id": entry.blueprint_id,
            "blueprint_version": entry.blueprint_version,
            "played": 0,
            "won": 0,
            "lost": 0,
            "drawn": 0,
            "sweeps": 0,
        }
    for match in store.matches(season_id):
        if match.status != JOB_COMPLETE or not match.result:
            continue
        result = match.result
        left = rows.get(str(result.get("left_entry_id") or match.left_entry_id))
        right = rows.get(str(result.get("right_entry_id") or match.right_entry_id))
        if not left or not right:
            continue
        left["played"] += 1
        right["played"] += 1
        left["won"] += int(result.get("left_wins") or 0)
        right["won"] += int(result.get("right_wins") or 0)
        left["lost"] += int(result.get("right_wins") or 0)
        right["lost"] += int(result.get("left_wins") or 0)
        draws = int(result.get("draws") or 0)
        left["drawn"] += draws
        right["drawn"] += draws
        left["sweeps"] += int(result.get("left_sweeps") or 0)
        right["sweeps"] += int(result.get("right_sweeps") or 0)
    table = list(rows.values())
    table.sort(
        key=lambda row: (
            -int(row["sweeps"]),
            -int(row["won"]),
            int(row["lost"]),
            str(row["entry_id"]),
        )
    )
    return table


# ======================================================================
# validation
# ======================================================================


def _validate_regulation(regulation: Regulation) -> None:
    if not (regulation.model or "").strip():
        raise CompetitionError("A season regulation must name a model.")
    if not 0.0 <= float(regulation.temperature) <= 2.0:
        raise CompetitionError("Regulation temperature must be between 0.0 and 2.0.")
    if not 1 <= int(regulation.max_tokens) <= 32000:
        raise CompetitionError("Regulation max_tokens must be between 1 and 32000.")
    if int(regulation.turns) < 1:
        raise CompetitionError("Regulation turns must be at least 1.")
    if int(regulation.seed_pairs) < 1:
        raise CompetitionError("Regulation seed_pairs must be at least 1.")
    if float(regulation.max_spend_usd) < 0:
        raise CompetitionError("Regulation max_spend_usd cannot be negative.")
    if int(regulation.max_retries) < 0:
        raise CompetitionError("Regulation max_retries cannot be negative.")
    if int(regulation.timeout_s) < 1:
        raise CompetitionError("Regulation timeout_s must be at least 1.")
    if int(regulation.max_concurrent) < 1:
        raise CompetitionError("Regulation max_concurrent must be at least 1.")
    if regulation.allow_vision or regulation.allow_subagents:
        raise CompetitionError("Coach League regulation cannot enable vision or subagents.")


def _assert_entry_allowed(rules: Regulation, runtime: dict) -> None:
    model = str(runtime.get("model") or "").strip()
    if model and model != rules.model:
        raise CompetitionError(
            f"This season is locked to {rules.model}; the blueprint names {model}."
        )


def sanitize_untrusted(text: str) -> str:
    """Opponent text as the official path treats it: neutralized, never trusted."""
    from webapp.ai.context import neutralize_untrusted

    return neutralize_untrusted(text)


# ======================================================================
# default store
# ======================================================================


_store: CompetitionStore | None = None


def default_store() -> CompetitionStore:
    global _store
    if _store is None:
        _store = CompetitionStore()
    return _store
