"""The ceiling on the endpoints that spend something.

Opening rooms writes games and takes seats; running a bot spends the
operator's LLM key. `SOE_BETA_ACCESS_CODE` decides who may start, but it is
one shared string -- these limits are what stands between a copy of it and an
unbounded bill.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_rl_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_rl_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp import ratelimit  # noqa: E402
from webapp.main import app  # noqa: E402

client = TestClient(app)

#: Cheap and gated: the limit is charged before the room is looked up, so
#: every call here is a rate-limit decision and nothing else.
JOIN = "/api/join"
BOGUS = {"code": "ZZZZ", "pin": "0000", "name": "nobody"}


@pytest.fixture
def small_signup_limit(monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "signup", (3, 600.0))
    return 3


def test_calls_under_the_allowance_pass_through(small_signup_limit):
    for _ in range(small_signup_limit):
        assert client.post(JOIN, json=BOGUS).status_code == 400


def test_the_allowance_is_a_ceiling(small_signup_limit):
    for _ in range(small_signup_limit):
        client.post(JOIN, json=BOGUS)
    refused = client.post(JOIN, json=BOGUS)
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) >= 1


def test_each_visitor_gets_their_own_window(small_signup_limit):
    """One caller's spending must not lock everyone else out.

    Every request through a TLS terminator arrives from 127.0.0.1, so without
    reading the forwarded hop this whole limit would be a single global
    bucket -- one script could deny the alpha to all of it.
    """
    for _ in range(small_signup_limit + 1):
        client.post(JOIN, json=BOGUS, headers={"X-Forwarded-For": "198.51.100.7"})
    blocked = client.post(
        JOIN, json=BOGUS, headers={"X-Forwarded-For": "198.51.100.7"}
    )
    other = client.post(
        JOIN, json=BOGUS, headers={"X-Forwarded-For": "198.51.100.8"}
    )
    assert blocked.status_code == 429
    assert other.status_code == 400


def test_a_forged_leading_hop_does_not_buy_a_fresh_window(small_signup_limit):
    """The proxy appends the real peer, so only the last hop is trustworthy.

    Reading the first entry instead would let one caller mint a new bucket per
    request just by varying a header they control.
    """
    for i in range(small_signup_limit):
        response = client.post(
            JOIN,
            json=BOGUS,
            headers={"X-Forwarded-For": f"10.0.0.{i}, 198.51.100.9"},
        )
        assert response.status_code == 400
    refused = client.post(
        JOIN, json=BOGUS, headers={"X-Forwarded-For": "10.0.0.99, 198.51.100.9"}
    )
    assert refused.status_code == 429


def test_zero_turns_a_bucket_off(monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "signup", (0, 600.0))
    for _ in range(12):
        assert client.post(JOIN, json=BOGUS).status_code == 400


def test_the_window_is_charged_before_the_invite_is_checked(monkeypatch):
    """Otherwise the invite code itself is free to guess at."""
    monkeypatch.setattr("webapp.main.BETA_ACCESS_CODE", "the-real-invite")
    monkeypatch.setitem(ratelimit.LIMITS, "signup", (2, 600.0))
    assert client.post(JOIN, json=dict(BOGUS, invite="wrong")).status_code == 403
    assert client.post(JOIN, json=dict(BOGUS, invite="wrong")).status_code == 403
    assert client.post(JOIN, json=dict(BOGUS, invite="wrong")).status_code == 429


def test_reset_clears_every_window(small_signup_limit):
    for _ in range(small_signup_limit + 1):
        client.post(JOIN, json=BOGUS)
    assert client.post(JOIN, json=BOGUS).status_code == 429
    ratelimit.reset()
    assert client.post(JOIN, json=BOGUS).status_code == 400


def test_the_shipped_defaults_are_generous_enough_for_a_person():
    """A limit a coach can feel is a limit that gets removed in a hurry."""
    signup, signup_window = ratelimit.LIMITS["signup"]
    bot, bot_window = ratelimit.LIMITS["bot"]
    assert signup >= 20 and signup_window <= 900
    assert bot >= 40 and bot_window <= 3600
