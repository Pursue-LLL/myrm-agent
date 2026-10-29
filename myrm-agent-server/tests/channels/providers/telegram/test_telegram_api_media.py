"""Tests for providers/telegram/api_media.py — media sending and the recommended send method."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.channels.providers.telegram.telegram_client_mocks import _mock_client, _ok_response


class TestSendMedia:
    """Verify _send_media helper delegates correctly."""

    @pytest.mark.asyncio
    async def test_send_media_bytes_uses_files(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))
        result = await client._send_media(
            "sendPhoto",
            "photo",
            123,
            b"img",
            filename="p.jpg",
            mime_type="image/jpeg",
        )
        assert result["message_id"] == 1
        post_call = http.post.call_args
        assert "files" in post_call.kwargs or (len(post_call.args) > 1)

    @pytest.mark.asyncio
    async def test_send_media_url_uses_json(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_id": 2}))
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
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        voice_data = b"ogg_data" * 100  # Small voice file
        result = await client.send_voice(123, voice_data, filename="v.ogg")

        assert result["message_id"] == 1
        assert http.post.called

    @pytest.mark.asyncio
    async def test_send_voice_oversized_raises(self) -> None:
        from app.channels.providers.telegram.exceptions import (
            VoiceMessageTooLargeError,
        )

        client, http = _mock_client()

        voice_data = b"x" * (51 * 1024 * 1024)  # 51MB > 50MB limit

        with pytest.raises(VoiceMessageTooLargeError) as exc_info:
            await client.send_voice(123, voice_data, filename="big.ogg")

        assert exc_info.value.actual_size == len(voice_data)
        assert exc_info.value.max_size == 50 * 1024 * 1024
        assert "Voice message" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_voice_invalid_mime_type_raises(self) -> None:
        client, http = _mock_client()

        with pytest.raises(ValueError) as exc_info:
            await client.send_voice(123, b"data", mime_type="audio/mpeg")  # MP3 not supported

        assert "Unsupported MIME type for sendVoice" in str(exc_info.value)
        assert "send_audio()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_voice_opus_mime_type(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        result = await client.send_voice(123, b"opus_data", mime_type="audio/opus")

        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_normal_size(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        audio_data = b"mp3_data" * 100
        result = await client.send_audio(123, audio_data, filename="song.mp3")

        assert result["message_id"] == 1

    @pytest.mark.asyncio
    async def test_send_audio_oversized_raises(self) -> None:
        from app.channels.providers.telegram.exceptions import (
            AudioFileTooLargeError,
        )

        client, http = _mock_client()

        audio_data = b"x" * (51 * 1024 * 1024)  # 51MB

        with pytest.raises(AudioFileTooLargeError) as exc_info:
            await client.send_audio(123, audio_data)

        assert exc_info.value.actual_size == len(audio_data)
        assert "Audio file" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_audio_invalid_mime_type_raises(self) -> None:
        client, http = _mock_client()

        with pytest.raises(ValueError) as exc_info:
            await client.send_audio(123, b"data", mime_type="audio/ogg")  # OGG not supported

        assert "Unsupported MIME type for sendAudio" in str(exc_info.value)
        assert "send_voice()" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_audio_m4a_mime_type(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_id": 1}))

        result = await client.send_audio(123, b"m4a_data", mime_type="audio/m4a")

        assert result["message_id"] == 1


class TestGetRecommendedSendMethod:
    """Test the get_recommended_send_method helper function."""

    def test_voice_ogg_small(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/ogg", size=1_000_000) == "send_voice"

    def test_voice_opus_small(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/opus", size=5_000_000) == "send_voice"

    def test_voice_oversized(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/ogg", size=60_000_000) == "send_document"

    def test_audio_mp3(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/mpeg", size=10_000_000) == "send_audio"

    def test_audio_m4a(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/m4a", size=5_000_000) == "send_audio"

    def test_audio_oversized(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/mpeg", size=60_000_000) == "send_document"

    def test_unknown_mime_type(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/wav", size=1_000_000) == "send_document"

    def test_no_size_provided(self) -> None:
        from app.channels.providers.telegram.api_media import (
            get_recommended_send_method,
        )

        assert get_recommended_send_method("audio/ogg") == "send_voice"
        assert get_recommended_send_method("audio/mpeg") == "send_audio"
