"""Tests for Feishu QR scan-to-create registration flow."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.channels.providers.feishu.registration import (
    FeishuAppRegistration,
)


class TestFeishuAppRegistrationInit:
    def test_default_domain(self) -> None:
        reg = FeishuAppRegistration()
        assert reg._domain == "feishu"
        assert reg._current_domain == "feishu"

    def test_lark_domain(self) -> None:
        reg = FeishuAppRegistration(domain="lark")
        assert reg._domain == "lark"
        assert reg._current_domain == "lark"

    def test_accounts_url_feishu(self) -> None:
        reg = FeishuAppRegistration(domain="feishu")
        assert reg._accounts_url() == "https://accounts.feishu.cn"

    def test_accounts_url_lark(self) -> None:
        reg = FeishuAppRegistration(domain="lark")
        assert reg._accounts_url() == "https://accounts.larksuite.com"

    def test_open_api_url_feishu(self) -> None:
        reg = FeishuAppRegistration(domain="feishu")
        assert reg._open_api_url() == "https://open.feishu.cn"

    def test_open_api_url_lark(self) -> None:
        reg = FeishuAppRegistration(domain="lark")
        assert reg._open_api_url() == "https://open.larksuite.com"

    def test_fallback_to_feishu_for_unknown_domain(self) -> None:
        reg = FeishuAppRegistration(domain="unknown")
        assert reg._accounts_url() == "https://accounts.feishu.cn"
        assert reg._open_api_url() == "https://open.feishu.cn"


class TestPostRegistration:
    def test_successful_post(self) -> None:
        reg = FeishuAppRegistration()
        response_data = {"supported_auth_methods": ["client_secret"]}

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch(
            "app.channels.providers.feishu.registration.urlopen",
            return_value=mock_resp,
        ):
            result = reg._post_registration({"action": "init"})
            assert result == response_data

    def test_http_error_with_json_body(self) -> None:
        from urllib.error import HTTPError

        reg = FeishuAppRegistration()
        error_data = {"error": "authorization_pending"}

        exc = HTTPError("url", 400, "Bad Request", {}, None)  # type: ignore[arg-type]
        exc.read = MagicMock(return_value=json.dumps(error_data).encode("utf-8"))

        with patch(
            "app.channels.providers.feishu.registration.urlopen",
            side_effect=exc,
        ):
            result = reg._post_registration({"action": "poll", "device_code": "dc"})
            assert result == error_data

    def test_http_error_without_body_raises(self) -> None:
        from urllib.error import HTTPError

        reg = FeishuAppRegistration()
        exc = HTTPError("url", 500, "Server Error", {}, None)  # type: ignore[arg-type]
        exc.read = MagicMock(return_value=b"")

        with patch(
            "app.channels.providers.feishu.registration.urlopen",
            side_effect=exc,
        ), pytest.raises(HTTPError):
            reg._post_registration({"action": "init"})


class TestBegin:
    @pytest.mark.asyncio
    async def test_begin_success(self) -> None:
        reg = FeishuAppRegistration()
        init_response = {"supported_auth_methods": ["client_secret"]}
        begin_response = {
            "device_code": "dc_123",
            "verification_uri_complete": "https://feishu.cn/scan?code=abc",
            "user_code": "USER123",
            "interval": 3,
            "expire_in": 300,
        }

        call_count = 0

        def mock_post(body: dict[str, str]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return init_response
            return begin_response

        with patch.object(reg, "_post_registration", side_effect=mock_post):
            result = await reg.begin()

        assert result["device_code"] == "dc_123"
        assert "from=myrm" in result["qr_url"]
        assert result["user_code"] == "USER123"
        assert result["interval"] == 3
        assert result["expire_in"] == 300

    @pytest.mark.asyncio
    async def test_begin_no_client_secret_support(self) -> None:
        reg = FeishuAppRegistration()
        init_response = {"supported_auth_methods": ["oauth2"]}

        with patch.object(reg, "_post_registration", return_value=init_response):
            with pytest.raises(RuntimeError, match="does not support client_secret"):
                await reg.begin()

    @pytest.mark.asyncio
    async def test_begin_no_device_code(self) -> None:
        reg = FeishuAppRegistration()
        init_response = {"supported_auth_methods": ["client_secret"]}
        begin_response: dict[str, Any] = {}

        call_count = 0

        def mock_post(body: dict[str, str]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return init_response if call_count == 1 else begin_response

        with patch.object(reg, "_post_registration", side_effect=mock_post):
            with pytest.raises(RuntimeError, match="did not return device_code"):
                await reg.begin()

    @pytest.mark.asyncio
    async def test_begin_qr_url_separator_handling(self) -> None:
        reg = FeishuAppRegistration()
        init_response = {"supported_auth_methods": ["client_secret"]}
        begin_response = {
            "device_code": "dc_456",
            "verification_uri_complete": "https://feishu.cn/scan",
            "interval": 5,
            "expire_in": 600,
        }

        call_count = 0

        def mock_post(body: dict[str, str]) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return init_response if call_count == 1 else begin_response

        with patch.object(reg, "_post_registration", side_effect=mock_post):
            result = await reg.begin()
            assert "?from=myrm" in result["qr_url"]


class TestPoll:
    @pytest.mark.asyncio
    async def test_poll_success(self) -> None:
        reg = FeishuAppRegistration()
        poll_response: dict[str, Any] = {
            "client_id": "cli_abc",
            "client_secret": "secret_xyz",
            "user_info": {"open_id": "ou_123", "tenant_brand": "feishu"},
        }

        with patch.object(reg, "_post_registration", return_value=poll_response):
            result = await reg.poll("dc_123")

        assert result["status"] == "success"
        assert result["credentials"] is not None
        assert result["credentials"]["app_id"] == "cli_abc"
        assert result["credentials"]["app_secret"] == "secret_xyz"
        assert result["credentials"]["open_id"] == "ou_123"

    @pytest.mark.asyncio
    async def test_poll_pending(self) -> None:
        reg = FeishuAppRegistration()
        poll_response: dict[str, Any] = {"error": "authorization_pending"}

        with patch.object(reg, "_post_registration", return_value=poll_response):
            result = await reg.poll("dc_123")

        assert result["status"] == "pending"
        assert result["credentials"] is None

    @pytest.mark.asyncio
    async def test_poll_denied(self) -> None:
        reg = FeishuAppRegistration()
        poll_response: dict[str, Any] = {"error": "access_denied"}

        with patch.object(reg, "_post_registration", return_value=poll_response):
            result = await reg.poll("dc_123")

        assert result["status"] == "denied"

    @pytest.mark.asyncio
    async def test_poll_expired(self) -> None:
        reg = FeishuAppRegistration()
        poll_response: dict[str, Any] = {"error": "expired_token"}

        with patch.object(reg, "_post_registration", return_value=poll_response):
            result = await reg.poll("dc_123")

        assert result["status"] == "expired"

    @pytest.mark.asyncio
    async def test_poll_network_error_returns_pending(self) -> None:
        from urllib.error import URLError

        reg = FeishuAppRegistration()

        with patch.object(reg, "_post_registration", side_effect=URLError("timeout")):
            result = await reg.poll("dc_123")

        assert result["status"] == "pending"
        assert result["credentials"] is None

    @pytest.mark.asyncio
    async def test_poll_auto_detects_lark_domain(self) -> None:
        reg = FeishuAppRegistration(domain="feishu")
        poll_response: dict[str, Any] = {
            "error": "authorization_pending",
            "user_info": {"tenant_brand": "lark"},
        }

        with patch.object(reg, "_post_registration", return_value=poll_response):
            await reg.poll("dc_123")

        assert reg._current_domain == "lark"


def _make_async_client_mock(
    post_json: dict[str, Any],
    get_json: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock httpx.AsyncClient that works with async with."""
    from unittest.mock import AsyncMock

    token_resp = MagicMock()
    token_resp.json.return_value = post_json

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = token_resp

    if get_json is not None:
        bot_resp = MagicMock()
        bot_resp.json.return_value = get_json
        mock_client.get.return_value = bot_resp

    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


