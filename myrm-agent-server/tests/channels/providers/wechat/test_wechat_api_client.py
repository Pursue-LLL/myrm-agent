"""Tests for WeChatOfficialApiClient retry and error hints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.exceptions import ChannelAuthError, ChannelConnectionError
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


@pytest.mark.asyncio
async def test_get_json_success() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    token = httpx.Response(
        200,
        json={"access_token": "token_abc", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    ok = httpx.Response(
        200,
        json={"errcode": 0, "user_list": []},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/user/get"),
    )
    http.get = AsyncMock(side_effect=[token, ok])

    client = WeChatOfficialApiClient("app", "secret", http=http)
    data = await client.get_json("user/get")

    assert data["user_list"] == []


@pytest.mark.asyncio
async def test_post_json_retries_on_token_expired() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    expired = httpx.Response(
        200,
        json={"errcode": 40001, "errmsg": "invalid credential"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/draft/add"),
    )
    ok = httpx.Response(
        200,
        json={"errcode": 0, "media_id": "draft_retry"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/draft/add"),
    )
    token = httpx.Response(
        200,
        json={"access_token": "token_new", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    http.post = AsyncMock(side_effect=[expired, ok])
    http.get = AsyncMock(side_effect=[token, token])

    client = WeChatOfficialApiClient("app", "secret", http=http)
    data = await client.post_json("draft/add", {"articles": []})

    assert data["media_id"] == "draft_retry"
    assert http.post.await_count == 2


@pytest.mark.asyncio
async def test_post_multipart_retries_transient_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    limited = httpx.Response(
        200,
        json={"errcode": 45009, "errmsg": "reach max api daily quota limit"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/media/uploadimg"),
    )
    ok = httpx.Response(
        200,
        json={"errcode": 0, "url": "https://mmbiz.qpic.cn/uploaded"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/media/uploadimg"),
    )
    token = httpx.Response(
        200,
        json={"access_token": "token_abc", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    http.post = AsyncMock(side_effect=[limited, ok])
    http.get = AsyncMock(return_value=token)

    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "app.channels.providers.wechat.wechat_api_client.asyncio.sleep",
        sleep_mock,
    )

    client = WeChatOfficialApiClient("app", "secret", http=http)
    data = await client.post_multipart(
        "media/uploadimg",
        field_name="media",
        filename="cover.png",
        content=b"png-bytes",
    )

    assert data["url"] == "https://mmbiz.qpic.cn/uploaded"
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_token_raises_on_http_error() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.get = AsyncMock(
        return_value=httpx.Response(
            500,
            text="server error",
            request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
        )
    )

    client = WeChatOfficialApiClient("app", "secret", http=http)

    with pytest.raises(ChannelAuthError):
        await client.ensure_token()


@pytest.mark.asyncio
async def test_refresh_token_raises_on_wechat_errcode() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.get = AsyncMock(
        return_value=httpx.Response(
            200,
            json={"errcode": 40013, "errmsg": "invalid appid"},
            request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
        )
    )

    client = WeChatOfficialApiClient("app", "secret", http=http)

    with pytest.raises(ChannelAuthError):
        await client.ensure_token()


@pytest.mark.asyncio
async def test_parse_json_response_raises_on_http_status() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    token = httpx.Response(
        200,
        json={"access_token": "token_abc", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    bad = httpx.Response(
        503,
        text="unavailable",
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/draft/add"),
    )
    http.post = AsyncMock(return_value=bad)
    http.get = AsyncMock(return_value=token)

    client = WeChatOfficialApiClient("app", "secret", http=http)

    with pytest.raises(ChannelConnectionError, match="HTTP 503"):
        await client.post_json("draft/add", {"articles": []})


@pytest.mark.asyncio
async def test_close_disposes_owned_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    http.aclose = AsyncMock()
    monkeypatch.setattr(
        "app.channels.providers.wechat.wechat_api_client.httpx.AsyncClient",
        lambda: http,
    )
    client = WeChatOfficialApiClient("app", "secret")
    await client.close()
    http.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_post_multipart_retries_on_token_expired() -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    expired = httpx.Response(
        200,
        json={"errcode": 42001, "errmsg": "access_token expired"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/media/upload"),
    )
    ok = httpx.Response(
        200,
        json={"errcode": 0, "media_id": "thumb_retry"},
        request=httpx.Request("POST", "https://api.weixin.qq.com/cgi-bin/media/upload"),
    )
    token = httpx.Response(
        200,
        json={"access_token": "token_new", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    http.post = AsyncMock(side_effect=[expired, ok])
    http.get = AsyncMock(side_effect=[token, token])

    client = WeChatOfficialApiClient("app", "secret", http=http)
    data = await client.post_multipart(
        "media/upload",
        field_name="media",
        filename="cover.png",
        content=b"png-bytes",
        extra_params={"type": "thumb"},
    )

    assert data["media_id"] == "thumb_retry"


@pytest.mark.asyncio
async def test_get_json_retries_transient_system_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    http = AsyncMock(spec=httpx.AsyncClient)
    busy = httpx.Response(
        200,
        json={"errcode": -1, "errmsg": "system error"},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/user/get"),
    )
    ok = httpx.Response(
        200,
        json={"errcode": 0, "total": 0},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/user/get"),
    )
    token = httpx.Response(
        200,
        json={"access_token": "token_abc", "expires_in": 7200},
        request=httpx.Request("GET", "https://api.weixin.qq.com/cgi-bin/token"),
    )
    http.get = AsyncMock(side_effect=[token, busy, ok])

    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "app.channels.providers.wechat.wechat_api_client.asyncio.sleep",
        sleep_mock,
    )

    client = WeChatOfficialApiClient("app", "secret", http=http)
    data = await client.get_json("user/get")

    assert data["total"] == 0
    sleep_mock.assert_awaited_once()
