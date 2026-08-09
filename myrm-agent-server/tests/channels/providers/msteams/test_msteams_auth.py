"""BotFrameworkJwtVerifier tests — JWT verification, JWKS caching."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.providers.msteams.auth import (
    BotFrameworkJwtVerifier,
)


def _make_verifier(app_id: str = "test-app-id") -> BotFrameworkJwtVerifier:
    http = MagicMock()
    http.get = AsyncMock()
    return BotFrameworkJwtVerifier(app_id=app_id, http=http)


class TestVerifyBasic:
    @pytest.mark.asyncio
    async def test_no_app_id_skips(self) -> None:
        v = _make_verifier(app_id="")
        result = await v.verify("Bearer token", {})
        assert result is True

    @pytest.mark.asyncio
    async def test_missing_auth_header(self) -> None:
        v = _make_verifier()
        assert await v.verify("", {}) is False
        assert await v.verify("Basic token", {}) is False

    @pytest.mark.asyncio
    async def test_pyjwt_not_installed(self) -> None:
        v = _make_verifier()
        with patch.dict("sys.modules", {"jwt": None}):
            result = await v.verify("Bearer some-token", {})
            assert isinstance(result, bool)


class TestGetJwksUrl:
    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        v = _make_verifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"jwks_uri": "https://login.botframework.com/v1/.well-known/keys"}
        v._http.get = AsyncMock(return_value=mock_resp)

        url = await v._get_jwks_url()
        assert url == "https://login.botframework.com/v1/.well-known/keys"

    @pytest.mark.asyncio
    async def test_fetch_cached(self) -> None:
        v = _make_verifier()
        v._jwks_url_cache = "https://cached.url/keys"
        v._jwks_fetched_at = time.monotonic()

        url = await v._get_jwks_url()
        assert url == "https://cached.url/keys"
        v._http.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_http_error(self) -> None:
        v = _make_verifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        v._http.get = AsyncMock(return_value=mock_resp)

        url = await v._get_jwks_url()
        assert url == ""

    @pytest.mark.asyncio
    async def test_fetch_exception(self) -> None:
        v = _make_verifier()
        v._http.get = AsyncMock(side_effect=Exception("network"))

        url = await v._get_jwks_url()
        assert url == ""

    @pytest.mark.asyncio
    async def test_cache_expired(self) -> None:
        v = _make_verifier()
        v._jwks_url_cache = "https://old.url/keys"
        v._jwks_fetched_at = time.monotonic() - 100000

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"jwks_uri": "https://new.url/keys"}
        v._http.get = AsyncMock(return_value=mock_resp)

        url = await v._get_jwks_url()
        assert url == "https://new.url/keys"

    @pytest.mark.asyncio
    async def test_no_jwks_uri_in_metadata(self) -> None:
        v = _make_verifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        v._http.get = AsyncMock(return_value=mock_resp)

        url = await v._get_jwks_url()
        assert url == ""


class TestVerifyWithJwksFailure:
    @pytest.mark.asyncio
    async def test_jwks_url_empty(self) -> None:
        v = _make_verifier()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        v._http.get = AsyncMock(return_value=mock_resp)

        result = await v.verify("Bearer some-token", {})
        assert result is False


class TestVerifyJwtDecoding:
    """Tests for JWT token decoding and validation paths."""

    def _setup_verifier_with_cached_jwks(self) -> BotFrameworkJwtVerifier:
        v = _make_verifier()
        v._jwks_url_cache = "https://login.botframework.com/keys"
        v._jwks_fetched_at = time.monotonic()
        return v

    def _make_jwt_mocks(self) -> tuple[MagicMock, MagicMock]:
        mock_signing_key = MagicMock()
        mock_signing_key.key = "test-key"
        mock_jwk_client_cls = MagicMock()
        mock_jwk_client_cls.return_value.get_signing_key_from_jwt.return_value = mock_signing_key
        return mock_signing_key, mock_jwk_client_cls

    @pytest.mark.asyncio
    async def test_valid_token_accepted(self) -> None:
        v = self._setup_verifier_with_cached_jwks()
        _, mock_jwk_cls = self._make_jwt_mocks()

        mock_jwt_mod = MagicMock()
        mock_jwt_mod.PyJWKClient = mock_jwk_cls
        mock_jwt_mod.decode.return_value = {
            "iss": "https://api.botframework.com",
            "aud": "test-app-id",
        }

        with patch.dict("sys.modules", {"jwt": mock_jwt_mod}):
            result = await v.verify("Bearer valid-token", {})
        assert result is True

    @pytest.mark.asyncio
    async def test_service_url_mismatch_rejected(self) -> None:
        v = self._setup_verifier_with_cached_jwks()
        _, mock_jwk_cls = self._make_jwt_mocks()

        mock_jwt_mod = MagicMock()
        mock_jwt_mod.PyJWKClient = mock_jwk_cls
        mock_jwt_mod.decode.return_value = {"serviceUrl": "https://wrong.service.url"}

        with patch.dict("sys.modules", {"jwt": mock_jwt_mod}):
            result = await v.verify(
                "Bearer valid-token",
                {"serviceUrl": "https://correct.service.url"},
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self) -> None:
        v = self._setup_verifier_with_cached_jwks()
        _, mock_jwk_cls = self._make_jwt_mocks()

        mock_jwt_mod = MagicMock()
        mock_jwt_mod.PyJWKClient = mock_jwk_cls
        mock_jwt_mod.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
        mock_jwt_mod.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
        mock_jwt_mod.decode.side_effect = mock_jwt_mod.ExpiredSignatureError()

        with patch.dict("sys.modules", {"jwt": mock_jwt_mod}):
            result = await v.verify("Bearer expired-token", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self) -> None:
        v = self._setup_verifier_with_cached_jwks()
        _, mock_jwk_cls = self._make_jwt_mocks()

        mock_jwt_mod = MagicMock()
        mock_jwt_mod.PyJWKClient = mock_jwk_cls
        mock_jwt_mod.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
        mock_jwt_mod.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
        mock_jwt_mod.decode.side_effect = mock_jwt_mod.InvalidTokenError("bad sig")

        with patch.dict("sys.modules", {"jwt": mock_jwt_mod}):
            result = await v.verify("Bearer bad-token", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_unexpected_error_handled(self) -> None:
        v = self._setup_verifier_with_cached_jwks()
        _, mock_jwk_cls = self._make_jwt_mocks()

        mock_jwt_mod = MagicMock()
        mock_jwt_mod.PyJWKClient = mock_jwk_cls
        mock_jwt_mod.ExpiredSignatureError = type("ExpiredSignatureError", (Exception,), {})
        mock_jwt_mod.InvalidTokenError = type("InvalidTokenError", (Exception,), {})
        mock_jwt_mod.decode.side_effect = RuntimeError("unexpected")

        with patch.dict("sys.modules", {"jwt": mock_jwt_mod}):
            result = await v.verify("Bearer bad-token", {})
        assert result is False
