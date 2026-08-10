"""
Auto-play controller: advance a room turn by turn in the background.

One daemon thread per room. Each cycle runs every enabled bot (subagents,
strategist, parser-filtered orders), then resolves when the room is ready
(or immediately when force is set). The host dashboard polls ``status()``;
nothing is persisted beyond the normal room files, so a crashed server leaves
the game exactly where the last turn left it.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone

from webapp import service
from webapp.ai import orchestrator
from webapp.ai.registry import default_registry
from webapp.rooms import default_store

POLL_SECONDS = 1.0
# A bot that fails this many turns in a row is suspended for the rest of the
# run so one broken profile cannot stall the room.
MAX_CONSECUTIVE_FAILURES = 3


class AutoplayError(RuntimeError):
    """The controller refused the request (already running, unknown room...)."""


class AutoplayController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._status: dict = _idle_status()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        code: str,
        *,
        turns: int = 0,
        delay: float = 5.0,
        force: bool = False,
        wait_humans: bool = False,
    ) -> dict:
        code = code.upper()
        with self._lock:
            if self._status.get("running"):
                raise AutoplayError(
                    f"Auto-play is already running for room {self._status.get('code')}."
                )
            room = default_store().get(code)
            if not room:
                raise AutoplayError(f"No room with code {code}.")
            bots = [
                p
                for p in room.players
                if default_registry().is_bot(room.code, p.faction_id)
            ]
            if not bots:
                raise AutoplayError("No enabled bots in this room.")
            self._stop_flag.clear()
            self._status = {
                "running": True,
                "code": code,
                "turns_done": 0,
                "turns_planned": max(1, int(turns)),
                "delay": max(0.1, float(delay)),
                "force": bool(force),
                "wait_humans": bool(wait_humans),
                "last_turn": 0,
                "last_result": "",
                "last_error": "",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "stopped_at": "",
                "log": deque([f"auto-play started for room {code}"], maxlen=20),
            }
            self._thread = threading.Thread(
                target=self._run,
                args=(code,),
                daemon=True,
                name=f"autoplay-{code}",
            )
            self._thread.start()
            return self.status()

    def stop(self, code: str) -> dict:
        code = code.upper()
        with self._lock:
            if self._status.get("running") and self._status.get("code") == code:
                self._stop_flag.set()
        return self.status()

    def status(self) -> dict:
        with self._lock:
            snapshot = dict(self._status)
            snapshot["log"] = list(self._status.get("log", []))
            return snapshot

    # ------------------------------------------------------------------
    # worker
    # ------------------------------------------------------------------

    def _run(self, code: str) -> None:
        try:
            self._cycle(code)
        finally:
            with self._lock:
                self._status["running"] = False
                self._status["stopped_at"] = datetime.now(timezone.utc).isoformat()
                self._log("auto-play stopped")

    def _cycle(self, code: str) -> None:
        failures: dict[str, int] = {}
        while not self._stop_flag.is_set():
            room = default_store().get(code)
            if not room:
                raise AutoplayError(f"Room {code} vanished mid-run.")
            turn = room.next_turn()
            self._log(f"turn {turn}: running bots")
            for player in room.players:
                if self._stop_flag.is_set():
                    break
                if not default_registry().is_bot(room.code, player.faction_id):
                    continue
                if failures.get(player.faction_id, 0) >= MAX_CONSECUTIVE_FAILURES:
                    self._log(
                        f"turn {turn}: {player.faction_name} suspended "
                        f"({MAX_CONSECUTIVE_FAILURES} consecutive failures)"
                    )
                    continue
                try:
                    result = orchestrator.run_bot_turn(room, player)
                    warnings = "; ".join(result["warnings"]) or "none"
                    self._log(
                        f"turn {turn}: {player.faction_name} "
                        f"{result['parsed']} order(s), warnings: {warnings}"
                    )
                    failures[player.faction_id] = 0
                except Exception as exc:  # noqa: BLE001 - per-bot, keep going
                    failures[player.faction_id] = failures.get(player.faction_id, 0) + 1
                    self._log(
                        f"turn {turn}: {player.faction_name} FAILED "
                        f"{type(exc).__name__}: {exc}"
                    )
            if self._stop_flag.is_set():
                break
            force = bool(
                self._status.get("force") or not self._status.get("wait_humans")
            )
            if force or room.all_submitted(turn):
                try:
                    resolved = service.resolve_turn(room, force=force)
                    with self._lock:
                        self._status["last_turn"] = resolved["turn"]
                        self._status["last_result"] = (
                            f"turn {resolved['turn']} resolved "
                            f"(seed {resolved['seed']})"
                        )
                        self._status["turns_done"] += 1
                        self._status["last_error"] = ""
                    self._log(self._status["last_result"])
                except Exception as exc:  # noqa: BLE001 - keep the room playable
                    self._log(
                        f"turn {turn}: resolution failed {type(exc).__name__}: {exc}"
                    )
                    with self._lock:
                        self._status["last_error"] = f"{type(exc).__name__}: {exc}"
                    self._sleep_or_stop()
                    continue
            else:
                waiting = ", ".join(self._status_waiting_on(room, turn))
                self._log(f"turn {turn}: waiting on {waiting}")
            with self._lock:
                if self._status["turns_done"] >= self._status["turns_planned"]:
                    self._log(f"planned {self._status['turns_planned']} turn(s) done")
                    break
            self._sleep_or_stop()

    def _sleep_or_stop(self) -> None:
        delay = float(self._status.get("delay", 5.0))
        for _ in range(max(1, int(delay / POLL_SECONDS))):
            if self._stop_flag.is_set():
                return
            time.sleep(POLL_SECONDS)

    def _status_waiting_on(self, room, turn: int) -> list[str]:
        bucket = room.submissions.get(turn, {})
        return [
            p.display_name for p in room.joined_players() if p.faction_id not in bucket
        ]

    def _log(self, line: str) -> None:
        with self._lock:
            self._status.setdefault("log", deque(maxlen=20)).append(
                f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {line}"
            )


def _idle_status() -> dict:
    return {
        "running": False,
        "code": "",
        "turns_done": 0,
        "turns_planned": 0,
        "delay": 5.0,
        "force": False,
        "wait_humans": False,
        "last_turn": 0,
        "last_result": "",
        "last_error": "",
        "started_at": "",
        "stopped_at": "",
        "log": [],
    }


_controller: AutoplayController | None = None


def default_controller() -> AutoplayController:
    global _controller
    if _controller is None:
        _controller = AutoplayController()
    return _controller
