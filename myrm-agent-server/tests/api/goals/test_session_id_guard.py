"""A path parameter outside the safe charset is a 404 on every goals route that carries one, before storage is read.

[INPUT]
- app.api.goals.router (POS: Goal HTTP endpoints for the frontend)
- app.api.dependencies::require_safe_path_ids (POS: Router-level guard answering 404 for a path parameter outside the safe id charset)

[OUTPUT]
- A case sending ids a storage key cannot carry (NUL byte, newline, `..`), an id too long for a file name, and ids
  merely outside the charset to every path parameter of every route in the router's own OpenAPI schema (session id,
  queued goal id, subgoal index): each answer is the guard's 404 and storage stays silent.
- A case proving that schema lists the routes of every nested router and every kind of path parameter, so the sweep
  cannot pass by finding nothing.
- A case proving well-formed ids the router has never seen, and routes without a path parameter, are still served.
"""

from __future__ import annotations

import logging
import re
import uuid

import pytest
from fastapi.testclient import TestClient

_STORAGE_LOGGER = "myrm_agent_harness.agent.goals.storage"
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_BODY_METHODS = ("POST", "PUT", "PATCH")
_PATH_PARAMETER = re.compile(r"\{(\w+)\}")

# As sent on the wire. The local storage backend fails on a key with a NUL byte or a newline or whose last component
# is `..`, so an unguarded read fails on them; a backslash and a dot are outside the charset yet harmless as keys.
# 256 characters is one past the 255 a chat id column holds and too long a file name, so an unguarded write fails.
_UNSAFE_IDS = ["x%00y", "x%0Ay", "%2e%2e", "x%5Cy", "has.dot", "a" * 256]

# Shapes the system itself issues: web chat, kanban task, and uuid ids, and the longest chat id.
_WELL_FORMED_IDS = [
    "c-lzx1k-9a-3f2e-1",
    "kanban:0123456789ab",
    "3f2b8c1e-5d4a-4e7b-9c10-a1b2c3d4e5f6",
    pytest.param("a" * 255, id="255-characters"),
]


def _path_parameters(client: TestClient) -> list[tuple[str, str, str]]:
    """Each (method, path template, parameter name) the app publishes for a path parameter."""
    paths = client.get("/openapi.json").json()["paths"]
    return [
        (method.upper(), path, name)
        for path, item in paths.items()
        for method in item
        if method in _HTTP_METHODS
        for name in _PATH_PARAMETER.findall(path)
    ]


def _send(client: TestClient, method: str, path: str, name: str, value: str) -> tuple[int, str]:
    """Status code and body of one operation called with `value` in its path parameter `name`.

    Other path parameters get a value valid for any type; a body-carrying method sends an empty JSON object.
    """
    url = _PATH_PARAMETER.sub(lambda match: value if match.group(1) == name else "1", path)
    response = client.request(method, url, json={} if method in _BODY_METHODS else None)
    return response.status_code, response.text


def _storage_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == _STORAGE_LOGGER and r.levelno >= logging.WARNING]


@pytest.mark.parametrize("unsafe_id", _UNSAFE_IDS)
def test_an_unsafe_path_parameter_is_not_found_on_every_route(
    client: TestClient, unsafe_id: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=_STORAGE_LOGGER):
        outcomes = {
            f"{method} {path} {name}": _send(client, method, path, name, unsafe_id)
            for method, path, name in _path_parameters(client)
        }

    assert {operation: status for operation, (status, _) in outcomes.items()} == dict.fromkeys(outcomes, 404)
    # The guard's own message: a routing miss would also be a 404 but would say "Not Found".
    assert all("Resource not found" in body for _, body in outcomes.values())
    assert _storage_warnings(caplog) == []


def test_the_sweep_covers_the_routes_and_parameters_of_every_nested_router(client: TestClient) -> None:
    parameters = _path_parameters(client)

    assert ("GET", "/api/v1/goals/{session_id}/status", "session_id") in parameters
    assert ("GET", "/api/v1/goals/{session_id}/plan", "session_id") in parameters
    assert ("GET", "/api/v1/goals/{session_id}/constraints", "session_id") in parameters
    assert ("POST", "/api/v1/goals/{session_id}/queue/reorder", "session_id") in parameters
    assert ("DELETE", "/api/v1/goals/{session_id}/queue/{goal_id}", "goal_id") in parameters
    assert ("DELETE", "/api/v1/goals/{session_id}/subgoals/{index}", "index") in parameters


@pytest.mark.parametrize("session_id", _WELL_FORMED_IDS)
def test_a_well_formed_session_id_the_router_has_never_seen_is_served(client: TestClient, session_id: str) -> None:
    status = client.get(f"/api/v1/goals/{session_id}/status")
    queue = client.get(f"/api/v1/goals/{session_id}/queue")

    assert status.status_code == 200
    assert status.json() == {"goal": None}
    assert queue.status_code == 200


def test_a_well_formed_goal_id_and_subgoal_index_reach_their_handlers(client: TestClient) -> None:
    cancel = client.delete(f"/api/v1/goals/c-1/queue/{uuid.uuid4()}")
    remove = client.delete("/api/v1/goals/c-1/subgoals/0")

    assert cancel.status_code == 404
    assert "Queued goal not found" in cancel.text
    assert remove.status_code == 404
    assert "No active goal found for this session" in remove.text


def test_a_route_without_a_path_parameter_is_not_guarded(client: TestClient) -> None:
    response = client.get("/api/v1/goals/active")

    assert response.status_code == 200
    assert isinstance(response.json()["goals"], list)
