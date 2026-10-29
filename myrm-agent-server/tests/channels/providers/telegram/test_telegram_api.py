"""Tests for providers/telegram/api.py — TelegramClient."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.providers.telegram.api import TelegramClient
from app.channels.providers.telegram.api_core import TelegramApiError
from tests.channels.providers.telegram.telegram_client_mocks import error_response, mock_client, ok_response


class TestTelegramApiError:
    def test_is_parse_error(self) -> None:
        err = TelegramApiError(400, "Bad Request: can't parse entities")
        assert err.is_parse_error is True

    def test_is_not_modified(self) -> None:
        err = TelegramApiError(400, "Bad Request: message is not modified")
        assert err.is_not_modified is True

    def test_normal_error(self) -> None:
        err = TelegramApiError(500, "Internal Server Error")
        assert err.is_parse_error is False
        assert err.is_not_modified is False
        assert err.error_code == 500


class TestTelegramClient:
    def test_custom_api_base(self) -> None:
        client = TelegramClient("tok", api_base="https://my-proxy.com")
        assert "my-proxy.com" in client._base
        assert "my-proxy.com" in client._file_base

    def test_default_api_base(self) -> None:
        client = TelegramClient("tok")
        assert "api.telegram.org" in client._base

    def test_get_http_creates_client(self) -> None:
        client = TelegramClient("tok")
        http = client._get_http()
        assert isinstance(http, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client, http = mock_client()
        await client.close()
        assert client._http is None

    @pytest.mark.asyncio
    async def test_close_already_closed(self) -> None:
        client = TelegramClient("tok")
        await client.close()

    @pytest.mark.asyncio
    async def test_get_me(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"id": 123, "first_name": "Bot"}))
        result = await client.get_me()
        assert result["id"] == 123

    @pytest.mark.asyncio
    async def test_verify_token_success(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"id": 1}))
        assert await client.verify_token() is True

    @pytest.mark.asyncio
    async def test_verify_token_failure(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=error_response(401, "Unauthorized"))
        assert await client.verify_token() is False

    @pytest.mark.asyncio
    async def test_get_updates(self) -> None:
        client, http = mock_client()
        updates = [{"update_id": 1}]
        http.post = AsyncMock(return_value=ok_response(updates))
        result = await client.get_updates(offset=1, allowed_updates=["message"])
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_updates_non_list(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response("not a list"))
        result = await client.get_updates()
        assert result == []

    @pytest.mark.asyncio
    async def test_set_webhook(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        result = await client.set_webhook("https://example.com/hook", secret_token="s", allowed_updates=["message"])
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_webhook(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        assert await client.delete_webhook() is True

    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 42}))
        result = await client.send_message(
            123,
            "hello",
            reply_to_message_id=10,
            message_thread_id=5,
            reply_markup={"inline_keyboard": []},
        )
        assert result["message_id"] == 42

    @pytest.mark.asyncio
    async def test_edit_message_text(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 42}))
        result = await client.edit_message_text(123, 42, "edited", reply_markup={"inline_keyboard": []})
        assert result["message_id"] == 42

    @pytest.mark.asyncio
    async def test_delete_message_success(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        assert await client.delete_message(123, 42) is True

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=error_response(400, "message not found"))
        assert await client.delete_message(123, 42) is False

    @pytest.mark.asyncio
    async def test_set_my_commands(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        assert await client.set_my_commands([{"command": "start", "description": "Start"}]) is True

    @pytest.mark.asyncio
    async def test_delete_my_commands_success(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        assert await client.delete_my_commands() is True

    @pytest.mark.asyncio
    async def test_delete_my_commands_failure(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=error_response(400, "error"))
        assert await client.delete_my_commands() is False

    @pytest.mark.asyncio
    async def test_pin_chat_message(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        await client.pin_chat_message(123, 42)

    @pytest.mark.asyncio
    async def test_set_message_reaction(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        await client.set_message_reaction(123, 42, [{"type": "emoji", "emoji": "\U0001f44d"}])

    @pytest.mark.asyncio
    async def test_answer_callback_query(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        await client.answer_callback_query("qid")

    @pytest.mark.asyncio
    async def test_answer_callback_query_error(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=error_response(400, "query expired"))
        await client.answer_callback_query("qid")

    @pytest.mark.asyncio
    async def test_send_photo_bytes(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_photo(
            123,
            b"fake-image",
            caption="a photo",
            reply_to_message_id=5,
        )
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_photo_url(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_photo(123, "https://example.com/photo.jpg")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_document_bytes(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_document(
            123,
            b"data",
            "file.pdf",
            caption="doc",
            reply_to_message_id=5,
        )
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_document_url(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_document(123, "https://example.com/file.pdf")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_voice_bytes(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_voice(123, b"ogg-data", caption="voice", reply_to_message_id=1)
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_voice_url(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_voice(123, "https://example.com/voice.ogg")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_bytes(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_audio(123, b"mp3-data", caption="audio", reply_to_message_id=1)
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_url(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_audio(123, "https://example.com/audio.mp3")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_video_bytes(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_video(123, b"mp4-data", caption="video", reply_to_message_id=1)
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_video_url(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"message_id": 1}))
        result = await client.send_video(123, "https://example.com/video.mp4")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_chat_action(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response(True))
        await client.send_chat_action(123)

    @pytest.mark.asyncio
    async def test_send_chat_action_error(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=error_response(400, "error"))
        await client.send_chat_action(123)

    @pytest.mark.asyncio
    async def test_get_file(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"file_path": "photos/file_0.jpg"}))
        result = await client.get_file("file123")
        assert result["file_path"] == "photos/file_0.jpg"

    @pytest.mark.asyncio
    async def test_download_file(self) -> None:
        client, http = mock_client()
        resp = httpx.Response(200, content=b"file-content", request=httpx.Request("GET", "https://x"))
        http.get = AsyncMock(return_value=resp)
        data = await client.download_file("photos/file_0.jpg")
        assert data == b"file-content"

    @pytest.mark.asyncio
    async def test_download_voice_success(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({"file_path": "voice/file_0.ogg"}))
        resp = httpx.Response(200, content=b"ogg-data", request=httpx.Request("GET", "https://x"))
        http.get = AsyncMock(return_value=resp)

        path = await client.download_voice("fid")
        assert path is not None
        assert path.suffix == ".ogg"
        path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_voice_no_path(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=ok_response({}))
        assert await client.download_voice("fid") is None

    @pytest.mark.asyncio
    async def test_download_voice_error(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(side_effect=RuntimeError("network"))
        assert await client.download_voice("fid") is None


# ──────────────────────────────────────────────────────────────────
# Transport
# ──────────────────────────────────────────────────────────────────


class TestOneEndpoint:
    """Every call goes to the one configured endpoint, and its transport errors reach the caller unchanged."""

    @staticmethod
    def _recording_client(error: Exception | None = None) -> tuple[TelegramClient, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if error is not None:
                raise error
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "x"}}, request=request)

        client = TelegramClient("tok")
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return client, seen

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [httpx.ConnectError("down"), httpx.ConnectTimeout("t"), httpx.ReadTimeout("slow")])
    async def test_a_transport_error_is_raised_after_one_request_to_the_official_host(self, error: Exception) -> None:
        client, seen = self._recording_client(error)

        with pytest.raises(type(error)):
            await client._call("sendMessage", json_data={"chat_id": 1, "text": "hi"})

        assert [request.url.host for request in seen] == ["api.telegram.org"]

    @pytest.mark.asyncio
    async def test_a_business_error_is_raised_after_one_request(self) -> None:
        client, http = mock_client()
        http.post = AsyncMock(return_value=error_response(400, "Bad Request"))

        with pytest.raises(TelegramApiError, match="Bad Request"):
            await client._call("getMe")

        assert http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_a_file_is_downloaded_from_the_official_host_without_a_host_override(self) -> None:
        client, seen = self._recording_client()

        await client.download_file("photos/f.jpg")

        assert [request.url.host for request in seen] == ["api.telegram.org"]
        assert seen[0].headers["host"] == "api.telegram.org"
