"""Route registration order: the first screen's routes come first.

[INPUT]
- app.main (POS: HTTP application; its registered route table)
- first_screen_requests.txt (POS: the requests the main screen makes on load, captured from the real frontend)

[OUTPUT]
- Regression coverage that /health is registered before every router, that the requests made before the readiness gate
  opens resolve at the head of the route table, and that every request the main screen makes resolves within the first
  part of it

[POS]
Startup tests. FastAPI matches routes in registration order and builds the route state of every router a request has to
walk past (dependency analysis and response fields, about 0.4 ms per route). A route registered at the end therefore makes
its first request build the whole table, about half a second of one event-loop turn on a fast machine and several times
that on a small one; the routers below the first-screen block are built by the warm-up after the screen has loaded.
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
_FIRST_SCREEN_FILE = Path(__file__).parent / "first_screen_requests.txt"

_HEALTH = "GET /health"

# What the screen sends while the readiness gate is still closed: the gate's own polls and the requests of the first
# burst. Whatever they match is built before the user sees anything, so these routers sit at the head of the table.
_BEFORE_READY = (
    "GET /api/v1/health",
    "GET /api/v1/health/liveness",
    "GET /api/v1/health/pressure",
    "GET /api/v1/health/update-status",
    "GET /api/v1/security/managed-policy/effective",
    "GET /api/v1/health/ready",
)
_MAX_BEFORE_READY_SHARE = 0.05

# The last first-screen route sits at 48% of the table; the rest is headroom for growth. Raise it deliberately, never to
# hide a router registered in front of the first-screen block.
_MAX_FIRST_SCREEN_SHARE = 0.55

_RESULT_FILE_ENV = "MYRM_ROUTE_ORDER_RESULT_FILE"


def _first_screen_requests() -> list[tuple[str, str]]:
    requests: list[tuple[str, str]] = []
    for line in _FIRST_SCREEN_FILE.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            method, path = line.split(" ", 1)
            requests.append((method, path))
    return requests


_REQUESTS = [("GET", "/health"), *_first_screen_requests()]

# Runs in a fresh interpreter, like the other startup gates, so the application is the one a launch builds. The result
# goes to a file because imports may print to stdout.
_PROBE_SOURCE = f"""
import json
import os
from pathlib import Path

from fastapi.routing import iter_route_contexts

import app.main  # noqa: E402,F401

requests = {_REQUESTS!r}
contexts = list(iter_route_contexts(app.main.app.routes))


def first_match(method, path):
    for position, context in enumerate(contexts):
        if method in (context.methods or ()) and context.path_regex is not None and context.path_regex.match(path):
            return position
    return None


result = dict(
    total=len(contexts),
    positions={{f"{{method}} {{path}}": first_match(method, path) for method, path in requests}},
)
Path(os.environ[{_RESULT_FILE_ENV!r}]).write_text(json.dumps(result))
"""


@dataclass(frozen=True)
class _RouteOrder:
    total: int
    positions: dict[str, int | None]

    def share(self, request: str) -> float:
        position = self.positions[request]
        assert position is not None, f"{request} matches no registered route"
        return position / self.total


@pytest.fixture(scope="module")
def route_order(tmp_path_factory: pytest.TempPathFactory) -> _RouteOrder:
    result_file = tmp_path_factory.mktemp("route-order") / "result.json"
    env = dict(os.environ)
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
    return _RouteOrder(total=int(payload["total"]), positions=dict(payload["positions"]))


def test_every_first_screen_request_resolves_to_a_route(route_order: _RouteOrder) -> None:
    unresolved = [request for request, position in route_order.positions.items() if position is None]
    assert not unresolved, (
        f"first-screen requests that match no registered route (update tests/startup/first_screen_requests.txt "
        f"if the route moved): {unresolved}"
    )


def test_health_is_registered_before_every_router(route_order: _RouteOrder) -> None:
    health = route_order.positions[_HEALTH]
    first_router_route = min(
        position for request, position in route_order.positions.items() if request != _HEALTH and position is not None
    )
    assert health is not None
    assert health < first_router_route, (
        "/health must be registered before the routers: registered last, its first request builds the whole route table"
    )


def test_requests_before_the_readiness_gate_opens_resolve_at_the_head_of_the_table(route_order: _RouteOrder) -> None:
    shares = {request: route_order.share(request) for request in _BEFORE_READY}
    late = {request: f"{share:.0%}" for request, share in shares.items() if share > _MAX_BEFORE_READY_SHARE}
    assert not late, (
        f"requests the screen makes before the backend is reported ready resolve late in the route table: {late}. Each "
        "builds every router in front of it before the user sees anything; register its router at the head of app/api/router.py."
    )


def test_first_screen_routes_sit_in_the_first_part_of_the_route_table(route_order: _RouteOrder) -> None:
    latest = max((position, request) for request, position in route_order.positions.items() if position is not None)
    share = latest[0] / route_order.total
    assert share <= _MAX_FIRST_SCREEN_SHARE, (
        f"{latest[1]} is route {latest[0]} of {route_order.total} ({share:.0%}); the first screen builds every router in front of "
        "it, so a router registered above the first-screen block of app/api/router.py delays it. Move the router into the block "
        "if the screen calls it, below the block if it does not."
    )
