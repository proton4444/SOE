"""TLS terminator in front of the loopback application worker.

The application never speaks TLS. This process binds a separate loopback
address (default 127.0.0.2) so ``check_https.ps1`` can prove port 8000 is
not reachable on the public hostname while still forwarding to
``127.0.0.1:8000``.
"""

from __future__ import annotations

import argparse
import http.client
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class _Proxy(BaseHTTPRequestHandler):
    upstream_host = "127.0.0.1"
    upstream_port = 8000

    def log_message(self, format, *args):  # noqa: A003 - BaseHTTPRequestHandler API
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def do_GET(self) -> None:  # noqa: N802
        self._forward()

    def do_HEAD(self) -> None:  # noqa: N802
        self._forward()

    def do_POST(self) -> None:  # noqa: N802
        self._forward()

    def do_PUT(self) -> None:  # noqa: N802
        self._forward()

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward()

    def do_PATCH(self) -> None:  # noqa: N802
        self._forward()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._forward()

    def _respond_simple(self, status: int, message: str) -> None:
        body = message.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _forward(self) -> None:
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            # Hop-by-hop TE was stripped below; a chunked body cannot be
            # forwarded without de-chunking it first, so refuse honestly.
            self._respond_simple(
                501, "Chunked request bodies are not supported by this proxy."
            )
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._respond_simple(400, "Invalid Content-Length header.")
            return
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in _HOP_BY_HOP
        }
        headers["Host"] = f"{self.upstream_host}:{self.upstream_port}"
        # Tell the application a hop happened, and who the visitor was. Both
        # matter upstream: without this every caller looks like 127.0.0.1, so
        # the loopback operator fallback would open to anyone and every
        # visitor would share one rate-limit bucket. Append rather than
        # replace, and read the last entry upstream: whatever the client sent
        # ahead of ours stays where it can only be ignored.
        peer = self.client_address[0] if self.client_address else ""
        seen = ""
        for key in [k for k in headers if k.lower() == "x-forwarded-for"]:
            seen = headers.pop(key)
        headers["X-Forwarded-For"] = f"{seen}, {peer}" if seen else peer
        for key in [k for k in headers if k.lower() == "x-forwarded-proto"]:
            headers.pop(key)
        headers["X-Forwarded-Proto"] = "https"
        conn = http.client.HTTPConnection(
            self.upstream_host, self.upstream_port, timeout=30
        )
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            response = conn.getresponse()
            payload = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in _HOP_BY_HOP:
                    self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        finally:
            conn.close()


def serve(
    *,
    cert: Path,
    key: Path,
    listen_host: str = "127.0.0.2",
    listen_port: int = 8443,
    upstream_host: str = "127.0.0.1",
    upstream_port: int = 8000,
) -> None:
    _Proxy.upstream_host = upstream_host
    _Proxy.upstream_port = upstream_port
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(key))
    httpd = ThreadingHTTPServer((listen_host, listen_port), _Proxy)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    print(
        f"https://{listen_host}:{listen_port} -> "
        f"http://{upstream_host}:{upstream_port}",
        flush=True,
    )
    httpd.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cert", required=True, type=Path)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--listen-host", default="127.0.0.2")
    parser.add_argument("--listen-port", type=int, default=8443)
    parser.add_argument("--upstream-host", default="127.0.0.1")
    parser.add_argument("--upstream-port", type=int, default=8000)
    args = parser.parse_args()
    if not args.cert.is_file() or not args.key.is_file():
        print("Certificate or key is missing.", file=sys.stderr)
        return 2
    serve(
        cert=args.cert,
        key=args.key,
        listen_host=args.listen_host,
        listen_port=args.listen_port,
        upstream_host=args.upstream_host,
        upstream_port=args.upstream_port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