class TestProbeBot:
    @pytest.mark.asyncio
    async def test_probe_bot_success(self) -> None:
        reg = FeishuAppRegistration()
        mock_client = _make_async_client_mock(
            post_json={"tenant_access_token": "t_abc"},
            get_json={"code": 0, "bot": {"app_name": "MyBot", "open_id": "ou_bot_123"}},
        )

        with patch("app.channels.providers.feishu.registration.httpx.AsyncClient", return_value=mock_client):
            result = await reg.probe_bot("cli_abc", "secret_xyz")

        assert result["bot_name"] == "MyBot"
        assert result["bot_open_id"] == "ou_bot_123"

    @pytest.mark.asyncio
    async def test_probe_bot_no_token(self) -> None:
        reg = FeishuAppRegistration()
        mock_client = _make_async_client_mock(post_json={})

        with patch("app.channels.providers.feishu.registration.httpx.AsyncClient", return_value=mock_client):
            result = await reg.probe_bot("cli_abc", "secret_xyz")

        assert result["bot_name"] is None
        assert result["bot_open_id"] is None

    @pytest.mark.asyncio
    async def test_probe_bot_exception_returns_empty(self) -> None:
        reg = FeishuAppRegistration()

        with patch("app.channels.providers.feishu.registration.httpx.AsyncClient", side_effect=Exception("connection refused")):
            result = await reg.probe_bot("cli_abc", "secret_xyz")

        assert result["bot_name"] is None
        assert result["bot_open_id"] is None

    @pytest.mark.asyncio
    async def test_probe_bot_non_zero_code(self) -> None:
        reg = FeishuAppRegistration()
        mock_client = _make_async_client_mock(
            post_json={"tenant_access_token": "t_abc"},
            get_json={"code": 99991},
        )

        with patch("app.channels.providers.feishu.registration.httpx.AsyncClient", return_value=mock_client):
            result = await reg.probe_bot("cli_abc", "secret_xyz")

        assert result["bot_name"] is None
        assert result["bot_open_id"] is None
