"""
Background execution for single bot turns.

A bot turn spends brain's whole retry budget -- tens of seconds even when
everything works -- inside ``orchestrator.run_bot_turn``. Run synchronously,
that pins a request-handler thread for the duration; ``autoplay`` already
proved the alternative for whole-room loops: one daemon worker, results
polled by the caller. This module applies the same shape to one-shot turns:
``submit`` enqueues, a single worker plays the seat, ``get`` reports status
and the outcome.

Jobs live in memory only, like autoplay's status: a crashed server loses the
queued turn, not the game -- nothing was submitted yet, so the seat simply
has not played this turn.
"""

from __future__ import annotations

import queue
import secrets
import threading
from datetime import datetime, timezone

from webapp.ai import orchestrator
from webapp.rooms import default_store

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"

#: Pending submissions allowed before the queue pushes back. The worker is
#: one thread on purpose -- the deployment is single-worker and the seats of
#: one room play in sequence -- so this ceiling is what a burst meets.
_MAX_PENDING = 32

#: Finished jobs kept for polling; older ones fall out of the map.
_KEEP_FINISHED = 200


class QueueFullError(RuntimeError):
    """Too many bot turns are already waiting."""


class BotJob:
    def __init__(self, job_id: str, room_code: str, faction_id: str) -> None:
        self.id = job_id
        self.room_code = room_code
        self.faction_id = faction_id
        self.status = STATUS_QUEUED
        self.created_at = _now()
        self.finished_at = ""
        self.result: dict | None = None
        self.error = ""

    def public(self) -> dict:
        payload = {
            "job_id": self.id,
            "room_code": self.room_code,
            "faction_id": self.faction_id,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }
        if self.status == STATUS_COMPLETE:
            payload["result"] = self.result
        if self.error:
            payload["error"] = self.error
        return payload


class BotJobRunner:
    """One lazy daemon worker draining a bounded queue of bot turns."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, BotJob] = {}
        self._pending: queue.Queue[str] = queue.Queue(maxsize=_MAX_PENDING)
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # caller side
    # ------------------------------------------------------------------

    def submit(self, room_code: str, faction_id: str) -> BotJob:
        """Enqueue one bot turn. Raises ``QueueFullError`` under load."""
        self._ensure_worker()
        job = BotJob(
            job_id="bj_" + secrets.token_hex(8),
            room_code=room_code.upper(),
            faction_id=faction_id,
        )
        # Register before enqueue: the worker may drain the id immediately,
        # and a lookup that misses reads as a pruned job, not an error.
        with self._lock:
            self._jobs[job.id] = job
            try:
                self._pending.put_nowait(job.id)
            except queue.Full:
                del self._jobs[job.id]
                raise QueueFullError(
                    "Too many bot turns are already queued. Try again shortly."
                ) from None
        return job

    def get(self, job_id: str) -> BotJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def reset(self) -> None:
        """Forget every job. For tests."""
        with self._lock:
            self._jobs.clear()
            try:
                while True:
                    self._pending.get_nowait()
            except queue.Empty:
                pass

    # ------------------------------------------------------------------
    # worker side
    # ------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._loop, daemon=True, name="soe-bot-jobs"
            )
            self._thread.start()

    def _loop(self) -> None:
        while True:
            job_id = self._pending.get()
            job = self.get(job_id)
            if job is None:  # reset while queued
                continue
            room = default_store().get(job.room_code)
            player = (
                next(
                    (
                        p
                        for p in room.players
                        if p.faction_id == job.faction_id
                    ),
                    None,
                )
                if room
                else None
            )
            if room is None or player is None:
                self._finish(job_id, status=STATUS_ERROR, error="The room or "
                              "faction no longer exists.")
                continue
            self._finish(job_id, status=STATUS_RUNNING)
            try:
                result = orchestrator.run_bot_turn(room, player)
            except Exception as exc:  # noqa: BLE001 - reported through the job
                self._finish(
                    job_id,
                    status=STATUS_ERROR,
                    error=f"{type(exc).__name__}: {exc}"[:500],
                    finished_at=_now(),
                )
            else:
                self._finish(
                    job_id,
                    status=STATUS_COMPLETE,
                    result=result,
                    finished_at=_now(),
                )

    def _finish(self, job_id: str, **fields) -> None:
        """Patch one job through a fresh lookup: reset() may have dropped it."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for name, value in fields.items():
                setattr(job, name, value)
            self._prune_locked()

    def _prune_locked(self) -> None:
        finished = [j for j in self._jobs.values() if j.finished_at]
        excess = len(finished) - _KEEP_FINISHED
        if excess <= 0:
            return
        finished.sort(key=lambda j: j.finished_at)
        for job in finished[:excess]:
            self._jobs.pop(job.id, None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_runner: BotJobRunner | None = None


def default_runner() -> BotJobRunner:
    global _runner
    if _runner is None:
        _runner = BotJobRunner()
    return _runner
