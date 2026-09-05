"""Unit tests for MCP HTTP Origin and DNS-rebinding guard.

Validates pure predicates (is_loopback_hostname, resolve_origin_guard, check_request_origin)
and ASGI middleware behavior under diverse RFC and browser scenarios.
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


class TestIsLoopbackHostname:
    """Validate loopback hostname determination according to MCP specifications."""

    def test_standard_localhost(self) -> None:
        assert is_loopback_hostname("localhost") is True
        assert is_loopback_hostname("LOCALHOST") is True
        assert is_loopback_hostname("  localhost  ") is True

    def test_subdomain_localhost(self) -> None:
        assert is_loopback_hostname("sub.localhost") is True
        assert is_loopback_hostname("deep.nested.sub.localhost") is True

    def test_ipv4_loopback_range(self) -> None:
        assert is_loopback_hostname("127.0.0.1") is True
        assert is_loopback_hostname("127.0.1.1") is True
        assert is_loopback_hostname("127.255.255.254") is True
        assert is_loopback_hostname("127.12.34.56") is True

    def test_ipv6_loopback(self) -> None:
        assert is_loopback_hostname("::1") is True
        assert is_loopback_hostname("[::1]") is True
        assert is_loopback_hostname("0:0:0:0:0:0:0:1") is True

    def test_ipv4_mapped_ipv6(self) -> None:
        assert is_loopback_hostname("::ffff:127.0.0.1") is True
        assert is_loopback_hostname("[::ffff:127.0.0.1]") is True
        assert is_loopback_hostname("::ffff:127.1.2.3") is True

    def test_zero_zero_zero_zero_excluded(self) -> None:
        """0.0.0.0 is deliberately excluded because browsers route it to loopback."""
        assert is_loopback_hostname("0.0.0.0") is False

    def test_external_and_private_hostnames_rejected(self) -> None:
        assert is_loopback_hostname("attacker.com") is False
        assert is_loopback_hostname("evil.attacker.com") is False
        assert is_loopback_hostname("192.168.1.1") is False
        assert is_loopback_hostname("10.0.0.1") is False
        assert is_loopback_hostname("128.0.0.1") is False
        assert is_loopback_hostname("") is False


class TestOriginParsingAndNormalization:
    """Validate Origin URL parsing and normalization."""

    def test_normalize_valid_origins(self) -> None:
        assert normalize_origin("http://localhost:3000") == "http://localhost:3000"
        assert normalize_origin("HTTP://LOCALHOST:3000/") == "http://localhost:3000"
        assert normalize_origin("https://example.com:8443/some/path") == "https://example.com:8443"

    def test_normalize_invalid_origins(self) -> None:
        assert normalize_origin("") is None
        assert normalize_origin("ftp://example.com") is None
        assert normalize_origin("javascript:alert(1)") is None
        assert normalize_origin("null") is None

    def test_origin_hostname_extraction(self) -> None:
        assert origin_hostname("http://localhost:3000") == "localhost"
        assert origin_hostname("http://127.0.0.1:8080") == "127.0.0.1"
        assert origin_hostname("https://attacker.example/path") == "attacker.example"
        assert origin_hostname("not-a-url") is None

    def test_host_header_hostname_extraction(self) -> None:
        assert host_header_hostname("localhost") == "localhost"
        assert host_header_hostname("localhost:8080") == "localhost"
        assert host_header_hostname("127.0.0.1:8080") == "127.0.0.1"
        assert host_header_hostname("[::1]:8080") == "::1"
        assert host_header_hostname("attacker.com:8080") == "attacker.com"
        assert host_header_hostname("") is None


class TestResolveOriginGuard:
    """Validate OriginGuard policy construction."""

    def test_default_loopback_bind(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        assert guard.disabled is False
        assert guard.enforce_host is True

    def test_wildcard_bind_disables_host_enforcement_without_allowlist(self) -> None:
        guard = resolve_origin_guard(host="0.0.0.0")
        assert guard.disabled is False
        assert guard.enforce_host is False

    def test_wildcard_bind_enforces_host_when_allowlist_provided(self) -> None:
        guard = resolve_origin_guard(
            host="0.0.0.0",
            allowed_hosts=["my-mcp.internal"],
        )
        assert guard.enforce_host is True
        assert "my-mcp.internal" in guard.allowed_hosts

    def test_concrete_interface_bind_adds_self_to_allowed_hosts(self) -> None:
        guard = resolve_origin_guard(host="192.168.1.100")
        assert guard.enforce_host is True
        assert "192.168.1.100" in guard.allowed_hosts

    def test_wildcard_origin_disables_guard(self) -> None:
        guard = resolve_origin_guard(allowed_origins=["*"])
        assert guard.disabled is True
        assert guard.enforce_host is False


class TestCheckRequestOrigin:
    """Validate pure request validation decisions."""

    def test_missing_origin_allowed_for_non_browser_clients(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin({"host": "127.0.0.1:8080"}, guard)
        assert verdict.ok is True

    def test_loopback_origin_allowed(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin(
            {"origin": "http://localhost:3000", "host": "localhost:8080"},
            guard,
        )
        assert verdict.ok is True

    def test_external_origin_rejected(self) -> None:
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin(
            {"origin": "http://attacker.com", "host": "127.0.0.1:8080"},
            guard,
        )
        assert verdict.ok is False
        assert "Origin not allowed" in verdict.reason

    def test_dns_rebinding_host_rejected(self) -> None:
        """When an attacker rebinds their domain to 127.0.0.1, the Host header is their domain."""
        guard = resolve_origin_guard(host="127.0.0.1")
        verdict = check_request_origin(
            {"host": "attacker.com:8080"},
            guard,
        )
        assert verdict.ok is False
        assert "Host not allowed" in verdict.reason

    def test_explicit_allowed_origin_and_host(self) -> None:
        guard = resolve_origin_guard(
            host="127.0.0.1",
            allowed_origins=["https://dashboard.example.com"],
            allowed_hosts=["dashboard.example.com:8080"],
        )
        verdict = check_request_origin(
            {
                "origin": "https://dashboard.example.com",
                "host": "dashboard.example.com:8080",
            },
            guard,
        )
        assert verdict.ok is True

    def test_disabled_guard_allows_all(self) -> None:
        guard = OriginGuard(
            disabled=True,
            allowed_origins=frozenset(),
            allowed_hosts=frozenset(),
            enforce_host=False,
        )
        verdict = check_request_origin(
            {"origin": "http://evil.com", "host": "evil.com:8080"},
            guard,
        )
        assert verdict.ok is True


class TestMCPOriginGuardMiddleware:
    """Test Starlette ASGI middleware integration."""

    def _build_client(self, guard: OriginGuard | None = None) -> TestClient:
        def _echo(request: Request) -> JSONResponse:
            return JSONResponse({"status": "ok"})

        inner_app = Starlette(routes=[Route("/mcp", _echo, methods=["GET", "POST"])])
        middleware = _MCPOriginGuardMiddleware(inner_app, guard=guard)
        return TestClient(middleware, raise_server_exceptions=False)

    def test_middleware_allows_native_tool_without_origin(self) -> None:
        tc = self._build_client()
        response = tc.get("/mcp", headers={"Host": "127.0.0.1:8080"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_middleware_blocks_foreign_browser_origin(self) -> None:
        tc = self._build_client()
        response = tc.get(
            "/mcp",
            headers={
                "Origin": "http://attacker.evil",
                "Host": "127.0.0.1:8080",
            },
        )
        assert response.status_code == 403
        assert "Forbidden" in response.json()["error"]
        assert "Origin not allowed" in response.json()["error"]

    def test_middleware_blocks_dns_rebinding_host(self) -> None:
        tc = self._build_client()
        response = tc.get(
            "/mcp",
            headers={
                "Host": "attacker.evil:8080",
            },
        )
        assert response.status_code == 403
        assert "Forbidden" in response.json()["error"]
        assert "Host not allowed" in response.json()["error"]

    def test_middleware_allows_loopback_webui_origin(self) -> None:
        tc = self._build_client()
        response = tc.get(
            "/mcp",
            headers={
                "Origin": "http://localhost:3000",
                "Host": "127.0.0.1:8080",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_non_http_scope_passed_through(self) -> None:
        inner = AsyncMock()
        middleware = _MCPOriginGuardMiddleware(inner)
        scope = {"type": "lifespan"}
        receive = AsyncMock()
        send = AsyncMock()
        await middleware(scope, receive, send)
        inner.assert_called_once_with(scope, receive, send)
