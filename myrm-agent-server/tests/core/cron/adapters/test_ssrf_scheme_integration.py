"""Integration test: SSRF_ALLOWED_SCHEMES includes ws/wss without breaking http/https.

Validates that the url_utils.SSRF_ALLOWED_SCHEMES expansion to include ws/wss
does not regress existing http/https validation, and that ws/wss URLs pass
scheme validation while still being subjected to full SSRF hostname/IP checks.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.guards.ssrf import (
    async_validate_url_for_ssrf,
    validate_url_for_ssrf,
)
from myrm_agent_harness.utils.url_utils import SSRF_ALLOWED_SCHEMES


class TestSSRFAllowedSchemes:
    """Verify ws/wss in SSRF_ALLOWED_SCHEMES without regression."""

    def test_schemes_include_ws_wss(self) -> None:
        assert "ws" in SSRF_ALLOWED_SCHEMES
        assert "wss" in SSRF_ALLOWED_SCHEMES

    def test_schemes_include_http_https(self) -> None:
        assert "http" in SSRF_ALLOWED_SCHEMES
        assert "https" in SSRF_ALLOWED_SCHEMES

    def test_schemes_is_frozen(self) -> None:
        assert isinstance(SSRF_ALLOWED_SCHEMES, frozenset)


class TestSSRFSchemeValidation:
    """Scheme validation rejects unknown schemes, allows http/https/ws/wss."""

    def test_http_scheme_passes_validation(self) -> None:
        result = validate_url_for_ssrf("http://example.com/path")
        assert result.safe is True

    def test_https_scheme_passes_validation(self) -> None:
        result = validate_url_for_ssrf("https://example.com/path")
        assert result.safe is True

    def test_ws_scheme_passes_validation(self) -> None:
        result = validate_url_for_ssrf("ws://example.com/ws")
        assert result.safe is True

    def test_wss_scheme_passes_validation(self) -> None:
        result = validate_url_for_ssrf("wss://example.com/ws")
        assert result.safe is True

    def test_ftp_scheme_rejected(self) -> None:
        result = validate_url_for_ssrf("ftp://example.com/file")
        assert result.safe is False

    def test_file_scheme_rejected(self) -> None:
        result = validate_url_for_ssrf("file:///etc/passwd")
        assert result.safe is False

    def test_ssh_scheme_rejected(self) -> None:
        result = validate_url_for_ssrf("ssh://example.com")
        assert result.safe is False


class TestSSRFHostnameCheckWithWSScheme:
    """ws/wss URLs still get full hostname/IP SSRF validation."""

    def test_ws_private_ip_blocked(self) -> None:
        result = validate_url_for_ssrf("ws://127.0.0.1:8080/ws")
        assert result.safe is False

    def test_wss_private_ip_blocked(self) -> None:
        result = validate_url_for_ssrf("wss://10.0.0.1:8080/ws")
        assert result.safe is False

    @pytest.mark.asyncio
    async def test_async_ws_private_ip_blocked(self) -> None:
        result = await async_validate_url_for_ssrf("ws://127.0.0.1:8080/ws")
        assert result.safe is False

    @pytest.mark.asyncio
    async def test_async_ws_public_ip_passes(self) -> None:
        result = await async_validate_url_for_ssrf("ws://example.com/ws")
        assert result.safe is True

    @pytest.mark.asyncio
    async def test_async_wss_public_ip_passes(self) -> None:
        result = await async_validate_url_for_ssrf("wss://example.com/ws")
        assert result.safe is True
