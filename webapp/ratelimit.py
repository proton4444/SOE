"""A fixed-window rate limit for the handful of endpoints that cost something.

Two things on this server spend a resource that is not the caller's: opening a
room writes a game to disk and takes a seat, and running a bot turn makes a
live LLM call on the operator's key. ``SOE_BETA_ACCESS_CODE`` gates who may
start, but an invite code is a shared secret -- once it circulates, nothing
else stands between one loop and the operator's bill.

In-process and per-worker by design. The controlled beta runs a single worker
(``scripts/start_beta.ps1``), so one process's window is the whole server. A
count of ``0`` turns a bucket off.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request

from webapp.net import client_ip


def _count(name: str, default: int) -> int:
    """Read a per-window allowance from the environment, ignoring nonsense."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


#: bucket -> (requests allowed, window in seconds). Generous on purpose: this
#: is a ceiling on scripted abuse, not a throttle a person can feel.
LIMITS: Dict[str, Tuple[int, float]] = {
    "signup": (_count("SOE_RATE_LIMIT_SIGNUP", 30), 600.0),
    "bot": (_count("SOE_RATE_LIMIT_BOT", 60), 3600.0),
}

#: Above this many tracked callers we drop the windows that have fully expired.
#: Forged addresses are cheap to invent; unbounded memory is not.
_MAX_TRACKED = 4096

_HITS: Dict[Tuple[str, str], Deque[float]] = {}
_LOCK = threading.Lock()


def reset() -> None:
    """Forget every window. For tests, and for an operator restarting a season."""
    with _LOCK:
        _HITS.clear()


def _prune(now: float) -> None:
    """Drop callers whose window has fully passed. Caller holds the lock.

    Only once the map has actually grown: a caller's own window is trimmed
    when they next call, so the common path should not walk every key it has
    ever seen to find that out.
    """
    if len(_HITS) <= _MAX_TRACKED:
        return
    for key, hits in list(_HITS.items()):
        window = LIMITS.get(key[0], (0, 0.0))[1]
        while hits and now - hits[0] > window:
            hits.popleft()
        if not hits:
            del _HITS[key]


def check(request: Request, bucket: str) -> None:
    """Record one call and raise 429 when the caller is over the allowance."""
    allowed, window = LIMITS.get(bucket, (0, 0.0))
    if allowed <= 0:
        return
    key = (bucket, client_ip(request))
    now = time.monotonic()
    with _LOCK:
        _prune(now)
        hits = _HITS.setdefault(key, deque())
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= allowed:
            retry_after = max(1, int(window - (now - hits[0])) + 1)
            raise HTTPException(
                429,
                "Too many requests. Wait a moment and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
