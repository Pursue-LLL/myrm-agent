"""Tests for providers/telegram/api.py — TelegramClient."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.providers.telegram.api import (
    _API_HOST,
    _FALLBACK_IPS,
    TelegramApiError,
    TelegramClient,
)


def _mock_client() -> TelegramClient:
    client = TelegramClient("test-token")
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.is_closed = False
    client._http = mock_http
    return client


def _ok_response(result: object = None) -> httpx.Response:
    """Build a mock Telegram API success response."""

    body = {"ok": True, "result": result or {}}
    return httpx.Response(200, json=body)


def _error_response(code: int = 400, desc: str = "Bad Request") -> httpx.Response:
    body = {"ok": False, "error_code": code, "description": desc}
    return httpx.Response(code, json=body)


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
        client = _mock_client()
        await client.close()
        assert client._http is None

    @pytest.mark.asyncio
    async def test_close_already_closed(self) -> None:
        client = TelegramClient("tok")
        await client.close()

    @pytest.mark.asyncio
    async def test_get_me(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"id": 123, "first_name": "Bot"}))
        result = await client.get_me()
        assert result["id"] == 123

    @pytest.mark.asyncio
    async def test_verify_token_success(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"id": 1}))
        assert await client.verify_token() is True

    @pytest.mark.asyncio
    async def test_verify_token_failure(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_error_response(401, "Unauthorized"))
        assert await client.verify_token() is False

    @pytest.mark.asyncio
    async def test_get_updates(self) -> None:
        client = _mock_client()
        updates = [{"update_id": 1}]
        client._http.post = AsyncMock(return_value=_ok_response(updates))
        result = await client.get_updates(offset=1, allowed_updates=["message"])
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_updates_non_list(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response("not a list"))
        result = await client.get_updates()
        assert result == []

    @pytest.mark.asyncio
    async def test_set_webhook(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        result = await client.set_webhook("https://example.com/hook", secret_token="s", allowed_updates=["message"])
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_webhook(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.delete_webhook() is True

    @pytest.mark.asyncio
    async def test_send_message(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 42}))
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
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 42}))
        result = await client.edit_message_text(123, 42, "edited", reply_markup={"inline_keyboard": []})
        assert result["message_id"] == 42

    @pytest.mark.asyncio
    async def test_delete_message_success(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.delete_message(123, 42) is True

    @pytest.mark.asyncio
    async def test_delete_message_failure(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_error_response(400, "message not found"))
        assert await client.delete_message(123, 42) is False

    @pytest.mark.asyncio
    async def test_set_my_commands(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.set_my_commands([{"command": "start", "description": "Start"}]) is True

    @pytest.mark.asyncio
    async def test_delete_my_commands_success(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.delete_my_commands() is True

    @pytest.mark.asyncio
    async def test_delete_my_commands_failure(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_error_response(400, "error"))
        assert await client.delete_my_commands() is False

    @pytest.mark.asyncio
    async def test_pin_chat_message(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        await client.pin_chat_message(123, 42)

    @pytest.mark.asyncio
    async def test_set_message_reaction(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        await client.set_message_reaction(123, 42, [{"type": "emoji", "emoji": "\U0001f44d"}])

    @pytest.mark.asyncio
    async def test_answer_callback_query(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        await client.answer_callback_query("qid")

    @pytest.mark.asyncio
    async def test_answer_callback_query_error(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_error_response(400, "query expired"))
        await client.answer_callback_query("qid")

    @pytest.mark.asyncio
    async def test_send_photo_bytes(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_photo(
            123,
            b"fake-image",
            caption="a photo",
            reply_to_message_id=5,
        )
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_photo_url(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_photo(123, "https://example.com/photo.jpg")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_document_bytes(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
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
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_document(123, "https://example.com/file.pdf")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_voice_bytes(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_voice(123, b"ogg-data", caption="voice", reply_to_message_id=1)
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_voice_url(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_voice(123, "https://example.com/voice.ogg")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_bytes(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_audio(123, b"mp3-data", caption="audio", reply_to_message_id=1)
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_url(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_audio(123, "https://example.com/audio.mp3")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_video_bytes(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_video(123, b"mp4-data", caption="video", reply_to_message_id=1)
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_video_url(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client.send_video(123, "https://example.com/video.mp4")
        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_chat_action(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        await client.send_chat_action(123)

    @pytest.mark.asyncio
    async def test_send_chat_action_error(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_error_response(400, "error"))
        await client.send_chat_action(123)

    @pytest.mark.asyncio
    async def test_get_file(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"file_path": "photos/file_0.jpg"}))
        result = await client.get_file("file123")
        assert result["file_path"] == "photos/file_0.jpg"

    @pytest.mark.asyncio
    async def test_download_file(self) -> None:
        client = _mock_client()
        resp = httpx.Response(200, content=b"file-content", request=httpx.Request("GET", "https://x"))
        client._http.get = AsyncMock(return_value=resp)
        data = await client.download_file("photos/file_0.jpg")
        assert data == b"file-content"

    @pytest.mark.asyncio
    async def test_download_voice_success(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"file_path": "voice/file_0.ogg"}))
        resp = httpx.Response(200, content=b"ogg-data", request=httpx.Request("GET", "https://x"))
        client._http.get = AsyncMock(return_value=resp)

        path = await client.download_voice("fid")
        assert path is not None
        assert path.suffix == ".ogg"
        path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_voice_no_path(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({}))
        assert await client.download_voice("fid") is None

    @pytest.mark.asyncio
    async def test_download_voice_error(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(side_effect=RuntimeError("network"))
        assert await client.download_voice("fid") is None


# ──────────────────────────────────────────────────────────────────
# Fallback / Transport Resilience
# ──────────────────────────────────────────────────────────────────


class TestFallbackInit:
    """Verify __init__ builds correct base-URL chains."""

    def test_default_builds_fallback_chain(self) -> None:
        client = TelegramClient("tok")
        assert len(client._api_bases) == 1 + len(_FALLBACK_IPS)
        assert "api.telegram.org" in client._api_bases[0]
        for ip in _FALLBACK_IPS:
            assert any(ip in b for b in client._api_bases[1:])

    def test_custom_api_base_single_entry(self) -> None:
        client = TelegramClient("tok", api_base="https://proxy.local")
        assert len(client._api_bases) == 1
        assert "proxy.local" in client._api_bases[0]

    def test_file_bases_match_api_bases_length(self) -> None:
        client = TelegramClient("tok")
        assert len(client._file_bases) == len(client._api_bases)

    def test_active_idx_starts_zero(self) -> None:
        assert TelegramClient("tok")._active_idx == 0


class TestFallbackCall:
    """Verify _call cycles through endpoints on network errors."""

    @pytest.mark.asyncio
    async def test_network_error_triggers_fallback(self) -> None:
        """First endpoint fails → client tries second and succeeds."""
        client = _mock_client()
        client._http.post = AsyncMock(
            side_effect=[httpx.ConnectError("dns fail"), _ok_response({"id": 1})],
        )
        result = await client._call("getMe")
        assert result["id"] == 1
        assert client._active_idx == 1

    @pytest.mark.asyncio
    async def test_sticky_on_success(self) -> None:
        """After fallback succeeds, subsequent calls start from that idx."""
        client = _mock_client()
        client._http.post = AsyncMock(
            side_effect=[httpx.ConnectTimeout("t"), _ok_response({"a": 1})],
        )
        await client._call("getMe")
        assert client._active_idx == 1

        client._http.post = AsyncMock(return_value=_ok_response({"b": 2}))
        result = await client._call("getMe")
        assert result["b"] == 2
        assert client._active_idx == 1

    @pytest.mark.asyncio
    async def test_all_endpoints_fail_raises_last(self) -> None:
        """All endpoints fail → raises the last network error."""
        client = _mock_client()
        n = len(client._api_bases)
        client._http.post = AsyncMock(
            side_effect=[httpx.ConnectError(f"fail-{i}") for i in range(n)],
        )
        with pytest.raises(httpx.ConnectError, match=f"fail-{n - 1}"):
            await client._call("getMe")

    @pytest.mark.asyncio
    async def test_business_error_no_fallback(self) -> None:
        """TelegramApiError is raised immediately without trying fallback."""
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_error_response(400, "Bad Request"))
        with pytest.raises(TelegramApiError, match="Bad Request"):
            await client._call("getMe")
        assert client._http.post.call_count == 1
        assert client._active_idx == 0

    @pytest.mark.asyncio
    async def test_custom_base_no_fallback_on_network_error(self) -> None:
        """Custom api_base has only 1 endpoint — no fallback available."""
        client = TelegramClient("tok", api_base="https://proxy.local")
        mock_http = AsyncMock(spec=httpx.AsyncClient)
        mock_http.is_closed = False
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("down"))
        client._http = mock_http

        with pytest.raises(httpx.ConnectError, match="down"):
            await client._call("getMe")
        assert mock_http.post.call_count == 1


class TestHostHeader:
    """Verify Host header is set only for IP-based fallback endpoints."""

    def test_host_header_for_fallback_ip(self) -> None:
        client = TelegramClient("tok")
        assert client._host_headers(0) == {}
        assert client._host_headers(1) == {"Host": _API_HOST}
        assert client._host_headers(2) == {"Host": _API_HOST}

    def test_host_header_single_base(self) -> None:
        client = TelegramClient("tok", api_base="https://proxy.local")
        assert client._host_headers(0) == {}

    @pytest.mark.asyncio
    async def test_fallback_call_sends_host_header(self) -> None:
        """When falling back to IP endpoint, Host header must be present."""
        client = _mock_client()
        client._http.post = AsyncMock(
            side_effect=[httpx.ConnectError("dns"), _ok_response({"ok": True})],
        )
        await client._call("getMe")

        second_call = client._http.post.call_args_list[1]
        assert second_call.kwargs.get("headers", {}).get("Host") == _API_HOST

    @pytest.mark.asyncio
    async def test_download_file_host_header_on_fallback(self) -> None:
        """download_file uses Host header when active endpoint is a fallback IP."""
        client = _mock_client()
        client._active_idx = 1
        resp = httpx.Response(200, content=b"data", request=httpx.Request("GET", "https://x"))
        client._http.get = AsyncMock(return_value=resp)

        await client.download_file("photos/f.jpg")
        get_call = client._http.get.call_args
        assert get_call.kwargs.get("headers", {}).get("Host") == _API_HOST

    @pytest.mark.asyncio
    async def test_download_file_no_host_header_official(self) -> None:
        """download_file omits Host header when using official endpoint."""
        client = _mock_client()
        client._active_idx = 0
        resp = httpx.Response(200, content=b"data", request=httpx.Request("GET", "https://x"))
        client._http.get = AsyncMock(return_value=resp)

        await client.download_file("photos/f.jpg")
        get_call = client._http.get.call_args
        assert get_call.kwargs.get("headers", {}) == {}


class TestSendMedia:
    """Verify _send_media helper delegates correctly."""

    @pytest.mark.asyncio
    async def test_send_media_bytes_uses_files(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client._send_media(
            "sendPhoto",
            "photo",
            123,
            b"img",
            filename="p.jpg",
            mime_type="image/jpeg",
        )
        assert result["message_id"] == 1
        post_call = client._http.post.call_args
        assert "files" in post_call.kwargs or (len(post_call.args) > 1)

    @pytest.mark.asyncio
    async def test_send_media_url_uses_json(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 2}))
        result = await client._send_media(
            "sendPhoto",
            "photo",
            123,
            "https://example.com/p.jpg",
            filename="p.jpg",
            mime_type="image/jpeg",
        )
        assert result["message_id"] == 2


class TestVoiceAudioSizeValidation:
    """Test size validation and MIME type checks for voice/audio methods."""

    @pytest.mark.asyncio
    async def test_send_voice_normal_size(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        voice_data = b"ogg_data" * 100  # Small voice file
        result = await client.send_voice(123, voice_data, filename="v.ogg")

        assert result["message_id"] == 1
        assert client._http.post.called

    @pytest.mark.asyncio
    async def test_send_voice_oversized_raises(self) -> None:
        from app.channels.providers.telegram.exceptions import (
            VoiceMessageTooLargeError,
        )

        client = _mock_client()

        voice_data = b"x" * (51 * 1024 * 1024)  # 51MB > 50MB limit

        with pytest.raises(VoiceMessageTooLargeError) as exc_info:
            await client.send_voice(123, voice_data, filename="big.ogg")

        assert exc_info.value.actual_size == len(voice_data)
        assert exc_info.value.max_size == 50 * 1024 * 1024
        assert "Voice message" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_voice_invalid_mime_type_raises(self) -> None:
        client = _mock_client()

        with pytest.raises(ValueError) as exc_info:
            await client.send_voice(123, b"data", mime_type="audio/mpeg")  # MP3 not supported

        assert "Unsupported MIME type for sendVoice" in str(exc_info.value)
        assert "send_audio()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_voice_opus_mime_type(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        result = await client.send_voice(123, b"opus_data", mime_type="audio/opus")

        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_normal_size(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        audio_data = b"mp3_data" * 100
        result = await client.send_audio(123, audio_data, filename="song.mp3")

        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_oversized_raises(self) -> None:
        from app.channels.providers.telegram.exceptions import (
            AudioFileTooLargeError,
        )

        client = _mock_client()

        audio_data = b"x" * (51 * 1024 * 1024)  # 51MB

        with pytest.raises(AudioFileTooLargeError) as exc_info:
            await client.send_audio(123, audio_data)

        assert exc_info.value.actual_size == len(audio_data)
        assert "Audio file" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_audio_invalid_mime_type_raises(self) -> None:
        client = _mock_client()

        with pytest.raises(ValueError) as exc_info:
            await client.send_audio(123, b"data", mime_type="audio/ogg")  # OGG not supported

        assert "Unsupported MIME type for sendAudio" in str(exc_info.value)
        assert "send_voice()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_audio_m4a_mime_type(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        result = await client.send_audio(123, b"m4a_data", mime_type="audio/m4a")

        assert result["message_id"] == 1


class TestGetRecommendedSendMethod:
    """Test the get_recommended_send_method helper function."""

    def test_voice_ogg_small(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/ogg", size=1_000_000) == "send_voice"

    def test_voice_opus_small(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/opus", size=5_000_000) == "send_voice"

    def test_voice_oversized(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/ogg", size=60_000_000) == "send_document"

    def test_audio_mp3(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/mpeg", size=10_000_000) == "send_audio"

    def test_audio_m4a(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/m4a", size=5_000_000) == "send_audio"

    def test_audio_oversized(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/mpeg", size=60_000_000) == "send_document"

    def test_unknown_mime_type(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/wav", size=1_000_000) == "send_document"

    def test_no_size_provided(self) -> None:
        from app.channels.providers.telegram.api import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/ogg") == "send_voice"
        assert get_recommended_send_method("audio/mpeg") == "send_audio"


# ──────────────────────────────────────────────────────────────────
# Forum Topic API methods (Bot API 6.3+)
# ──────────────────────────────────────────────────────────────────


class TestForumTopicApi:
    """Test the 5 Forum Topic API methods on TelegramClient."""

    @pytest.mark.asyncio
    async def test_create_forum_topic(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_thread_id": 42, "name": "Test Topic"}))
        result = await client.create_forum_topic(-100123, "Test Topic", icon_color=0x6FB9F0)
        assert result["message_thread_id"] == 42
        assert result["name"] == "Test Topic"

    @pytest.mark.asyncio
    async def test_create_forum_topic_with_emoji(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response({"message_thread_id": 43, "name": "Dev"}))
        result = await client.create_forum_topic(-100123, "Dev", icon_custom_emoji_id="5368324170671202286")
        assert result["message_thread_id"] == 43

    @pytest.mark.asyncio
    async def test_edit_forum_topic(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        result = await client.edit_forum_topic(-100123, 42, name="Renamed")
        assert result is True

    @pytest.mark.asyncio
    async def test_edit_forum_topic_icon_only(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        result = await client.edit_forum_topic(-100123, 42, icon_custom_emoji_id="5368324170671202286")
        assert result is True

    @pytest.mark.asyncio
    async def test_close_forum_topic(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.close_forum_topic(-100123, 42) is True

    @pytest.mark.asyncio
    async def test_reopen_forum_topic(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.reopen_forum_topic(-100123, 42) is True

    @pytest.mark.asyncio
    async def test_delete_forum_topic(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.delete_forum_topic(-100123, 42) is True

    @pytest.mark.asyncio
    async def test_create_forum_topic_permission_error(self) -> None:
        client = _mock_client()
        client._http.post = AsyncMock(return_value=_error_response(403, "Forbidden: not enough rights"))
        with pytest.raises(TelegramApiError, match="not enough rights"):
            await client.create_forum_topic(-100123, "Forbidden Topic")
