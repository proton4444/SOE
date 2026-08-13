"""
Phase 0 run bundle (WP4): every execution writes a self-contained, resumable
bundle under ``games/arena/<run_id>/``.

    manifest.json                     provenance + status (atomic)
    games.jsonl                       one append-only line per game start
    turns.jsonl                       one append-only line per resolved turn
    decisions/<game_id>/turn_<n>_<faction>.json   decision trace (atomic)
    orders/<game_id>/turn_<n>_<faction>.txt       orders as submitted to parser
    blueprints/                       hashed copies of the frozen blueprints
    ARENA_REPORT.md                   rendered at completion

Resume contract: every record is append-only or atomically replaced; the
idempotent key is ``game + turn + faction``; a resumed run replays games from
turn 1, reusing recorded decisions instead of calling the model, and refuses
to start if manifest, prompt, blueprint, map or commit changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from soe import __version__ as ENGINE_VERSION

SCHEMA_VERSION = "1"

#: Fields of the manifest that, if changed, invalidate a resume. ``git_commit``
#: and ``blueprints`` are verified separately (commit via git, blueprints
#: normalized to id+hash), so they are not compared as raw values here.
_IMMUTABLE_MANIFEST_KEYS = (
    "schema_version",
    "mode",
    "map",
    "map_hash",
    "prompt_hashes",
    "model",
    "temperature",
    "max_tokens",
    "retry_policy",
    "seed_pairs",
    "turns",
    "entrants",
    "max_spend_usd",
    "seats",
)


def _normalise_blueprints(entries) -> dict[str, str]:
    """Normalise blueprint manifest entries to {id: hash}."""
    if not isinstance(entries, list):
        return {}
    return {
        str(entry.get("id", "")): str(entry.get("hash", ""))
        for entry in entries
        if isinstance(entry, dict)
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def state_sha(game_state) -> str:
    """Deterministic content hash of a GameState (for turns.jsonl)."""
    canonical = json.dumps(
        asdict(game_state), sort_keys=True, separators=(",", ":"), default=str
    )
    return sha256_bytes(canonical.encode("utf-8"))


def git_provenance(repo_root: Path) -> dict:
    """Commit and dirty flag of the repository running the batch."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {"git_commit": "unknown", "git_dirty": True}
    if head.returncode != 0:
        return {"git_commit": "unknown", "git_dirty": True}
    dirty = bool(status.stdout.strip())
    return {
        "git_commit": head.stdout.strip(),
        "git_dirty": dirty,
    }


class BundleError(RuntimeError):
    """The bundle is missing, truncated, or incompatible with a resume."""


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")
        handle.flush()


