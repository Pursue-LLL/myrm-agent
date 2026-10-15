"""Public-path admission rules: only the liveness/readiness probes are open; diagnostics and operator routes are not."""

from __future__ import annotations

import pytest

from app.core.security.auth.public_paths import PUBLIC_READ_ONLY_EXACT_PATHS, is_public_path
from tests.support.public_api_app import public_api_openapi

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


_HEALTH_PROBES = ("/api/v1/health", "/api/v1/health/liveness", "/api/v1/health/ready")

_HEALTH_DIAGNOSTICS = (
    "/api/v1/health/",
    "/api/v1/health/doctor",
    "/api/v1/health/info",
    "/api/v1/health/metrics",
    "/api/v1/health/pressure",
    "/api/v1/health/resources",
    "/api/v1/health/update-status",
    "/api/v1/health/browser",
    "/api/v1/health/browser/doctor",
    "/api/v1/health/memory/history",
    "/api/v1/health/memory/search",
    "/api/v1/health/database/status",
)


@pytest.mark.parametrize("method", ["GET", "HEAD", "get"])
@pytest.mark.parametrize("path", _HEALTH_PROBES)
def test_health_probes_are_public_for_read_only_methods(path: str, method: str) -> None:
    assert is_public_path(path, method)


@pytest.mark.parametrize("method", ["GET", "HEAD", *_MUTATING_METHODS])
@pytest.mark.parametrize("path", _HEALTH_DIAGNOSTICS)
def test_health_diagnostics_are_not_public(path: str, method: str) -> None:
    assert not is_public_path(path, method)


@pytest.mark.parametrize("method", _MUTATING_METHODS)
@pytest.mark.parametrize("path", (*_HEALTH_OPERATOR_ROUTES, *_HEALTH_PROBES))
def test_health_operator_routes_and_probes_are_not_public_for_mutating_methods(path: str, method: str) -> None:
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


def test_every_public_probe_path_is_a_live_get_route() -> None:
    routes = public_api_openapi().paths
    stale = sorted(path for path in PUBLIC_READ_ONLY_EXACT_PATHS if "get" not in routes.get(path, {}))
    assert not stale, f"Public probe paths with no GET route behind them; remove them from public_paths.py: {stale}"
