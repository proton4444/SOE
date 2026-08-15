"""Local TLS terminator forwards to the loopback application worker."""

from __future__ import annotations

import shutil
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from scripts import https_proxy


def _openssl_works() -> bool:
    """Whether an openssl on PATH can actually issue a certificate.

    Being on PATH is not enough. The one Strawberry Perl installs on Windows
    answers `version` and then fails every real command, because it looks for
    a config file at a build-time path that does not exist on this machine.
    A drill this test cannot run is a skip; only a proxy that forwards wrong
    is a failure.
    """
    if not shutil.which("openssl"):
        return False
    # Has to be a real issue, not `-help`: the failure mode above answers
    # `version`, `-help` and `genrsa` with 0 and only breaks once a command
    # reads openssl.cnf.
    with tempfile.TemporaryDirectory() as work:
        try:
            return (
                subprocess.call(
                    [
                        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(Path(work) / "probe.key"),
                        "-out", str(Path(work) / "probe.crt"),
                        "-days", "1", "-subj", "/CN=probe",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                == 0
            )
        except OSError:
            return False


requires_openssl = pytest.mark.skipif(
    not _openssl_works(), reason="no working openssl on PATH to issue test certificates"
)


def _certs(tmp_path: Path) -> tuple[Path, Path]:
    ca_key = tmp_path / "ca.key"
    ca_crt = tmp_path / "ca.crt"
    leaf_key = tmp_path / "leaf.key"
    leaf_csr = tmp_path / "leaf.csr"
    leaf_crt = tmp_path / "leaf.crt"
    ext = tmp_path / "leaf.ext"
    ext.write_text(
        "subjectAltName=IP:127.0.0.2,DNS:soe.local\n", encoding="ascii"
    )
    subprocess.check_call(
        ["openssl", "genrsa", "-out", str(ca_key), "2048"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [
            "openssl", "req", "-x509", "-new", "-nodes", "-key", str(ca_key),
            "-sha256", "-days", "2", "-out", str(ca_crt), "-subj", "/CN=SOE test CA",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        ["openssl", "genrsa", "-out", str(leaf_key), "2048"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [
            "openssl", "req", "-new", "-key", str(leaf_key), "-out", str(leaf_csr),
            "-subj", "/CN=127.0.0.2",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [
            "openssl", "x509", "-req", "-in", str(leaf_csr), "-CA", str(ca_crt),
            "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(leaf_crt),
            "-days", "2", "-sha256", "-extfile", str(ext),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return leaf_crt, leaf_key, ca_crt


class _Upstream(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


@requires_openssl
def test_https_proxy_forwards_healthz_over_tls(tmp_path):
    leaf_crt, leaf_key, ca_crt = _certs(tmp_path)
    # SAN includes soe.local; the unit test binds loopback so it does not
    # depend on 127.0.0.2 being present. The operator drill still uses 127.0.0.2.
    ext = tmp_path / "leaf.ext"
    ext.write_text("subjectAltName=DNS:localhost,IP:127.0.0.1\n", encoding="ascii")
    subprocess.check_call(
        [
            "openssl", "x509", "-req", "-in", str(tmp_path / "leaf.csr"),
            "-CA", str(tmp_path / "ca.crt"), "-CAkey", str(tmp_path / "ca.key"),
            "-CAcreateserial", "-out", str(leaf_crt), "-days", "2", "-sha256",
            "-extfile", str(ext),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    upstream = HTTPServer(("127.0.0.1", 0), _Upstream)
    up_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    up_thread.start()
    holder = HTTPServer(("127.0.0.1", 0), _Upstream)
    listen_port = holder.server_address[1]
    holder.server_close()
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            https_proxy.serve(
                cert=leaf_crt,
                key=leaf_key,
                listen_host="127.0.0.1",
                listen_port=listen_port,
                upstream_host="127.0.0.1",
                upstream_port=upstream.server_address[1],
            )
        except BaseException as exc:  # noqa: BLE001 - surface bind failures
            errors.append(exc)

    threading.Thread(target=_run, daemon=True).start()
    deadline = time.time() + 3
    context = ssl.create_default_context()
    context.load_verify_locations(str(ca_crt))
    last_error: Exception | None = None
    try:
        while time.time() < deadline:
            if errors:
                raise errors[0]
            try:
                with urllib.request.urlopen(
                    f"https://127.0.0.1:{listen_port}/healthz",
                    context=context,
                    timeout=2,
                ) as response:
                    assert response.status == 200
                    assert b'"status"' in response.read()
                    return
            except Exception as exc:  # noqa: BLE001 - retry until listen
                last_error = exc
                time.sleep(0.05)
        raise AssertionError(f"proxy did not accept TLS: {last_error}")
    finally:
        upstream.shutdown()
