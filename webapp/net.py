"""Who a request actually came from, once a TLS terminator is in front.

The application never speaks TLS. Both documented deployments put a reverse
proxy on the same host -- ``deploy/Caddyfile`` and ``scripts/https_proxy.py``
both forward to ``127.0.0.1:8000`` -- so ``request.client.host`` reads
``127.0.0.1`` for every visitor on the internet. Anything that reasons about
*who* is calling has to read the forwarded hop instead, and first has to know
that a hop happened at all.
"""

from __future__ import annotations

from fastapi import Request

#: Headers a reverse proxy adds on the way through. Their presence is what
#: tells us the peer on the socket is the proxy and not the visitor. Caddy
#: sets the first three; ``scripts/https_proxy.py`` sets ``X-Forwarded-For``.
PROXY_HEADERS = (
    "x-forwarded-for",
    "x-forwarded-proto",
    "x-forwarded-host",
    "x-real-ip",
    "forwarded",
)


def arrived_via_proxy(request: Request) -> bool:
    """True when this request crossed a reverse proxy to reach us.

    A visitor can of course send ``X-Forwarded-For`` themselves. That only
    ever costs them: every caller of this function treats a proxied request as
    *less* trusted, never more.
    """
    return any(header in request.headers for header in PROXY_HEADERS)


def client_ip(request: Request) -> str:
    """The visitor's address, seen through one trusted proxy hop.

    A proxy appends the socket peer to ``X-Forwarded-For``, so with exactly
    one hop in front the last entry is the real visitor and everything to its
    left is whatever the visitor chose to claim. Reading the last entry is
    what makes this usable as a rate-limit key: the leftmost one is free to
    forge, and a forged key would let one caller spread its spending across as
    many buckets as it likes.

    Behind two hops (a CDN in front of Caddy) the last entry is the CDN's
    address and the visitors it fronts share a bucket. That is a coarse limit,
    not a broken one.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    client = request.client
    return (client.host if client else "").strip() or "unknown"
