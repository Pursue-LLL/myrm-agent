"""Tests for feishu SDK client — FeishuClient core functionality."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.channels.providers.feishu.sdk import FeishuClient
from app.channels.providers.feishu.sdk.exceptions import (
    FeishuAuthError,
)

# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def client() -> FeishuClient:
    return FeishuClient("test_app_id", "test_app_secret")


@pytest.fixture
def lark_client() -> FeishuClient:
    return FeishuClient("test_app_id", "test_app_secret", use_lark=True)


def _mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    content: bytes = b"",
) -> httpx.Response:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_data or {}
    resp.content = content
    return resp


# ── Init & Config ────────────────────────────────────────────────

class TestInit:
    def test_default_api_base(self, client: FeishuClient) -> None:
        assert "feishu.cn" in client.api_base

    def test_lark_api_base(self, lark_client: FeishuClient) -> None:
        assert "larksuite.com" in lark_client.api_base

    def test_is_configured(self, client: FeishuClient) -> None:
        assert client.is_configured is True

    def test_not_configured(self) -> None:
        c = FeishuClient("", "")
        assert c.is_configured is False

    def test_partially_configured(self) -> None:
        c = FeishuClient("app_id", "")
        assert c.is_configured is False


# ── HTTP Client ──────────────────────────────────────────────────

class TestHttpClient:
    def test_get_http_creates_client(self, client: FeishuClient) -> None:
        http = client._get_http()
        assert isinstance(http, httpx.AsyncClient)

    def test_get_http_reuses_client(self, client: FeishuClient) -> None:
        http1 = client._get_http()
        http2 = client._get_http()
        assert http1 is http2

    @pytest.mark.asyncio
    async def test_close(self, client: FeishuClient) -> None:
        _ = client._get_http()
        assert client._http is not None
        await client.close()
        assert client._http is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, client: FeishuClient) -> None:
        await client.close()
        await client.close()


# ── Token Management ─────────────────────────────────────────────

class TestTokenManagement:
    @pytest.mark.asyncio
    async def test_ensure_token_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "tenant_access_token": "tok123", "expire": 7200})
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=resp)
        mock_http.is_closed = False
        client._http = mock_http

        token = await client.ensure_token()
        assert token == "tok123"
        assert client._token == "tok123"

    @pytest.mark.asyncio
    async def test_ensure_token_cached(self, client: FeishuClient) -> None:
        client._token = "cached_tok"
        client._token_expires_at = time.monotonic() + 3600

        token = await client.ensure_token()
        assert token == "cached_tok"

    @pytest.mark.asyncio
    async def test_ensure_token_http_error(self, client: FeishuClient) -> None:
        resp = _mock_response(500)
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=resp)
        mock_http.is_closed = False
        client._http = mock_http

        with pytest.raises(FeishuAuthError, match="HTTP 500"):
            await client.ensure_token()

    @pytest.mark.asyncio
    async def test_ensure_token_api_error(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99999, "msg": "invalid app"})
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=resp)
        mock_http.is_closed = False
        client._http = mock_http

        with pytest.raises(FeishuAuthError, match="code=99999"):
            await client.ensure_token()

    @pytest.mark.asyncio
    async def test_ensure_token_double_check_lock(self, client: FeishuClient) -> None:
        """Verify double-check locking: second caller uses cached token."""
        call_count = 0

        async def mock_post(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return _mock_response(200, {"code": 0, "tenant_access_token": f"tok{call_count}", "expire": 7200})

        mock_http = AsyncMock()
        mock_http.post = mock_post
        mock_http.is_closed = False
        client._http = mock_http

        results = await asyncio.gather(
            client.ensure_token(),
            client.ensure_token(),
        )
        assert results[0] == results[1]
        assert call_count == 1


# ── Safe JSON ────────────────────────────────────────────────────

class TestSafeJson:
    def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"id": "123"}})
        result = client._safe_json(resp, "test")
        assert result["code"] == 0

    def test_http_error(self, client: FeishuClient) -> None:
        resp = _mock_response(500)
        result = client._safe_json(resp, "test")
        assert result["code"] == 500

    def test_non_json(self, client: FeishuClient) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.is_success = True
        resp.json.side_effect = ValueError("not json")
        result = client._safe_json(resp, "test")
        assert result["code"] == -1

    def test_non_dict_json(self, client: FeishuClient) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.is_success = True
        resp.json.return_value = [1, 2, 3]
        result = client._safe_json(resp, "test")
        assert result["code"] == -1


# ── Auth Header ──────────────────────────────────────────────────

class TestAuth:
    def test_auth_header(self, client: FeishuClient) -> None:
        headers = client._auth("my_token")
        assert headers == {"Authorization": "Bearer my_token"}


# ── Verify Connectivity ─────────────────────────────────────────

class TestVerifyConnectivity:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        client._token = "tok"
        client._token_expires_at = time.monotonic() + 3600
        assert await client.verify_connectivity() is True

    @pytest.mark.asyncio
    async def test_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(500)
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=resp)
        mock_http.is_closed = False
        client._http = mock_http
        assert await client.verify_connectivity() is False


# ── Fetch Bot Info ───────────────────────────────────────────────

class TestFetchBotInfo:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        client._token = "tok"
        client._token_expires_at = time.monotonic() + 3600
        resp = _mock_response(200, {"bot": {"open_id": "ou_bot123"}})
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=resp)
        mock_http.is_closed = False
        client._http = mock_http

        bot_id = await client.fetch_bot_info()
        assert bot_id == "ou_bot123"
        assert client.bot_open_id == "ou_bot123"
