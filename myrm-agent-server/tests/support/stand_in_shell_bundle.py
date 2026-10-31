"""A stand-in desktop bundle: an executable that acts like the shell, or misacts on purpose.

[INPUT]
- the caller's two loopback ports and a temporary directory to build the bundle in

[OUTPUT]
- Ports: the two ports a stand-in shell serves on
- stand_in_bundle(): a macOS `.app` or Linux `squashfs-root`-style directory whose executable starts a backend and a
  frontend as children on those ports, with a chosen behaviour (healthy, crash, leaky, ...), page and data

[POS]
Test double for scripts/ci/desktop-release/smoke_launch_shell.py: the smoke has to be shown to fail on every way the
product can misbehave, which a real bundle cannot be made to do on demand. POSIX only (the stand-in is a shell script).
"""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path
from typing import Protocol


class Ports(Protocol):
    backend: int
    frontend: int


_SERVER = """
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

role, port, frontend, data = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
PAGE = b'<script src="/_next/static/app.js"></script>' if frontend != "bare" else b"<html></html>"
STARTED = time.monotonic()
# The lists the backend builds from its bundled data, in the two response shapes the real API uses.
LISTS = {
    "/api/v1/skills/": {"skills": [{"id": "s"}], "total": 1},
    "/api/v1/agents/templates": {"success": True, "data": [{"id": "t"}]},
    "/api/v1/integrations/catalog": {"success": True, "data": {"entries": [{"id": "c"}], "total": 1}},
    "/api/v1/integrations/search/providers": {"success": True, "data": {"providers": [{"slug": "p"}]}},
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if role == "backend" and self.path == "/health":
            self.reply(b"ok")
        elif role == "backend" and self.path in LISTS:
            self.reply_list(self.path)
        elif role == "frontend" and self.path == "/":
            self.reply(PAGE)
        elif role == "frontend" and self.path == "/_next/static/app.js" and frontend == "complete":
            self.reply(b"//")
        else:
            self.send_error(404)

    def reply(self, body):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def reply_list(self, path):
        if data == "broken":
            self.send_error(500)
            return
        body = json.loads(json.dumps(LISTS[path]))
        withheld = data == "no-skills" or (data == "late-skills" and time.monotonic() - STARTED < 1.5)
        if withheld and path == "/api/v1/skills/":
            body["skills"] = []
        self.reply(json.dumps(body).encode())

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""

_SHELL = """#!{python}
import os
import signal
import subprocess
import sys
import time

BEHAVIOUR = "{behaviour}"
# Where the shell was started, for the test to read back; next to the executable is the one place a stand-in may write.
with open(os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), "cwd.txt"), "w") as record:
    record.write(os.getcwd())
if BEHAVIOUR == "crash":
    print("boom: cannot create the main window", flush=True)
    sys.exit(3)
if BEHAVIOUR == "canonical-path-only" and os.path.realpath(sys.argv[0]) != sys.argv[0]:
    # What Tauri does on macOS: a starting binary behind a symlink leaves the shell without its resources.
    print("Failed to resolve sidecar path: unknown path", flush=True)
    sys.exit(3)

SERVERS = [("backend", {backend})] + ([] if BEHAVIOUR == "backend-only" else [("frontend", {frontend})])
children = [subprocess.Popen([sys.executable, "-c", {server!r}, role, str(port), "{page}", "{data}"]) for role, port in SERVERS]


def quit_(*_args):
    if BEHAVIOUR != "leaky":
        for child in children:
            child.terminate()
            child.wait()
    sys.exit(0)


signal.signal(signal.SIGTERM, quit_)
while True:
    time.sleep(0.2)
"""


def stand_in_bundle(
    tmp_path: Path,
    ports: Ports,
    *,
    behaviour: str = "healthy",
    page: str = "complete",
    data: str = "full",
    executable: str = "AppRun",
) -> Path:
    """A bundle whose executable acts like the shell: it starts the backend and the Next server as children."""
    is_app = executable.startswith("Contents/")
    bundle = tmp_path / ("MyrmAgent.app" if is_app else "squashfs-root")
    shell = bundle / executable
    shell.parent.mkdir(parents=True)
    if is_app:
        (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleExecutable": shell.name}))
    shell.write_text(
        _SHELL.format(
            python=sys.executable,
            behaviour=behaviour,
            backend=ports.backend,
            frontend=ports.frontend,
            server=_SERVER,
            page=page,
            data=data,
        ),
        encoding="utf-8",
    )
    shell.chmod(0o755)
    return bundle
