"""Unit tests for HostAllowlistMiddleware local DNS rebinding and cross-origin defense."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.host_allowlist import HostAllowlistMiddleware


async def _dummy_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _build_test_app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/api/v1/test", _dummy_endpoint, methods=["GET", "POST", "OPTIONS"]),
        ]
    )
    app.add_middleware(HostAllowlistMiddleware)
    return app


def test_host_allowlist_permits_loopback_hosts() -> None:
    client = TestClient(_build_test_app())
    for host in ("localhost:8080", "127.0.0.1:8080", "127.0.0.5:8080", "[::1]:8080", "[::1]", "::1"):
        resp = client.get("/api/v1/test", headers={"Host": host})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_host_allowlist_blocks_external_host_dns_rebinding() -> None:
    client = TestClient(_build_test_app())
    # Attacker website mapped to 127.0.0.1 via DNS rebinding
    resp = client.get("/api/v1/test", headers={"Host": "attacker.example:8080"})
    assert resp.status_code == 403
    assert "DNS rebinding" in resp.json().get("detail", "")


def test_host_allowlist_permits_safe_local_origins() -> None:
    client = TestClient(_build_test_app())
    # Normal WebUI and desktop webview origins
    safe_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://[::1]:3000",
        "tauri://localhost",
        "vscode-webview://desktop",
    ]
    for origin in safe_origins:
        resp = client.post(
            "/api/v1/test",
            headers={"Host": "127.0.0.1:8080", "Origin": origin},
        )
        assert resp.status_code == 200


def test_host_allowlist_blocks_malicious_cross_origin() -> None:
    client = TestClient(_build_test_app())
    # Foreign browser origin attempting to hijack local endpoint
    resp = client.post(
        "/api/v1/test",
        headers={"Host": "127.0.0.1:8080", "Origin": "http://evil-tracker.com"},
    )
    assert resp.status_code == 403
    assert "Origin not allowed" in resp.json().get("detail", "")


def test_host_allowlist_skips_options_preflight() -> None:
    client = TestClient(_build_test_app())
    resp = client.options("/api/v1/test", headers={"Host": "attacker.example"})
    assert resp.status_code == 200


def test_host_allowlist_skips_public_path() -> None:
    app = Starlette(
        routes=[
            Route("/api/v1/health", _dummy_endpoint, methods=["GET"]),
        ]
    )
    app.add_middleware(HostAllowlistMiddleware)
    client = TestClient(app)
    # Public path /api/v1/health must bypass Host checking for monitoring probes
    resp = client.get("/api/v1/health", headers={"Host": "healthcheck.monitoring.internal"})
    assert resp.status_code == 200


def test_host_allowlist_missing_host() -> None:
    client = TestClient(_build_test_app())
    resp = client.get("/api/v1/test", headers={"Host": ""})
    assert resp.status_code == 400
    assert "Missing Host" in resp.json().get("detail", "")


def test_host_allowlist_mixed_case_safe_origin() -> None:
    client = TestClient(_build_test_app())
    resp = client.post(
        "/api/v1/test",
        headers={"Host": "LOCALHOST:8080", "Origin": "HTTP://Localhost:3000"},
    )
    assert resp.status_code == 200
