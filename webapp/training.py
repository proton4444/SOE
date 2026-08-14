"""
Training runs — a coach tries a blueprint without an operator in the loop.

Phase 1 made the agent an object. This is the first half of the loop that
object exists for: create, **try**, understand, change. A coach picks a frozen
version and a scenario from a fixed catalogue, and gets back a run they own.

Three decisions shape the module.

**A training run is an arena run.** The headless arena already persists what a
debrief has to be built from — per-turn state hashes, every decision, the
orders as emitted and as accepted, cost, latency, provider failures — and it
resumes. Building a second runner would mean a second, weaker record. So this
module is a thin layer: it decides *who may run what*, and hands the rest to
``scripts.arena``.

**The blueprint travels by value, and the hash travels with it.** The arena
takes blueprints from ``configs/blueprints``; a Phase 1 blueprint is a row in a
coach's store. The run config therefore carries the prompt-facing payload
inline, and the run record keeps the enrolled content hash next to it. What was
played stays checkable after the store has moved on.

**Nothing private is recorded.** Runs are started with ``redact_reasoning``, so
the model's free text before the orders marker never reaches disk. A debrief
owes the coach an account of what their agent *did*; the model's inner
monologue is neither reliable as an explanation nor theirs to read.

State lives in ``server_data/training.json``; the evidence lives in the arena
bundle under ``games/training/<run_id>``.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from webapp import blueprints as blueprints_mod
from webapp.blueprints import BlueprintError, BlueprintRef
from webapp.coaches import Coach

_REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DATA = Path(os.environ.get("SOE_DATA_DIR", str(_REPO_ROOT / "server_data")))
GAMES_ROOT = Path(os.environ.get("SOE_GAMES_DIR", str(_REPO_ROOT / "games")))
TRAINING_FILE = SERVER_DATA / "training.json"
TRAINING_RUNS_ROOT = GAMES_ROOT / "training"
SCENARIOS_FILE = _REPO_ROOT / "configs" / "training" / "scenarios.json"

#: Quotas. A training run costs provider money and the coach is not the one
#: paying, so the ceiling is not optional. Two limits rather than one: the
#: daily one bounds the bill, and the per-version one bounds a coach burning a
#: whole day's allowance re-running a version they have not changed.
QUOTA_PER_COACH_DAILY = int(os.environ.get("SOE_TRAINING_QUOTA_DAILY", "20"))
QUOTA_PER_VERSION = int(os.environ.get("SOE_TRAINING_QUOTA_VERSION", "10"))

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


class TrainingRegistryError(RuntimeError):
    """The persisted training registry cannot be trusted for startup."""


class TrainingError(Exception):
    """A training request cannot be honoured as asked."""


class QuotaExceeded(TrainingError):
    """This coach has used up an allowance."""


# ======================================================================
# scenarios
# ======================================================================


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    map: str
    turns: int
    seed_pairs: int
    opponent: dict
    max_spend_usd: float

    @property
    def opponent_label(self) -> str:
        kind = self.opponent.get("type", "")
        style = self.opponent.get("style", "")
        return f"{kind}:{style}" if style else kind


def _load_scenarios() -> dict[str, Scenario]:
    try:
        data = json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TrainingRegistryError(
            f"The training scenario catalogue is unreadable: {SCENARIOS_FILE}"
        ) from exc
    scenarios: dict[str, Scenario] = {}
    for raw in data.get("scenarios", []):
        scenario = Scenario(
            id=str(raw["id"]),
            name=str(raw.get("name", raw["id"])),
            description=str(raw.get("description", "")),
            map=str(raw["map"]),
            turns=int(raw["turns"]),
            seed_pairs=int(raw["seed_pairs"]),
            opponent=dict(raw.get("opponent") or {}),
            max_spend_usd=float(raw.get("max_spend_usd", 0.0)),
        )
        scenarios[scenario.id] = scenario
    if not scenarios:
        raise TrainingRegistryError("The training scenario catalogue is empty.")
    return scenarios


_scenarios: dict[str, Scenario] | None = None


def scenarios() -> dict[str, Scenario]:
    global _scenarios
    if _scenarios is None:
        _scenarios = _load_scenarios()
    return _scenarios


def scenario(scenario_id: str) -> Scenario:
    try:
        return scenarios()[scenario_id]
    except KeyError:
        known = ", ".join(sorted(scenarios()))
        raise TrainingError(f"Unknown scenario '{scenario_id}'. Choose one of: {known}.")


# ======================================================================
# the run record
# ======================================================================


@dataclass
class TrainingRun:
    id: str
    coach_id: str
    blueprint_id: str
    blueprint_version: int
    #: The Phase 1 content hash enrolled when the run started. The run is
    #: readable against this for as long as the version exists.
    blueprint_hash: str
    scenario_id: str
    opponent: str
    model: str
    status: str = STATUS_QUEUED
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    #: Arena bundle identity. The numbers a debrief shows come from here, not
    #: from anything this record duplicates.
    run_id: str = ""
    run_dir: str = ""
    error: str = ""
    result: dict = field(default_factory=dict)

    @property
    def finished(self) -> bool:
        return self.status in (STATUS_COMPLETE, STATUS_FAILED)

    def bundle_dir(self) -> Path:
        return Path(self.run_dir) if self.run_dir else TRAINING_RUNS_ROOT / self.run_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ======================================================================
# store
# ======================================================================


class TrainingStore:
    """Thread-safe, file-backed registry of training runs."""

    def __init__(self, path: Path = TRAINING_FILE, runs_root: Path | None = None):
        self.path = path
        self.runs_root = runs_root or TRAINING_RUNS_ROOT
        self._lock = threading.RLock()
        self._runs: dict[str, TrainingRun] = {}
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
            # Losing this file would reset every coach's quota and orphan the
            # bundles on disk from the coaches who own them.
            raise TrainingRegistryError(
                "The persisted training registry is unreadable; restore a "
                "backup before starting."
            ) from exc
        for raw in data.get("runs", []):
            try:
                run = TrainingRun(**raw)
            except TypeError:
                continue
            self._runs[run.id] = run

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"runs": [asdict(r) for r in self._runs.values()]}
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

    def get(self, coach: Coach, run_id: str) -> TrainingRun:
        """A run this coach owns. Somebody else's is reported as missing."""
        with self._lock:
            run = self._runs.get(run_id)
            if not run or run.coach_id != coach.id:
                raise TrainingError(f"No training run '{run_id}'.")
            return run

    def for_coach(self, coach: Coach) -> list[TrainingRun]:
        with self._lock:
            return sorted(
                (r for r in self._runs.values() if r.coach_id == coach.id),
                key=lambda r: r.created_at,
                reverse=True,
            )

    def for_version(self, coach: Coach, blueprint_id: str, version: int) -> list[TrainingRun]:
        return [
            run
            for run in self.for_coach(coach)
            if run.blueprint_id == blueprint_id and run.blueprint_version == int(version)
        ]

    # ------------------------------------------------------------------
    # quotas
    # ------------------------------------------------------------------

    def quota_state(self, coach: Coach, blueprint_id: str = "", version: int = 0) -> dict:
        """What the coach has left, and against what limit.

        A failed run still counts: the provider was still called. What does not
        count is a run this store never started.
        """
        since = _now() - timedelta(days=1)
        runs = self.for_coach(coach)
        today = sum(1 for r in runs if _parsed(r.created_at) >= since)
        state = {
            "daily_used": today,
            "daily_limit": QUOTA_PER_COACH_DAILY,
            "daily_remaining": max(0, QUOTA_PER_COACH_DAILY - today),
        }
        if blueprint_id:
            used = len(self.for_version(coach, blueprint_id, version))
            state.update(
                {
                    "version_used": used,
                    "version_limit": QUOTA_PER_VERSION,
                    "version_remaining": max(0, QUOTA_PER_VERSION - used),
                }
            )
        return state

    def _check_quota(self, coach: Coach, blueprint_id: str, version: int) -> None:
        state = self.quota_state(coach, blueprint_id, version)
        if state["daily_remaining"] <= 0:
            raise QuotaExceeded(
                f"You have used all {QUOTA_PER_COACH_DAILY} training runs for today. "
                "The allowance is per rolling 24 hours."
            )
        if state["version_remaining"] <= 0:
            raise QuotaExceeded(
                f"Version {version} has used all {QUOTA_PER_VERSION} of its training "
                "runs. Open a new version to keep going."
            )

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        coach: Coach,
        blueprint_id: str,
        scenario_id: str,
        *,
        version: int | None = None,
        blueprint_store: "blueprints_mod.BlueprintStore | None" = None,
    ) -> TrainingRun:
        """Record a run this coach may make. Does not play it.

        The blueprint is enrolled through the Phase 1 store, so the same rules
        apply as to a league seat: a frozen version, of a live blueprint, that
        this coach may read.
        """
        chosen = scenario(scenario_id)
        store = blueprint_store or blueprints_mod.default_store()
        ref = store.enroll(coach, blueprint_id, version)
        blueprint = store.get(coach, blueprint_id)
        runtime = blueprint.version(ref.version).runtime or {}
        with self._lock:
            self._check_quota(coach, ref.blueprint_id, ref.version)
            run = TrainingRun(
                id="tr_" + secrets.token_hex(8),
                coach_id=coach.id,
                blueprint_id=ref.blueprint_id,
                blueprint_version=ref.version,
                blueprint_hash=ref.content_hash,
                scenario_id=chosen.id,
                opponent=chosen.opponent_label,
                model=str(runtime.get("model", "")),
                created_at=_now().isoformat(),
            )
            self._runs[run.id] = run
            self.save()
            return run

    def mark(self, run: TrainingRun, status: str, **fields) -> TrainingRun:
        with self._lock:
            run.status = status
            for key, value in fields.items():
                setattr(run, key, value)
            if status == STATUS_RUNNING and not run.started_at:
                run.started_at = _now().isoformat()
            if status in (STATUS_COMPLETE, STATUS_FAILED):
                run.finished_at = _now().isoformat()
            self._runs[run.id] = run
            self.save()
            return run


