"""The loopback operator fallback, once a TLS terminator is in front.

Without `SOE_OPERATOR_KEY` the server treats its own console as the operator,
which is a convenience for a laptop and a hole in the documented deployment:
`deploy/Caddyfile` and `scripts/https_proxy.py` both forward to 127.0.0.1, so
every visitor on the internet arrives from a loopback address. These pin the
rule that closes it -- a proxied request is never the console, whatever
address the socket reports.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_opproxy_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_opproxy_games_{uuid.uuid4().hex[:8]}"),
)

from fastapi.testclient import TestClient  # noqa: E402

from webapp import main as web_main  # noqa: E402
from webapp.main import app  # noqa: E402

OPERATOR = "operator-secret-for-tests"
#: An operator-only page, cheap to fetch and with nothing to set up. Note it
#: is a GET: `/llm-settings` renders for anyone and masks what it shows, so it
#: proves nothing about the gate.
OPERATOR_PAGE = "/ops/alpha"

console = TestClient(app, client=("127.0.0.1", 51000))


@pytest.fixture(autouse=True)
def _no_configured_key(monkeypatch):
    """The unconfigured case: the fallback is all that decides."""
    monkeypatch.setattr(web_main, "OPERATOR_KEY", "")
    console.cookies.clear()


def test_console_on_loopback_is_the_operator():
    assert console.get(OPERATOR_PAGE).status_code == 200


@pytest.mark.parametrize(
    "header",
    [
        {"X-Forwarded-For": "203.0.113.9"},
        {"X-Forwarded-Proto": "https"},
        {"X-Forwarded-Host": "beta.example.org"},
        {"X-Real-IP": "203.0.113.9"},
        {"Forwarded": "for=203.0.113.9;proto=https"},
    ],
)
def test_loopback_behind_a_proxy_is_not_the_operator(header):
    response = console.get(OPERATOR_PAGE, headers=header)
    assert response.status_code == 403
    assert "proxy" in response.json()["detail"]


def test_a_configured_key_still_works_through_the_proxy(monkeypatch):
    """The fix must not cost the operator their own dashboard over HTTPS."""
    monkeypatch.setattr(web_main, "OPERATOR_KEY", OPERATOR)
    response = console.get(
        OPERATOR_PAGE,
        headers={
            "X-Forwarded-For": "203.0.113.9",
            web_main.OPERATOR_HEADER: OPERATOR,
        },
    )
    assert response.status_code == 200


def test_a_visitor_through_the_proxy_without_the_key_is_refused(monkeypatch):
    monkeypatch.setattr(web_main, "OPERATOR_KEY", OPERATOR)
    response = console.get(
        OPERATOR_PAGE, headers={"X-Forwarded-For": "203.0.113.9"}
    )
    assert response.status_code == 403


def test_a_remote_address_was_never_the_operator():
    remote = TestClient(app, client=("203.0.113.9", 51000))
    assert remote.get(OPERATOR_PAGE).status_code == 403
