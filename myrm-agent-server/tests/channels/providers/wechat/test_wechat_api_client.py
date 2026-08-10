"""Tests for WeChatOfficialApiClient retry and error hints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.exceptions import ChannelConnectionError
from app.channels.providers.wechat.wechat_api_client import WeChatOfficialApiClient
from app.channels.providers.wechat.wechat_api_errors import format_wechat_api_error_message


def test_format_wechat_api_error_message_ip_whitelist_zh() -> None:
    message = format_wechat_api_error_message(
        40164,
        "invalid ip",
        path="draft/add",
        locale="zh",
    )
    assert "IP 白名单" in message
    assert "errcode=40164" in message


def test_format_wechat_api_error_message_ip_whitelist_en() -> None:
    message = format_wechat_api_error_message(
        40164,
        "invalid ip",
        path="draft/add",
        locale="en",
    )
    assert "IP whitelist" in message


@pytest.mark.asyncio
async def test_post_json_retries_transient_system_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    busy = httpx.Response(
        200,
        json={"errcode": -1, "errmsg": "system error"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/draft/add"),
    )
    ok = httpx.Response(
        200,
        json={"errcode": 0, "media_id": "draft_123"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/draft/add"),
    )
    token = httpx.Response(
        200,
        json={"access_token": "token_abc", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    http.post = AsyncMock(side_effect=[busy, ok])
    http.get = AsyncMock(return_value=token)

    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "app.channels.providers.wechat.wechat_api_client.asyncio.sleep",
        sleep_mock,
    )

    client = WeChatOfficialApiClient("app", "secret", http=http)
    data = await client.post_json("draft/add", {"articles": []})

    assert data["media_id"] == "draft_123"
    assert http.post.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_json_raises_actionable_error_for_ip_whitelist() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    denied = httpx.Response(
        200,
        json={"errcode": 40164, "errmsg": "invalid ip"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/draft/add"),
    )
    token = httpx.Response(
        200,
        json={"access_token": "token_abc", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    http.post = AsyncMock(return_value=denied)
    http.get = AsyncMock(return_value=token)

    client = WeChatOfficialApiClient("app", "secret", http=http, locale="zh")

    with pytest.raises(ChannelConnectionError) as exc_info:
        await client.post_json("draft/add", {"articles": []})

    assert "IP 白名单" in str(exc_info.value)
