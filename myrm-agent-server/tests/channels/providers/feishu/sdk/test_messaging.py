"""Tests for feishu SDK messaging — FeishuMessagingMixin methods."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.channels.providers.feishu.sdk import FeishuClient
from app.channels.providers.feishu.sdk.exceptions import (
    FeishuRateLimitError,
    FeishuSendError,
)


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


@pytest.fixture
def client() -> FeishuClient:
    c = FeishuClient("app", "secret")
    c._token = "tok"
    c._token_expires_at = time.monotonic() + 3600
    mock_http = AsyncMock()
    mock_http.is_closed = False
    c._http = mock_http
    return c


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"message_id": "msg_001"}})
        client._http.post = AsyncMock(return_value=resp)
        msg_id = await client.send_message("chat_123", "text", '{"text":"hi"}')
        assert msg_id == "msg_001"

    @pytest.mark.asyncio
    async def test_with_reply_in_thread(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"message_id": "msg_002"}})
        client._http.post = AsyncMock(return_value=resp)
        msg_id = await client.send_message("chat_123", "text", "{}", reply_in_thread=True)
        assert msg_id == "msg_002"
        body = client._http.post.call_args.kwargs.get("json", {})
        assert body.get("reply_in_thread") is True

    @pytest.mark.asyncio
    async def test_rate_limit(self, client: FeishuClient) -> None:
        resp = _mock_response(429)
        client._http.post = AsyncMock(return_value=resp)
        with pytest.raises(FeishuRateLimitError):
            await client.send_message("chat_123", "text", '{"text":"hi"}')

    @pytest.mark.asyncio
    async def test_server_error(self, client: FeishuClient) -> None:
        resp = _mock_response(500, {"msg": "internal error"})
        client._http.post = AsyncMock(return_value=resp)
        with pytest.raises(FeishuSendError) as exc_info:
            await client.send_message("chat_123", "text", '{"text":"hi"}')
        assert exc_info.value.retriable is True
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_client_error_not_retriable(self, client: FeishuClient) -> None:
        resp = _mock_response(400, {"msg": "bad request"})
        client._http.post = AsyncMock(return_value=resp)
        with pytest.raises(FeishuSendError) as exc_info:
            await client.send_message("chat_123", "text", '{"text":"hi"}')
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "param error"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.send_message("chat_123", "text", '{"text":"hi"}')
        assert result is None


class TestReplyMessage:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"message_id": "reply_001"}})
        client._http.post = AsyncMock(return_value=resp)
        msg_id = await client.reply_message("orig_msg", "text", '{"text":"reply"}')
        assert msg_id == "reply_001"

    @pytest.mark.asyncio
    async def test_with_reply_in_thread(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"message_id": "reply_002"}})
        client._http.post = AsyncMock(return_value=resp)
        msg_id = await client.reply_message("orig_msg", "text", "{}", reply_in_thread=True)
        assert msg_id == "reply_002"

    @pytest.mark.asyncio
    async def test_rate_limit(self, client: FeishuClient) -> None:
        resp = _mock_response(429)
        client._http.post = AsyncMock(return_value=resp)
        with pytest.raises(FeishuRateLimitError):
            await client.reply_message("orig_msg", "text", '{"text":"reply"}')

    @pytest.mark.asyncio
    async def test_server_error(self, client: FeishuClient) -> None:
        resp = _mock_response(500, {"msg": "server error"})
        client._http.post = AsyncMock(return_value=resp)
        with pytest.raises(FeishuSendError) as exc_info:
            await client.reply_message("orig_msg", "text", "{}")
        assert exc_info.value.retriable is True

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "param error"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.reply_message("orig_msg", "text", "{}")
        assert result is None


class TestEditDeleteMessage:
    @pytest.mark.asyncio
    async def test_edit_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.put = AsyncMock(return_value=resp)
        result = await client.edit_message("msg_001", "text", '{"text":"edited"}')
        assert result is True

    @pytest.mark.asyncio
    async def test_edit_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "not allowed"})
        client._http.put = AsyncMock(return_value=resp)
        result = await client.edit_message("msg_001", "text", '{"text":"edited"}')
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.delete = AsyncMock(return_value=resp)
        result = await client.delete_message("msg_001")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.delete = AsyncMock(return_value=resp)
        result = await client.delete_message("msg_001")
        assert result is False

    @pytest.mark.asyncio
    async def test_patch_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.patch_message("msg_001", "interactive", "{}")
        assert result is True

    @pytest.mark.asyncio
    async def test_patch_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(400)
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.patch_message("msg_001", "interactive", "{}")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_delegates_to_patch(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.patch = AsyncMock(return_value=resp)
        result = await client.update_message("msg_001", "text", '{"text":"up"}')
        assert result is True


class TestReactions:
    @pytest.mark.asyncio
    async def test_add_reaction_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"reaction_id": "r_001"}})
        client._http.post = AsyncMock(return_value=resp)
        rid = await client.add_reaction("msg_001", "THUMBSUP")
        assert rid == "r_001"

    @pytest.mark.asyncio
    async def test_add_reaction_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99})
        client._http.post = AsyncMock(return_value=resp)
        rid = await client.add_reaction("msg_001")
        assert rid is None

    @pytest.mark.asyncio
    async def test_add_reaction_no_reaction_id(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {}})
        client._http.post = AsyncMock(return_value=resp)
        rid = await client.add_reaction("msg_001")
        assert rid is None

    @pytest.mark.asyncio
    async def test_delete_reaction_success(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0})
        client._http.delete = AsyncMock(return_value=resp)
        result = await client.delete_reaction("msg_001", "r_001")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_reaction_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99})
        client._http.delete = AsyncMock(return_value=resp)
        result = await client.delete_reaction("msg_001", "r_001")
        assert result is False


class TestGetMessage:
    @pytest.mark.asyncio
    async def test_success(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {"items": [{"message_id": "msg_001", "body": {"content": "hi"}}]},
            },
        )
        client._http.get = AsyncMock(return_value=resp)
        msg = await client.get_message("msg_001")
        assert msg is not None and msg["message_id"] == "msg_001"

    @pytest.mark.asyncio
    async def test_not_found(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "not found"})
        client._http.get = AsyncMock(return_value=resp)
        assert await client.get_message("nonexist") is None

    @pytest.mark.asyncio
    async def test_data_not_dict(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": "bad"})
        client._http.get = AsyncMock(return_value=resp)
        assert await client.get_message("msg") is None

    @pytest.mark.asyncio
    async def test_empty_items(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"items": []}})
        client._http.get = AsyncMock(return_value=resp)
        assert await client.get_message("msg") is None

    @pytest.mark.asyncio
    async def test_item_not_dict(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"items": ["bad"]}})
        client._http.get = AsyncMock(return_value=resp)
        assert await client.get_message("msg") is None


class TestMedia:
    @pytest.mark.asyncio
    async def test_upload_image(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"image_key": "img_key_001"}})
        client._http.post = AsyncMock(return_value=resp)
        key = await client.upload_image(b"\x89PNG\r\n")
        assert key == "img_key_001"

    @pytest.mark.asyncio
    async def test_upload_image_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        key = await client.upload_image(b"\x89PNG\r\n")
        assert key is None

    @pytest.mark.asyncio
    async def test_download_image(self, client: FeishuClient) -> None:
        resp = _mock_response(200, content=b"\x89PNG\r\n")
        client._http.get = AsyncMock(return_value=resp)
        data = await client.download_image("img_key_001")
        assert data == b"\x89PNG\r\n"

    @pytest.mark.asyncio
    async def test_download_image_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(404)
        client._http.get = AsyncMock(return_value=resp)
        data = await client.download_image("invalid")
        assert data is None

    @pytest.mark.asyncio
    async def test_upload_file(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"file_key": "file_key_001"}})
        client._http.post = AsyncMock(return_value=resp)
        key = await client.upload_file(b"file content", "test.txt")
        assert key == "file_key_001"

    @pytest.mark.asyncio
    async def test_upload_file_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "fail"})
        client._http.post = AsyncMock(return_value=resp)
        key = await client.upload_file(b"data", "test.txt")
        assert key is None

    @pytest.mark.asyncio
    async def test_download_message_resource(self, client: FeishuClient) -> None:
        resp = _mock_response(200, content=b"resource_data")
        client._http.get = AsyncMock(return_value=resp)
        data = await client.download_message_resource("msg_001", "file_key_001")
        assert data == b"resource_data"

    @pytest.mark.asyncio
    async def test_download_message_resource_failure(self, client: FeishuClient) -> None:
        resp = _mock_response(500)
        client._http.get = AsyncMock(return_value=resp)
        data = await client.download_message_resource("msg_001", "file_key_001")
        assert data is None


class TestFreeBusy:
    @pytest.mark.asyncio
    async def test_success_with_busy_slots(self, client: FeishuClient) -> None:
        resp = _mock_response(
            200,
            {
                "code": 0,
                "data": {"freebusy_list": [{"start_time": "10:00", "end_time": "11:00"}]},
            },
        )
        client._http.post = AsyncMock(return_value=resp)
        result = await client.get_freebusy(["ou_user1"], "2026-01-01", "2026-01-02")
        assert len(result) == 1
        assert result[0]["user_id"] == "ou_user1"
        assert len(result[0]["busy_slots"]) == 1

    @pytest.mark.asyncio
    async def test_api_error_skips_user(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 99, "msg": "no perm"})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.get_freebusy(["ou_user1"], "2026-01-01", "2026-01-02")
        assert result == []

    @pytest.mark.asyncio
    async def test_empty_freebusy_list(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"freebusy_list": []}})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.get_freebusy(["ou_user1"], "2026-01-01", "2026-01-02")
        assert len(result) == 1
        assert result[0]["busy_slots"] == []

    @pytest.mark.asyncio
    async def test_user_access_token(self, client: FeishuClient) -> None:
        resp = _mock_response(200, {"code": 0, "data": {"freebusy_list": []}})
        client._http.post = AsyncMock(return_value=resp)
        result = await client.get_freebusy(
            ["ou_user1"],
            "2026-01-01",
            "2026-01-02",
            user_access_token="user_tok",
        )
        assert len(result) == 1
        call_args = client._http.post.call_args
        headers = call_args.kwargs.get("headers", call_args[1].get("headers", {}))
        assert headers.get("Authorization") == "Bearer user_tok"

    @pytest.mark.asyncio
    async def test_multiple_users(self, client: FeishuClient) -> None:
        resp1 = _mock_response(
            200,
            {
                "code": 0,
                "data": {"freebusy_list": [{"start_time": "9:00", "end_time": "10:00"}]},
            },
        )
        resp2 = _mock_response(200, {"code": 0, "data": {"freebusy_list": []}})
        client._http.post = AsyncMock(side_effect=[resp1, resp2])
        result = await client.get_freebusy(
            ["ou_user1", "ou_user2"],
            "2026-01-01",
            "2026-01-02",
        )
        assert len(result) == 2
        assert len(result[0]["busy_slots"]) == 1
        assert len(result[1]["busy_slots"]) == 0
