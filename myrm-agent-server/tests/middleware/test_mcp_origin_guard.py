"""Unit and integration tests for MCP HTTP Origin & DNS-rebinding guard.

Validates pure predicates (is_loopback_hostname, resolve_origin_guard, check_request_origin)
and ASGI middleware behavior under various attack models, legitimate client scenarios,
and Tauri/Webview desktop environments.
"""

from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.api.mcp.origin_guard import (
    OriginGuard,
    _MCPOriginGuardMiddleware,
    check_request_origin,
    host_header_hostname,
    is_loopback_hostname,
    normalize_origin,
    origin_hostname,
    resolve_origin_guard,
)


class TestLoopbackHostnamePredicate:
    """Test pure loopback hostname classification."""

    @pytest.mark.parametrize(
        "hostname",
        [
            "localhost",
            "LocalHost",
            "sub.localhost",
            "deep.nested.localhost",
            "127.0.0.1",
            "127.0.0.2",
            "127.12.34.56",
            "127.255.255.254",
            "::1",
            "[::1]",
            "0:0:0:0:0:0:0:1",
            "0000:0000:0000:0000:0000:0000:0000:0001",
            "::ffff:127.0.0.1",
            "::ffff:127.100.200.1",
        ],
    )
    def test_valid_loopback_hostnames(self, hostname: str):
        assert is_loopback_hostname(hostname) is True

    @pytest.mark.parametrize(
        "hostname",
        [
            "0.0.0.0",  # Deliberately untrusted (Chromium loopback route hazard)
            "::",
            "192.168.1.1",
            "10.0.0.1",
            "172.16.0.1",
            "attacker.com",
            "evil-localhost.com",
            "localhost.attacker.com",
            "attacker.localhost.evil.com",
            "::ffff:192.168.1.1",
            "",
            "   ",
            "128.0.0.1",
        ],
    )
    def test_non_loopback_hostnames(self, hostname: str):
        assert is_loopback_hostname(hostname) is False


class TestOriginAndHostParsers:
    """Test normalization and parsing functions for Origin and Host."""

    def test_normalize_origin(self):
        assert normalize_origin("http://localhost:3000") == "http://localhost:3000"
        assert normalize_origin("HTTPS://EXAMPLE.COM:8443") == "https://example.com:8443"
        assert normalize_origin("http://127.0.0.1:8080/") == "http://127.0.0.1:8080"
        assert normalize_origin("file:///etc/passwd") is None
        assert normalize_origin("javascript:void(0)") is None
        assert normalize_origin("") is None

    def test_tauri_and_webview_schemes(self):
        # Crucial for myrm-agent-desktop Tauri and editor webview support
        assert normalize_origin("tauri://localhost") == "tauri://localhost"
        assert origin_hostname("tauri://localhost") == "localhost"
        assert normalize_origin("vscode-webview://webview-panel") == "vscode-webview://webview-panel"
        assert origin_hostname("vscode-webview://webview-panel") == "webview-panel"

    def test_origin_hostname(self):
        assert origin_hostname("http://localhost:3000") == "localhost"
        assert origin_hostname("https://127.0.0.1:8080") == "127.0.0.1"
        assert origin_hostname("http://[::1]:8080") == "::1"
        assert origin_hostname("invalid_url") is None

    def test_host_header_hostname(self):
        assert host_header_hostname("localhost:8080") == "localhost"
        assert host_header_hostname("127.0.0.1:8000") == "127.0.0.1"
        assert host_header_hostname("[::1]:8080") == "::1"
        assert host_header_hostname("attacker.com:8080") == "attacker.com"
        assert host_header_hostname("myrm.local") == "myrm.local"
        assert host_header_hostname("") is None


class TestResolveOriginGuard:
    """Test guard configuration resolution."""

    def test_default_guard_for_loopback(self):
        guard = resolve_origin_guard(host="127.0.0.1")
        assert guard.disabled is False
        assert guard.enforce_host is True

    def test_wildcard_bind_without_explicit_hosts(self):
        guard = resolve_origin_guard(host="0.0.0.0")
        assert guard.disabled is False
        assert guard.enforce_host is False

    def test_wildcard_bind_with_explicit_hosts(self):
        guard = resolve_origin_guard(host="0.0.0.0", allowed_hosts=["myrm.internal"])
        assert guard.disabled is False
        assert guard.enforce_host is True
        assert "myrm.internal" in guard.allowed_hosts

    def test_disabled_by_wildcard_origin(self):
        guard = resolve_origin_guard(host="127.0.0.1", allowed_origins=["*"])
        assert guard.disabled is True
        assert guard.enforce_host is False

    def test_explicit_env_configuration(self, monkeypatch):
        monkeypatch.setenv("MYRM_MCP_ALLOWED_ORIGINS", "https://app.myrm.ai,http://test.local:3000")
        monkeypatch.setenv("MYRM_MCP_ALLOWED_HOSTS", "internal-mcp.company.org")
        guard = resolve_origin_guard(host="127.0.0.1")
        assert "https://app.myrm.ai" in guard.allowed_origins
        assert "http://test.local:3000" in guard.allowed_origins
        assert "internal-mcp.company.org" in guard.allowed_hosts