class RunBundle:
    """Writes and reads one run bundle. Append-only where the resume contract
    depends on it; decision records are atomic per idempotent key."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.run_id = self.run_dir.name
        self.manifest_path = self.run_dir / "manifest.json"
        self.games_path = self.run_dir / "games.jsonl"
        self.turns_path = self.run_dir / "turns.jsonl"
        self.decisions_dir = self.run_dir / "decisions"
        self.orders_dir = self.run_dir / "orders"
        self.blueprints_dir = self.run_dir / "blueprints"

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def start(cls, run_dir: Path, manifest_fields: dict) -> "RunBundle":
        run_dir = Path(run_dir)
        if (run_dir / "manifest.json").exists():
            raise BundleError(f"Run already exists at {run_dir}")
        bundle = cls(run_dir)
        bundle.run_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": bundle.run_id,
            "status": "running",
            "engine_version": ENGINE_VERSION,
            "started_at": now_iso(),
            "completed_at": None,
        }
        manifest.update(manifest_fields)
        _atomic_write_text(bundle.manifest_path, json.dumps(manifest, indent=2))
        return bundle

    def load_manifest(self) -> dict:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleError(f"Manifest unreadable for {self.run_id}") from exc
        if not isinstance(data, dict):
            raise BundleError(f"Manifest is not an object for {self.run_id}")
        return data

    def finish(self, status: str, report_markdown: str = "", extra: dict | None = None) -> dict:
        manifest = self.load_manifest()
        manifest["status"] = status
        manifest["completed_at"] = now_iso()
        if extra:
            manifest.update(extra)
        _atomic_write_text(self.manifest_path, json.dumps(manifest, indent=2))
        if report_markdown:
            _atomic_write_text(self.run_dir / "ARENA_REPORT.md", report_markdown)
        return manifest

    # ------------------------------------------------------------------
    # records
    # ------------------------------------------------------------------

    def record_game(self, game_id: str, payload: dict) -> None:
        _append_jsonl(self.games_path, {"game_id": game_id, **payload})

    def record_turn(self, payload: dict) -> None:
        _append_jsonl(self.turns_path, payload)

    def get_turn(self, game_id: str, turn: int) -> dict | None:
        """The recorded turn record for one game+turn (resume verification)."""
        if not self.turns_path.exists():
            return None
        target = (game_id, turn)
        for line in reversed(self.turns_path.read_text(encoding="utf-8").splitlines()):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("game") == target[0] and record.get("turn") == target[1]:
                return record
        return None

    def decision_path(self, game_id: str, turn: int, faction_id: str) -> Path:
        return self.decisions_dir / game_id / f"turn_{turn}_{faction_id}.json"

    def orders_path(self, game_id: str, turn: int, faction_id: str) -> Path:
        return self.orders_dir / game_id / f"turn_{turn}_{faction_id}.txt"

    def decision_key(self, game_id: str, turn: int, faction_id: str) -> tuple:
        return (game_id, turn, faction_id)

    def get_decision(self, game_id: str, turn: int, faction_id: str) -> dict | None:
        path = self.decision_path(game_id, turn, faction_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleError(f"Truncated decision record: {path}") from exc

    def record_decision(
        self,
        game_id: str,
        turn: int,
        faction_id: str,
        trace: dict,
    ) -> bool:
        """Atomically record one decision. Returns False when the idempotent
        key already exists (the decision was already recorded)."""
        path = self.decision_path(game_id, turn, faction_id)
        if path.exists():
            return False
        trace = dict(trace)
        trace.update(
            {
                "game": game_id,
                "turn": turn,
                "faction_id": faction_id,
                "recorded_at": now_iso(),
            }
        )
        _atomic_write_text(path, json.dumps(trace, indent=2, default=str))
        return True

    def record_orders_text(
        self, game_id: str, turn: int, faction_id: str, text: str
    ) -> None:
        _atomic_write_text(self.orders_path(game_id, turn, faction_id), text)

    def copy_blueprints(self, source_paths: dict[str, Path]) -> list[dict]:
        """Copy frozen blueprint files into the bundle; returns hashes.

        The id becomes a filename, so it is confined here too: the bundle must
        not be able to write outside its own ``blueprints/`` directory.
        """
        entries = []
        root = self.blueprints_dir.resolve()
        for blueprint_id, path in source_paths.items():
            target = (self.blueprints_dir / f"{blueprint_id}.json").resolve()
            if not target.is_relative_to(root) or target.name != f"{blueprint_id}.json":
                raise BundleError(
                    f"Invalid blueprint id {blueprint_id!r}: would write outside "
                    f"{root}"
                )
            data = Path(path).read_bytes()
            digest = sha256_bytes(data)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            entries.append({"id": blueprint_id, "hash": digest, "file": target.name})
        return entries

    # ------------------------------------------------------------------
    # resume helpers
    # ------------------------------------------------------------------

    def recorded_keys(self) -> set[tuple]:
        keys: set[tuple] = set()
        for path in self.decisions_dir.glob("*/turn_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BundleError(f"Truncated decision record: {path}") from exc
            keys.add((data.get("game", ""), int(data.get("turn", 0)), data.get("faction_id", "")))
        return keys


def validate_resume_bundle(
    bundle: RunBundle, expected: dict, repo_root: Path
) -> None:
    """Refuse a resume when provenance or configuration changed."""
    manifest = bundle.load_manifest()
    if manifest.get("status") == "complete":
        raise BundleError(f"Run {bundle.run_id} is already complete; not resuming.")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise BundleError(
            f"Schema mismatch: bundle={manifest.get('schema_version')} "
            f"runner={SCHEMA_VERSION}"
        )
    for key in _IMMUTABLE_MANIFEST_KEYS:
        if manifest.get(key) != expected.get(key):
            raise BundleError(
                f"Resume refused: manifest field '{key}' changed "
                f"(bundle={manifest.get(key)!r}, config={expected.get(key)!r})"
            )
    if _normalise_blueprints(manifest.get("blueprints")) != _normalise_blueprints(
        expected.get("blueprints")
    ):
        raise BundleError(
            "Resume refused: blueprint hashes changed "
            f"(bundle={_normalise_blueprints(manifest.get('blueprints'))}, "
            f"config={_normalise_blueprints(expected.get('blueprints'))})"
        )
    provenance = git_provenance(repo_root)
    if provenance["git_commit"] != manifest.get("git_commit"):
        raise BundleError(
            f"Resume refused: git commit changed "
            f"(bundle={manifest.get('git_commit')}, now={provenance['git_commit']})"
        )
