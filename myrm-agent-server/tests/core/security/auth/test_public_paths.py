"""Public-path admission rules: read-only probes are open, mutating operator routes are not."""

from __future__ import annotations

import pytest

from app.core.security.auth.public_paths import is_public_path

_MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")

_HEALTH_OPERATOR_ROUTES = (
    "/api/v1/health/database/reset",
    "/api/v1/health/database/safe-purge",
    "/api/v1/health/browser/orphans",
    "/api/v1/health/browser/test-cloud-connection",
    "/api/v1/health/browser/test-proxy-connection",
    "/api/v1/health/memory/profile/start",
    "/api/v1/health/memory/profile/stop",
    "/api/v1/health/repair-actions/cleanup_browser_orphans/execute",
)

_A2A_OPERATOR_ROUTES = (
    "/api/v1/a2a/peers",
    "/api/v1/a2a/peers/probe",
    "/api/v1/a2a/peers/peer-1",
    "/api/v1/a2a/tasks/pending-approval",
    "/api/v1/a2a/tasks/task-1/approve",
    "/api/v1/a2a/tasks/task-1/reject",
)


@pytest.mark.parametrize("method", ["GET", "HEAD", "get"])
@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/health/doctor", "/api/v1/health/database/status"])
def test_health_probes_are_public_for_read_only_methods(path: str, method: str) -> None:
    assert is_public_path(path, method)


@pytest.mark.parametrize("method", _MUTATING_METHODS)
@pytest.mark.parametrize("path", _HEALTH_OPERATOR_ROUTES)
def test_health_operator_routes_are_not_public_for_mutating_methods(path: str, method: str) -> None:
    assert not is_public_path(path, method)


@pytest.mark.parametrize("method", ["GET", *_MUTATING_METHODS])
@pytest.mark.parametrize("path", _A2A_OPERATOR_ROUTES)
def test_a2a_operator_routes_are_never_public(path: str, method: str) -> None:
    assert not is_public_path(path, method)


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/a2a/rpc", "POST"),
        ("/api/v1/a2a/agents/agent-1/rpc", "POST"),
        ("/api/v1/a2a/agents/agent-1/.well-known/agent-card.json", "GET"),
        ("/api/v1/a2a/.well-known/agent-card.json", "GET"),
        ("/.well-known/agent-card.json", "GET"),
        ("/api/v1/public/artifact-share/token-1", "POST"),
        ("/webui/auth/login", "POST"),
        ("/health", "GET"),
    ],
)
def test_self_authenticating_and_discovery_routes_stay_public(path: str, method: str) -> None:
    assert is_public_path(path, method)


def test_regular_api_routes_are_not_public() -> None:
    assert not is_public_path("/api/v1/chats", "GET")