class TestCheckRequestOrigin:
    """Test request header evaluation against security policy."""

    def test_missing_origin_allowed(self):
        # Native IDE clients / CLI / curl omit Origin
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin({"host": "127.0.0.1:8080"}, guard)
        assert verdict.ok is True

    def test_legitimate_loopback_origins_allowed(self):
        guard = resolve_origin_guard(host="127.0.0.1")
        for origin in [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://[::1]:3000",
            "http://dev.localhost:3000",
            "tauri://localhost",
        ]:
            verdict = check_request_origin(
                {"origin": origin, "host": "127.0.0.1:8080"},
                guard,
            )
            assert verdict.ok is True

    def test_malicious_origins_blocked(self):
        guard = resolve_origin_guard(host="127.0.0.1")
        for bad_origin in [
            "http://attacker.com",
            "http://evil.org:8080",
            "http://0.0.0.0:8080",
            "http://localhost.attacker.com",
        ]:
            verdict = check_request_origin(
                {"origin": bad_origin, "host": "127.0.0.1:8080"},
                guard,
            )
            assert verdict.ok is False
            assert "Origin not allowed" in verdict.reason

    def test_dns_rebinding_host_header_blocked(self):
        # Even if origin is missing or manipulated, DNS rebinding gives attacker host
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin(
            {"host": "attacker.com:8080"},
            guard,
        )
        assert verdict.ok is False
        assert "Host not allowed" in verdict.reason

    def test_explicit_allowlist_permits_configured_domain(self):
        guard = resolve_origin_guard(
            host="127.0.0.1",
            allowed_origins=["https://cloud.myrm.ai"],
            allowed_hosts=["cloud.myrm.ai"],
        )
        verdict = check_request_origin(
            {"origin": "https://cloud.myrm.ai", "host": "cloud.myrm.ai"},
            guard,
        )
        assert verdict.ok is True


def _echo_endpoint(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


class TestMCPOriginGuardMiddleware:
    """ASGI integration test for _MCPOriginGuardMiddleware."""

    def _create_app(self, guard: OriginGuard | None = None) -> TestClient:
        inner = Starlette(routes=[Route("/mcp", _echo_endpoint, methods=["GET", "POST"])])
        app = _MCPOriginGuardMiddleware(inner, guard=guard)
        return TestClient(app, raise_server_exceptions=False)

    def test_request_without_origin_passes(self):
        tc = self._create_app()
        resp = tc.get("/mcp", headers={"host": "127.0.0.1:8080"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_request_with_valid_loopback_origin_passes(self):
        tc = self._create_app()
        resp = tc.get(
            "/mcp",
            headers={"origin": "http://localhost:3000", "host": "127.0.0.1:8080"},
        )
        assert resp.status_code == 200

    def test_request_with_tauri_desktop_origin_passes(self):
        tc = self._create_app()
        resp = tc.get(
            "/mcp",
            headers={"origin": "tauri://localhost", "host": "127.0.0.1:8080"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_request_with_malicious_origin_rejected_403(self):
        tc = self._create_app()
        resp = tc.get(
            "/mcp",
            headers={"origin": "http://malicious-site.com", "host": "127.0.0.1:8080"},
        )
        assert resp.status_code == 403
        assert "Origin not allowed" in resp.json()["error"]

    def test_request_with_rebound_host_rejected_403(self):
        tc = self._create_app()
        resp = tc.get(
            "/mcp",
            headers={"host": "malicious-site.com:8080"},
        )
        assert resp.status_code == 403
        assert "Host not allowed" in resp.json()["error"]

    @pytest.mark.asyncio
    async def test_non_http_scope_bypasses_guard(self):
        inner = AsyncMock()
        middleware = _MCPOriginGuardMiddleware(inner)
        scope = {"type": "websocket"}
        receive = AsyncMock()
        send = AsyncMock()
        await middleware(scope, receive, send)
        inner.assert_awaited_once_with(scope, receive, send)
