"""Tests for IP utility functions.

Tests cover:
- extract_real_ip() with trusted proxies
- is_ip_blocked() CIDR matching
- is_ip_allowed() CIDR matching
- validate_host() Host header validation
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.channels.security.ip_utils import (
    extract_real_ip,
    is_ip_allowed,
    is_ip_blocked,
    validate_host,
)


class TestExtractRealIP:
    """Test real IP extraction from X-Forwarded-For."""

    def test_direct_connection_no_proxy(self) -> None:
        """Direct connection should use request.client.host."""
        request = MagicMock()
        request.client.host = "203.0.113.45"
        request.headers = {}

        real_ip = extract_real_ip(request, trusted_proxies=None)
        assert real_ip == "203.0.113.45"

    def test_untrusted_proxy_ignores_xff(self) -> None:
        """Untrusted proxy should ignore X-Forwarded-For."""
        request = MagicMock()
        request.client.host = "192.168.1.100"  # Untrusted proxy
        request.headers = {"x-forwarded-for": "1.2.3.4"}

        real_ip = extract_real_ip(
            request,
            trusted_proxies=["10.0.0.0/8"],  # Different network
        )
        # Should return proxy IP, not XFF value
        assert real_ip == "192.168.1.100"

    def test_trusted_proxy_extracts_leftmost_ip(self) -> None:
        """Trusted proxy should extract leftmost IP from X-Forwarded-For."""
        request = MagicMock()
        request.client.host = "10.0.0.1"  # Trusted proxy
        request.headers = {"X-Forwarded-For": "203.0.113.45, 192.168.1.1"}

        real_ip = extract_real_ip(
            request,
            trusted_proxies=["10.0.0.0/8"],
        )
        assert real_ip == "203.0.113.45"

    def test_multiple_proxies_in_xff(self) -> None:
        """Multiple proxies should extract first client IP."""
        request = MagicMock()
        request.client.host = "10.0.0.5"
        request.headers = {"X-Forwarded-For": "203.0.113.45, 192.168.1.1, 10.0.0.2"}

        real_ip = extract_real_ip(
            request,
            trusted_proxies=["10.0.0.0/8"],
        )
        assert real_ip == "203.0.113.45"

    def test_single_ip_in_xff(self) -> None:
        """Single IP in X-Forwarded-For should be returned."""
        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "203.0.113.45"}

        real_ip = extract_real_ip(
            request,
            trusted_proxies=["10.0.0.0/8"],
        )
        assert real_ip == "203.0.113.45"

    def test_empty_xff_returns_client_host(self) -> None:
        """Empty X-Forwarded-For should return client host."""
        request = MagicMock()
        request.client.host = "10.0.0.1"
        request.headers = {"x-forwarded-for": ""}

        real_ip = extract_real_ip(
            request,
            trusted_proxies=["10.0.0.0/8"],
        )
        assert real_ip == "10.0.0.1"


class TestIsIPBlocked:
    """Test IP blacklist checking."""

    def test_exact_match_blocked(self) -> None:
        """Exact IP match should be blocked."""
        assert is_ip_blocked("1.2.3.4", ["1.2.3.4", "5.6.7.8"])

    def test_cidr_match_blocked(self) -> None:
        """IP in CIDR block should be blocked."""
        assert is_ip_blocked("10.0.0.50", ["10.0.0.0/24"])

    def test_not_in_blocklist(self) -> None:
        """IP not in blocklist should not be blocked."""
        assert not is_ip_blocked("203.0.113.45", ["1.2.3.4", "10.0.0.0/8"])

    def test_empty_blocklist(self) -> None:
        """Empty blocklist should not block anything."""
        assert not is_ip_blocked("1.2.3.4", [])

    def test_ipv6_blocked(self) -> None:
        """IPv6 addresses should be supported."""
        assert is_ip_blocked("2001:db8::1", ["2001:db8::/32"])

    def test_multiple_cidr_blocks(self) -> None:
        """Multiple CIDR blocks should all be checked."""
        blocklist = ["10.0.0.0/8", "192.168.0.0/16", "172.16.0.0/12"]
        assert is_ip_blocked("10.5.10.50", blocklist)
        assert is_ip_blocked("192.168.1.1", blocklist)
        assert is_ip_blocked("172.16.5.5", blocklist)
        assert not is_ip_blocked("203.0.113.1", blocklist)


class TestIsIPAllowed:
    """Test IP whitelist checking."""

    def test_exact_match_allowed(self) -> None:
        """Exact IP match should be allowed."""
        assert is_ip_allowed("1.2.3.4", ["1.2.3.4", "5.6.7.8"])

    def test_cidr_match_allowed(self) -> None:
        """IP in CIDR block should be allowed."""
        assert is_ip_allowed("192.168.1.100", ["192.168.1.0/24"])

    def test_not_in_allowlist(self) -> None:
        """IP not in allowlist should not be allowed."""
        assert not is_ip_allowed("203.0.113.45", ["192.168.1.0/24"])

    def test_empty_allowlist(self) -> None:
        """Empty allowlist should not allow anything."""
        assert not is_ip_allowed("1.2.3.4", [])

    def test_ipv6_allowed(self) -> None:
        """IPv6 addresses should be supported."""
        assert is_ip_allowed("::1", ["::1"])

    def test_large_cidr_block(self) -> None:
        """Large CIDR blocks should work correctly."""
        assert is_ip_allowed("10.50.100.200", ["10.0.0.0/8"])


class TestValidateHost:
    """Test Host header validation."""

    def test_valid_host_passes(self) -> None:
        """Valid host should pass validation."""
        request = MagicMock()
        request.headers = {"Host": "api.example.com"}

        assert validate_host(request, ["api.example.com"])

    def test_invalid_host_fails(self) -> None:
        """Invalid host should fail validation."""
        request = MagicMock()
        request.headers = {"Host": "evil.com"}

        assert not validate_host(request, ["api.example.com"])

    def test_multiple_allowed_hosts(self) -> None:
        """Multiple allowed hosts should all be checked."""
        request = MagicMock()
        request.headers = {"Host": "api2.example.com"}

        assert validate_host(
            request,
            ["api1.example.com", "api2.example.com", "api3.example.com"],
        )

    def test_missing_host_header_fails(self) -> None:
        """Missing Host header should fail validation."""
        request = MagicMock()
        request.headers = {}

        assert not validate_host(request, ["api.example.com"])

    def test_host_with_port(self) -> None:
        """Host with port should match allowed host."""
        request = MagicMock()
        request.headers = {"Host": "api.example.com:8080"}

        # Should match base host
        assert validate_host(request, ["api.example.com"])

    def test_empty_allowed_hosts(self) -> None:
        """Empty allowed hosts list should reject all."""
        request = MagicMock()
        request.headers = {"Host": "api.example.com"}

        assert not validate_host(request, [])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
