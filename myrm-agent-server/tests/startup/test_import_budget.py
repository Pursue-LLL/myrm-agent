"""Startup import gate: no outbound network and a bounded module count.

[INPUT]
- app.main (POS: HTTP application import surface)

[OUTPUT]
- Regression coverage that importing the server neither touches the network nor grows
  past its module budget.

[POS]
Startup tests. Importing the HTTP application must not wait on the network (litellm
downloads its price table from GitHub at import time unless the process is told to use the
packaged one) and must not silently grow: every extra module is CPU time spent on every
launch of the server and of the desktop sidecar.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]

# 8,206 modules were imported when this gate was introduced; the rest is ~10% headroom.
# Raise it deliberately, with a reason, when a feature genuinely needs more modules, never to
# silence an accidental eager import.
_MAX_IMPORTED_MODULES = 9_000

_RESULT_FILE_ENV = "MYRM_STARTUP_GATE_RESULT_FILE"

# Runs in a fresh interpreter so modules already imported by pytest cannot hide an eager
# import. Non-loopback DNS lookups and connects are recorded and refused, so a regression
# fails an assertion quickly instead of hanging on the network. The result goes to a file
# because imports print to stdout (litellm does).
_PROBE_SOURCE = f"""
import json
import os
import socket
import sys
from pathlib import Path

LOOPBACK = ("localhost", "127.0.0.1", "::1")
attempts = []
real_getaddrinfo = socket.getaddrinfo
real_connect = socket.socket.connect


def is_remote(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return isinstance(host, str) and host != "" and host not in LOOPBACK


def guarded_getaddrinfo(host, *args, **kwargs):
    if is_remote(host):
        attempts.append("dns:" + str(host))
        raise socket.gaierror("outbound network is blocked by the startup gate")
    return real_getaddrinfo(host, *args, **kwargs)


def guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and is_remote(address[0]):
        attempts.append("connect:" + str(address[0]))
        raise OSError("outbound network is blocked by the startup gate")
    return real_connect(self, address)


socket.getaddrinfo = guarded_getaddrinfo
socket.socket.connect = guarded_connect

import app.main  # noqa: E402,F401

result = dict(attempts=attempts, modules=len(sys.modules))
Path(os.environ[{_RESULT_FILE_ENV!r}]).write_text(json.dumps(result))
"""


@dataclass(frozen=True)
class _ImportProbe:
    outbound_attempts: tuple[str, ...]
    module_count: int


@pytest.fixture(scope="module")
def import_probe(tmp_path_factory: pytest.TempPathFactory) -> _ImportProbe:
    result_file = tmp_path_factory.mktemp("startup-gate") / "result.json"
    # The default under test comes from the app package itself, so an override exported in
    # the developer's shell must not leak into the child interpreter.
    env = {key: value for key, value in os.environ.items() if key != "LITELLM_LOCAL_MODEL_COST_MAP"}
    env[_RESULT_FILE_ENV] = str(result_file)
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE_SOURCE],
        cwd=_SERVER_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    payload = json.loads(result_file.read_text())
    return _ImportProbe(
        outbound_attempts=tuple(payload["attempts"]),
        module_count=int(payload["modules"]),
    )


def test_importing_app_main_makes_no_outbound_network_attempts(import_probe: _ImportProbe) -> None:
    assert import_probe.outbound_attempts == (), (
        f"Importing app.main reached the network, which stalls every server launch. Attempts: {import_probe.outbound_attempts}"
    )


def test_importing_app_main_stays_within_the_module_budget(import_probe: _ImportProbe) -> None:
    assert import_probe.module_count <= _MAX_IMPORTED_MODULES, (
        f"Importing app.main loads {import_probe.module_count} modules "
        f"(budget {_MAX_IMPORTED_MODULES}); look for a new eager import before raising the budget."
    )
