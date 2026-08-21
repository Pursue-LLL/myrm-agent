"""Unit and integration tests for Control Plane guard and origin verification."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import Headers

from app.core.security.auth.control_plane_guard import (
    extract_provided_cp_token,
    get_expected_control_plane_token,
    verify_control_plane_token,
    verify_internal_origin,
)


def _build_mock_request(
    headers: dict[str, str] | None = None,
    client_host: str = "127.0.0.1",
    path: str = "/api/channel/message",
) -> Request:
    raw_headers = headers or {}
    req = MagicMock(spec=Request)
    req.headers = Headers(raw_headers)
    req.client = MagicMock(host=client_host)
    req.url = MagicMock(path=path)
    return req


class TestControlPlaneGuard:
    def test_extract_provided_cp_token(self) -> None:
        # 1. Direct header
        req1 = _build_mock_request({"X-Control-Plane-Token": "secret-token-1"})
        assert extract_provided_cp_token(req1) == "secret-token-1"

        # 2. Telemetry header
        req2 = _build_mock_request({"X-Telemetry-Token": "secret-token-2"})
        assert extract_provided_cp_token(req2) == "secret-token-2"

        # 3. Bearer header
        req3 = _build_mock_request({"Authorization": "Bearer secret-token-3"})
        assert extract_provided_cp_token(req3) == "secret-token-3"

        # 4. None
        req4 = _build_mock_request({})
        assert extract_provided_cp_token(req4) == ""

    def test_verify_internal_origin_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config.settings import settings

        monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000", "tauri://localhost"])

        # No origin (cli/http client) -> allowed
        req1 = _build_mock_request()
        verify_internal_origin(req1)

        # Allowed origin -> allowed
        req2 = _build_mock_request({"Origin": "http://localhost:3000"})
        verify_internal_origin(req2)

        # Disallowed origin -> 403 Forbidden
        req3 = _build_mock_request({"Origin": "http://malicious-attacker.com"})
        with pytest.raises(HTTPException) as exc_info:
            verify_internal_origin(req3)
        assert exc_info.value.status_code == 403
        assert "Origin not allowed" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_verify_control_plane_token_with_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import SecretStr

        from app.config.settings import settings

        monkeypatch.setattr(settings.control_plane, "telemetry_token", SecretStr("valid-cp-token"))
        monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000"])

        # Valid token
        req_valid = _build_mock_request({"X-Control-Plane-Token": "valid-cp-token"})
        await verify_control_plane_token(req_valid)

        # Invalid token -> 401
        req_invalid = _build_mock_request({"X-Control-Plane-Token": "wrong-token"})
        with pytest.raises(HTTPException) as exc_info:
            await verify_control_plane_token(req_invalid)
        assert exc_info.value.status_code == 401

        # Missing token -> 401
        req_missing = _build_mock_request({})
        with pytest.raises(HTTPException) as exc_info:
            await verify_control_plane_token(req_missing)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_control_plane_token_no_secret_loopback_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pydantic import SecretStr

        from app.config.settings import settings

        monkeypatch.setattr(settings.control_plane, "telemetry_token", SecretStr(""))
        monkeypatch.setattr(settings, "internal_service_key", SecretStr(""))

        # Local loopback client -> Allowed
        req_local = _build_mock_request(client_host="127.0.0.1")
        await verify_control_plane_token(req_local)

        # Non-loopback client -> 401
        req_remote = _build_mock_request(client_host="192.168.1.100")
        with pytest.raises(HTTPException) as exc_info:
            await verify_control_plane_token(req_remote)
        assert exc_info.value.status_code == 401
        assert "not local loopback" in str(exc_info.value.detail)
