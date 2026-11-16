"""A session id outside the safe charset is a 404 on every goals route that carries one, before storage is read.

[INPUT]
- app.api.goals.router (POS: Goal HTTP endpoints for the frontend)
- app.api.dependencies::require_safe_session_id (POS: Router-level guard answering 404 for a path session id outside the safe charset)

[OUTPUT]
- A case sending ids a storage key cannot carry (NUL byte, newline, `..`) and ids merely outside the charset to
  every session-scoped route in the router's own OpenAPI schema: each answer is the guard's 404 and storage stays silent.
- A case proving that schema lists the routes of every nested router, so the sweep cannot pass by finding nothing.
- A case proving well-formed ids the router has never seen, and routes without a session id, are still served.
"""

from __future__ import annotations

import logging
import re

import pytest
from fastapi.testclient import TestClient

_STORAGE_LOGGER = "myrm_agent_harness.agent.goals.storage"
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_BODY_METHODS = ("POST", "PUT", "PATCH")

# As sent on the wire. The local storage backend rejects a NUL byte, a newline and `..` in a key, so an unguarded
# read fails on them; a backslash and a dot are outside the charset yet harmless as keys.
_UNSAFE_IDS = ["x%00y", "x%0Ay", "%2e%2e", "x%5Cy", "has.dot"]

# Shapes the system itself issues: web chat, kanban task, and uuid ids.
_WELL_FORMED_IDS = ["c-lzx1k-9a-3f2e-1", "kanban:0123456789ab", "3f2b8c1e-5d4a-4e7b-9c10-a1b2c3d4e5f6"]


def _session_scoped_operations(client: TestClient) -> list[tuple[str, str]]:
    """Each (method, path template) the app publishes whose path carries `{session_id}`."""
    paths = client.get("/openapi.json").json()["paths"]
    return [
        (method.upper(), path)
        for path, item in paths.items()
        if "{session_id}" in path
        for method in item
        if method in _HTTP_METHODS
    ]


def _send(client: TestClient, method: str, path: str, session_id: str) -> tuple[int, str]:
    """Status code and body of one operation called with `session_id` in its path.

    Other path parameters get a value valid for any type; a body-carrying method sends an empty JSON object.
    """
    url = re.sub(r"\{\w+\}", "1", path.replace("{session_id}", session_id))
    response = client.request(method, url, json={} if method in _BODY_METHODS else None)
    return response.status_code, response.text


def _storage_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == _STORAGE_LOGGER and r.levelno >= logging.WARNING]


@pytest.mark.parametrize("unsafe_id", _UNSAFE_IDS)
def test_an_unsafe_session_id_is_not_found_on_every_session_route(
    client: TestClient, unsafe_id: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=_STORAGE_LOGGER):
        outcomes = {
            f"{method} {path}": _send(client, method, path, unsafe_id) for method, path in _session_scoped_operations(client)
        }

    assert {operation: status for operation, (status, _) in outcomes.items()} == dict.fromkeys(outcomes, 404)
    # The guard's own message: a routing miss would also be a 404 but would say "Not Found".
    assert all("Session not found" in body for _, body in outcomes.values())
    assert _storage_warnings(caplog) == []


def test_the_sweep_covers_the_routes_of_every_nested_router(client: TestClient) -> None:
    operations = _session_scoped_operations(client)

    assert ("GET", "/api/v1/goals/{session_id}/status") in operations
    assert ("GET", "/api/v1/goals/{session_id}/plan") in operations
    assert ("GET", "/api/v1/goals/{session_id}/constraints") in operations
    assert ("POST", "/api/v1/goals/{session_id}/queue/reorder") in operations


@pytest.mark.parametrize("session_id", _WELL_FORMED_IDS)
def test_a_well_formed_session_id_the_router_has_never_seen_is_served(client: TestClient, session_id: str) -> None:
    status = client.get(f"/api/v1/goals/{session_id}/status")
    queue = client.get(f"/api/v1/goals/{session_id}/queue")

    assert status.status_code == 200
    assert status.json() == {"goal": None}
    assert queue.status_code == 200


def test_a_route_without_a_session_id_is_not_guarded(client: TestClient) -> None:
    response = client.get("/api/v1/goals/active")

    assert response.status_code == 200
    assert isinstance(response.json()["goals"], list)
