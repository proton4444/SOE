"""Fixtures every test in this directory gets.

The rate limit in `webapp.ratelimit` remembers callers across requests, which
is the whole point in production and a cross-test coupling here: every
TestClient presents the same address, so without this a test's allowance would
depend on how many tests happened to run before it. Each test starts with
empty windows.
"""

from __future__ import annotations

import pytest

try:
    from webapp import ratelimit
except ImportError:  # pragma: no cover - engine-only environment, no fastapi
    ratelimit = None


@pytest.fixture(autouse=True)
def _fresh_rate_limit_windows():
    if ratelimit is None:
        yield
        return
    ratelimit.reset()
    yield
    ratelimit.reset()
