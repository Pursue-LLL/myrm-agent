"""Loopback harness for running the imap-smtp-email skill script against a mail server the test scripts.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py, the script under test

[OUTPUT]
- SKILL_SCRIPTS, SCRIPT: the script directory and the script
- Session, serve_sessions: serve one scripted session per client on a loopback port
- run_email_script: run the script, or a copy of it such as the one the seed sync writes, in a child process with only the
  variables a skill run injects (and the ones the skill's settings add)

[POS]
Server pytest-only helper shared by the certificate tests and the command tests of the skill script. The script runs
in a child process the server's own policy never reaches, so these tests talk to it over a real socket.
"""

from __future__ import annotations

import os
import socket
import ssl
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "imap-smtp-email" / "scripts"
SCRIPT = SKILL_SCRIPTS / "email_manager.py"

Session = Callable[[socket.socket, ssl.SSLContext], None]


@contextmanager
def serve_sessions(session: Session, context: ssl.SSLContext) -> Iterator[int]:
    """Serve one client at a time on a loopback port; a client that rejects the certificate only ends its own session."""
    server = socket.create_server(("127.0.0.1", 0))
    server.settimeout(0.2)
    stopped = threading.Event()

    def serve() -> None:
        while not stopped.is_set():
            try:
                conn, _addr = server.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            try:
                session(conn, context)
            except (OSError, ssl.SSLError):
                pass
            finally:
                conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield server.getsockname()[1]
    finally:
        stopped.set()
        thread.join(timeout=5)
        server.close()


def run_email_script(
    tmp_path: Path,
    args: list[str],
    *,
    port: int,
    protocol: str = "imap",
    trust: Path | None = None,
    script: Path = SCRIPT,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run *script* (the source tree's by default, or another copy of it) from another directory with a minimal environment, as a skill run does.

    *extra_env* is what the skill's settings add on top, and wins over the defaults.
    """
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
    env |= {
        "HOME": str(tmp_path),
        "EMAIL_IMAP_HOST": "127.0.0.1",
        "EMAIL_IMAP_USER": "agent@example.test",
        "EMAIL_IMAP_PASSWORD": "secret",
        f"EMAIL_{protocol.upper()}_PORT": str(port),
    }
    if protocol == "smtp":
        env["EMAIL_SMTP_HOST"] = "127.0.0.1"
    if trust is not None:
        env["SSL_CERT_FILE"] = str(trust)
    env |= extra_env or {}
    return subprocess.run(
        [sys.executable, str(script), *args], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60, check=False
    )