def _parsed(timestamp: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ======================================================================
# running one
# ======================================================================


def run_config(
    run: TrainingRun, *, blueprint_store: "blueprints_mod.BlueprintStore | None" = None
) -> dict:
    """The arena config for one training run.

    The blueprint is resolved through the Phase 1 store rather than read from
    the record, so a version edited since the run started fails here — the same
    refusal a league seat gets — instead of quietly training something else.
    """
    store = blueprint_store or blueprints_mod.default_store()
    version = store.resolve(
        BlueprintRef(run.blueprint_id, run.blueprint_version, run.blueprint_hash)
    )
    chosen = scenario(run.scenario_id)
    label = f"{run.blueprint_id}_v{run.blueprint_version}"
    return {
        "mode": "training",
        "map": chosen.map,
        "turns": chosen.turns,
        "seed_pairs": chosen.seed_pairs,
        "temperature": float((version.runtime or {}).get("temperature", 0.0)),
        "max_tokens": int((version.runtime or {}).get("max_tokens", 1500)),
        "max_spend_usd": chosen.max_spend_usd,
        # The model's free reasoning is never persisted for a coach-facing run.
        "redact_reasoning": True,
        "entrants": [
            {
                "type": "llm",
                "model": run.model,
                "blueprint_label": label,
                "blueprint_inline": blueprints_mod.runtime_blueprint(
                    run.blueprint_id, version
                ),
                # Carried for the record, not for the arena: this is what the
                # coach entered, and it is checkable against the store.
                "blueprint_content_hash": run.blueprint_hash,
            },
            dict(chosen.opponent),
        ],
    }


def execute(run: TrainingRun, store: TrainingStore, **kwargs) -> TrainingRun:
    """Play a queued run and record where its evidence landed.

    A failure is recorded, not raised: a coach whose run died to a provider
    outage still owns the run, and the reason is part of the debrief.
    """
    from scripts.arena import prepare_bundle, run_batch

    if run.status != STATUS_QUEUED:
        raise TrainingError(f"Training run '{run.id}' has already been started.")
    try:
        config = run_config(run, **kwargs)
    except BlueprintError as exc:
        return store.mark(run, STATUS_FAILED, error=str(exc))

    store.runs_root.mkdir(parents=True, exist_ok=True)
    try:
        bundle = prepare_bundle(config, store.runs_root)
    except Exception as exc:  # noqa: BLE001 - the coach owns the failure
        return store.mark(run, STATUS_FAILED, error=f"{type(exc).__name__}: {exc}")

    store.mark(
        run, STATUS_RUNNING, run_id=bundle.run_id, run_dir=str(bundle.run_dir)
    )
    try:
        summary = run_batch(config, bundle.run_dir, bundle=bundle)
    except Exception as exc:  # noqa: BLE001 - the coach owns the failure
        return store.mark(run, STATUS_FAILED, error=f"{type(exc).__name__}: {exc}")
    return store.mark(run, STATUS_COMPLETE, result=_headline(summary, run))


def _headline(summary: dict, run: TrainingRun) -> dict:
    """The few numbers a run list needs, all of them read back from the record.

    Everything richer belongs in the debrief, which reads the bundle itself.
    Nothing here is computed from a source the coach cannot be shown.
    """
    policies = summary.get("policies") or []
    label = f"{run.blueprint_id}_v{run.blueprint_version}"
    mine = next((p for p in policies if p.endswith(label)), policies[0] if policies else "")
    wins = summary.get("wins") or {}
    return {
        "games": summary.get("games", 0),
        "policy": mine,
        "wins": wins.get(mine, 0),
        "opponent_wins": sum(v for k, v in wins.items() if k != mine),
        "draws": summary.get("draws", 0),
        "sweeps": (summary.get("pair_sweeps") or {}).get(mine, 0),
        "decided_by": summary.get("decided_by", {}),
    }


_store: TrainingStore | None = None


def default_store() -> TrainingStore:
    global _store
    if _store is None:
        _store = TrainingStore()
    return _store
