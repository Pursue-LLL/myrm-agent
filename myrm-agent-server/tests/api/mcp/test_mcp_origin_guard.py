"""Unit and integration tests for MCP HTTP Origin Guard and DNS-rebinding protection."""

from __future__ import annotations

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.mcp.origin_guard import (
    _MCPOriginGuardMiddleware,
    check_request_origin,
    host_header_hostname,
    is_loopback_hostname,
    normalize_origin,
    origin_hostname,
    resolve_origin_guard,
)


class TestIsLoopbackHostname:
    """Tests for is_loopback_hostname predicate."""

    def test_standard_localhost_names(self) -> None:
        assert is_loopback_hostname("localhost") is True
        assert is_loopback_hostname("LOCALHOST") is True
        assert is_loopback_hostname("sub.localhost") is True
        assert is_loopback_hostname("deep.nested.sub.localhost") is True

    def test_ipv4_loopback_range(self) -> None:
        assert is_loopback_hostname("127.0.0.1") is True
        assert is_loopback_hostname("127.0.0.2") is True
        assert is_loopback_hostname("127.1.2.3") is True
        assert is_loopback_hostname("127.255.255.254") is True

    def test_ipv6_loopback(self) -> None:
        assert is_loopback_hostname("::1") is True
        assert is_loopback_hostname("[::1]") is True
        assert is_loopback_hostname("0:0:0:0:0:0:0:1") is True
        assert is_loopback_hostname("0000:0000:0000:0000:0000:0000:0000:0001") is True
        assert is_loopback_hostname("::ffff:127.0.0.1") is True
        assert is_loopback_hostname("::ffff:127.10.20.30") is True

    def test_explicitly_excluded_addresses(self) -> None:
        # 0.0.0.0 is routed to loopback by Chromium on Linux/macOS and must be rejected
        assert is_loopback_hostname("0.0.0.0") is False
        assert is_loopback_hostname("::") is False

    def test_external_and_attacker_domains(self) -> None:
        assert is_loopback_hostname("attacker.example") is False
        assert is_loopback_hostname("evil.com") is False
        # False localhost subdomain suffixes must be rejected
        assert is_loopback_hostname("attacker.localhost.evil.com") is False
        assert is_loopback_hostname("localhost.evil.com") is False
        assert is_loopback_hostname("192.168.1.1") is False
        assert is_loopback_hostname("10.0.0.1") is False


class TestNormalizeAndOriginHostname:
    """Tests for normalize_origin and origin_hostname."""

    def test_http_https_normalization(self) -> None:
        assert normalize_origin("http://localhost:3000") == "http://localhost:3000"
        assert normalize_origin("HTTPS://EXAMPLE.COM:8080/path") == "https://example.com:8080"
        assert origin_hostname("http://localhost:3000") == "localhost"
        assert origin_hostname("https://sub.domain.org:9000") == "sub.domain.org"

    def test_tauri_and_webview_schemes(self) -> None:
        # Crucial for myrm-agent-desktop support
        assert normalize_origin("tauri://localhost") == "tauri://localhost"
        assert origin_hostname("tauri://localhost") == "localhost"
        assert normalize_origin("vscode-webview://webview-panel") == "vscode-webview://webview-panel"
        assert origin_hostname("vscode-webview://webview-panel") == "webview-panel"

    def test_invalid_origins(self) -> None:
        assert normalize_origin("") is None
        assert normalize_origin("not-a-url") is None
        assert normalize_origin("ftp://fileserver") is None
        assert origin_hostname("javascript:void(0)") is None


class TestHostHeaderHostname:
    """Tests for host_header_hostname parsing."""

    def test_host_without_port(self) -> None:
        assert host_header_hostname("localhost") == "localhost"
        assert host_header_hostname("example.com") == "example.com"

    def test_host_with_port(self) -> None:
        assert host_header_hostname("localhost:8080") == "localhost"
        assert host_header_hostname("127.0.0.1:3000") == "127.0.0.1"

    def test_ipv6_host_header(self) -> None:
        assert host_header_hostname("[::1]:8080") == "::1"
        assert host_header_hostname("[::1]") == "::1"


class TestCheckRequestOrigin:
    """Tests for check_request_origin core policy evaluation."""

    def test_non_browser_client_no_origin_allowed(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        # CLI / Cursor / Claude Code / Python SDK emit no Origin header
        verdict = check_request_origin({"host": "127.0.0.1:8080"}, guard)
        assert verdict.ok is True

    def test_loopback_origin_allowed(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin(
            {"origin": "http://localhost:3000", "host": "127.0.0.1:8080"},
            guard,
        )
        assert verdict.ok is True

    def test_tauri_desktop_origin_allowed(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin(
            {"origin": "tauri://localhost", "host": "127.0.0.1:8080"},
            guard,
        )
        assert verdict.ok is True

    def test_external_origin_blocked(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin(
            {"origin": "http://attacker.example", "host": "127.0.0.1:8080"},
            guard,
        )
        assert verdict.ok is False
        assert "Origin not allowed" in verdict.reason

    def test_allowlist_origin_allowed(self) -> None:
        guard = resolve_origin_guard(
            host="127.0.0.1",
            allowed_origins=["https://myrm-app.corp.internal:443"],
        )
        verdict = check_request_origin(
            {"origin": "https://myrm-app.corp.internal:443", "host": "127.0.0.1:8080"},
            guard,
        )
        assert verdict.ok is True

    def test_dns_rebinding_host_header_blocked(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        # Attacker's domain resolving to 127.0.0.1 sending Host: attacker.example:8080
        verdict = check_request_origin(
            {"origin": "http://attacker.example", "host": "attacker.example:8080"},
            guard,
        )
        assert verdict.ok is False

    def test_disabled_guard_allows_all(self) -> None:
        guard = resolve_origin_guard(allowed_origins=["*"])
        assert guard.disabled is True
        verdict = check_request_origin(
            {"origin": "http://attacker.example", "host": "attacker.example:8080"},
            guard,
        )
        assert verdict.ok is True


class TestMCPOriginGuardMiddlewareIntegration:
    """Integration tests executing through ASGI stack."""

    @pytest.fixture
    def dummy_app(self) -> ASGIApp:
        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                response = JSONResponse({"status": "ok"})
                await response(scope, receive, send)

        return app

    def test_middleware_allows_legitimate_cli_request(self, dummy_app: ASGIApp) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        middleware = _MCPOriginGuardMiddleware(dummy_app, guard=guard)
        client = TestClient(middleware)

        response = client.get("/", headers={"host": "127.0.0.1"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_middleware_allows_tauri_desktop_request(self, dummy_app: ASGIApp) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        middleware = _MCPOriginGuardMiddleware(dummy_app, guard=guard)
        client = TestClient(middleware)

        response = client.get("/", headers={"origin": "tauri://localhost", "host": "127.0.0.1"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_middleware_blocks_malicious_origin_with_403(self, dummy_app: ASGIApp) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        middleware = _MCPOriginGuardMiddleware(dummy_app, guard=guard)
        client = TestClient(middleware)

        response = client.get("/", headers={"origin": "http://evil-attacker.com", "host": "127.0.0.1"})
        assert response.status_code == 403
        data = response.json()
        assert "Forbidden" in data["error"]
        assert "Origin not allowed" in data["error"]
