"""TelegramClient: the error type and one test per Bot API call."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.telegram.api import TelegramClient
from app.channels.providers.telegram.api_core import TelegramApiError
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN


class TestTelegramApiError:
    def test_basic_error(self) -> None:
        err = TelegramApiError(400, "Bad Request")
        assert err.error_code == 400
        assert err.description == "Bad Request"
        assert str(err) == "Telegram API 400: Bad Request"

    def test_is_parse_error(self) -> None:
        err = TelegramApiError(400, "Bad Request: can't parse entities")
        assert err.is_parse_error is True
        err2 = TelegramApiError(400, "Bad Request: other")
        assert err2.is_parse_error is False

    def test_is_not_modified(self) -> None:
        err = TelegramApiError(400, "Bad Request: message is not modified")
        assert err.is_not_modified is True

    def test_parameters(self) -> None:
        err = TelegramApiError(429, "Too Many Requests", {"retry_after": 30})
        assert err.parameters.get("retry_after") == 30


class TestTelegramClient:
    def _make_client(self, api_base: str | None = None) -> TelegramClient:
        return TelegramClient(FAKE_TELEGRAM_BOT_TOKEN, api_base=api_base)

    def test_custom_api_base(self) -> None:
        client = self._make_client(api_base="https://custom.api.org")
        assert "custom.api.org" in client._base

    def test_default_api_base(self) -> None:
        client = self._make_client()
        assert "api.telegram.org" in client._base

    def test_token_property(self) -> None:
        client = self._make_client()
        assert client.token == FAKE_TELEGRAM_BOT_TOKEN

    @pytest.mark.asyncio
    async def test_call_success(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"id": 123, "username": "bot"}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.get_me()
        assert result["id"] == 123

    @pytest.mark.asyncio
    async def test_call_api_error(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"ok": False, "error_code": 401, "description": "Unauthorized"}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        with pytest.raises(TelegramApiError) as exc_info:
            await client.get_me()
        assert exc_info.value.error_code == 401

    @pytest.mark.asyncio
    async def test_verify_token_success(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"id": 1}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.verify_token() is True

    @pytest.mark.asyncio
    async def test_verify_token_failure(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"ok": False, "error_code": 401, "description": "Unauthorized"}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.verify_token() is False

    @pytest.mark.asyncio
    async def test_get_updates(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": [{"update_id": 1}]}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        updates = await client.get_updates(offset=0)
        assert len(updates) == 1

    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_message(123, "Hello!")
        assert result["message_id"] == 42

    @pytest.mark.asyncio
    async def test_send_message_with_reply(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 43}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_message(123, "Reply", reply_to_message_id=10)
        assert result["message_id"] == 43
        call_json = mock_http.post.call_args.kwargs.get("json")
        assert "reply_parameters" in call_json

    @pytest.mark.asyncio
    async def test_edit_message_text(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 42}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.edit_message_text(123, 42, "Updated")
        assert result["message_id"] == 42

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.delete_message(123, 42) is True

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"ok": False, "error_code": 400, "description": "not found"}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.delete_message(123, 42) is False

    @pytest.mark.asyncio
    async def test_send_photo_url(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 50}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_photo(123, "https://example.com/img.jpg")
        assert result["message_id"] == 50

    @pytest.mark.asyncio
    async def test_send_photo_bytes(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 51}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_photo(123, b"\x89PNG", caption="Photo")
        assert result["message_id"] == 51

    @pytest.mark.asyncio
    async def test_send_document_url(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 52}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_document(123, "https://example.com/doc.pdf")
        assert result["message_id"] == 52

    @pytest.mark.asyncio
    async def test_send_voice_bytes(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 53}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_voice(123, b"ogg_data")
        assert result["message_id"] == 53

    @pytest.mark.asyncio
    async def test_send_audio_url(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 54}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_audio(123, "https://example.com/a.mp3")
        assert result["message_id"] == 54

    @pytest.mark.asyncio
    async def test_send_video_bytes(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 55}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.send_video(123, b"mp4_data")
        assert result["message_id"] == 55

    @pytest.mark.asyncio
    async def test_send_chat_action(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        await client.send_chat_action(123, "typing")

    @pytest.mark.asyncio
    async def test_set_webhook(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.set_webhook("https://example.com/webhook", secret_token="sec") is True

    @pytest.mark.asyncio
    async def test_delete_webhook(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.delete_webhook() is True

    @pytest.mark.asyncio
    async def test_set_my_commands(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        assert await client.set_my_commands([{"command": "start", "description": "Start"}]) is True

    @pytest.mark.asyncio
    async def test_answer_callback_query(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": True}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        await client.answer_callback_query("cbq_1")

    @pytest.mark.asyncio
    async def test_get_file(self) -> None:
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"file_id": "f1", "file_path": "photos/f1.jpg"}}
        mock_http = MagicMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.is_closed = False
        client._http = mock_http

        result = await client.get_file("f1")
        assert result["file_path"] == "photos/f1.jpg"

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = self._make_client()
        mock_http = MagicMock()
        mock_http.is_closed = False
        mock_http.aclose = AsyncMock()
        client._http = mock_http

        await client.close()
        mock_http.aclose.assert_called_once()
        assert client._http is None
