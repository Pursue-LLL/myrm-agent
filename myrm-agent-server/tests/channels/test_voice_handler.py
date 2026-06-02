"""Tests for voice handler (handler.py), TTS (tts.py), and STT (stt.py) modules.

Covers pure functions, TTS mode logic, directive parsing, provider dispatch,
and STT transcription with mocked external APIs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    STTResult,
    TTSMode,
    VoiceConfig,
)
from app.channels.voice.handler import (
    download_inbound_audio,
    has_audio_attachment,
    maybe_tts,
    parse_tts_directives,
    strip_tts_tags,
    transcribe_inbound,
)


def _msg(
    content: str = "hello",
    media: tuple[MediaAttachment, ...] = (),
    channel: str = "test",
    metadata: dict[str, object] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id="user-1",
        content=content,
        chat_id="chat-1",
        media=media,
        metadata=metadata or {},
    )


def _outbound(content: str = "reply") -> OutboundMessage:
    return OutboundMessage(channel="test", recipient_id="chat-1", content=content, user_id="u1")


def _voice_config(**overrides: object) -> VoiceConfig:
    defaults: dict[str, object] = {
        "stt_enabled": True,
        "stt_provider": "openai",
        "stt_api_key": "test-key",
        "tts_mode": TTSMode.ALWAYS,
        "tts_provider": "edge",
        "tts_api_key": "test-key",
        "tts_max_length": 4000,
    }
    defaults.update(overrides)
    return VoiceConfig(**defaults)  # type: ignore[arg-type]


def _audio_attachment(url: str | None = None, path: str | None = None) -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.AUDIO, url=url, path=path)


# ══════════════════════════════════════════════════════════════════════
# handler.py — Pure Functions
# ══════════════════════════════════════════════════════════════════════


class TestHasAudioAttachment:
    def test_no_media(self) -> None:
        assert has_audio_attachment(_msg()) is False

    def test_image_only(self) -> None:
        img = MediaAttachment(media_type=MediaType.IMAGE, url="https://x.com/img.png")
        assert has_audio_attachment(_msg(media=(img,))) is False

    def test_audio_present(self) -> None:
        assert has_audio_attachment(_msg(media=(_audio_attachment(url="https://x.com/a.mp3"),))) is True

    def test_mixed_media(self) -> None:
        img = MediaAttachment(media_type=MediaType.IMAGE, url="https://x.com/img.png")
        audio = _audio_attachment(url="https://x.com/a.mp3")
        assert has_audio_attachment(_msg(media=(img, audio))) is True


class TestParseTtsDirectives:
    def test_no_directives(self) -> None:
        directives, text_block = parse_tts_directives("Hello world")
        assert directives == {}
        assert text_block is None

    def test_off_directive(self) -> None:
        directives, _ = parse_tts_directives("Hello [[tts:off]] world")
        assert directives == {"off": "true"}

    def test_voice_directive(self) -> None:
        directives, _ = parse_tts_directives("Hello [[tts:voice=nova]] world")
        assert directives["voice"] == "nova"

    def test_provider_directive(self) -> None:
        directives, _ = parse_tts_directives("Hello [[tts:provider=openai]] world")
        assert directives["provider"] == "openai"

    def test_multiple_directives(self) -> None:
        directives, _ = parse_tts_directives("Hello [[tts:voice=nova provider=openai]] world")
        assert directives["voice"] == "nova"
        assert directives["provider"] == "openai"

    def test_text_block(self) -> None:
        _, text_block = parse_tts_directives("Hello [[tts:text]]Custom speech[[/tts:text]] world")
        assert text_block == "Custom speech"

    def test_text_block_multiline(self) -> None:
        _, text_block = parse_tts_directives("Start [[tts:text]]Line1\nLine2[[/tts:text]] end")
        assert text_block == "Line1\nLine2"


class TestStripTtsTags:
    def test_no_tags(self) -> None:
        assert strip_tts_tags("Hello world") == "Hello world"

    def test_strip_directive(self) -> None:
        assert strip_tts_tags("Hello [[tts:off]] world") == "Hello  world"

    def test_strip_text_block(self) -> None:
        result = strip_tts_tags("Hello [[tts:text]]hidden[[/tts:text]] world")
        assert "hidden" not in result
        assert "Hello" in result

    def test_strip_all(self) -> None:
        result = strip_tts_tags("[[tts:voice=nova]] Hi [[tts:text]]speech[[/tts:text]]")
        assert result == "Hi"


# ══════════════════════════════════════════════════════════════════════
# handler.py — maybe_tts
# ══════════════════════════════════════════════════════════════════════


class TestMaybeTts:
    @pytest.mark.asyncio
    async def test_tts_off_returns_original(self) -> None:
        config = _voice_config(tts_mode=TTSMode.OFF)
        result = await maybe_tts(_outbound(), True, config)
        assert result.content == "reply"

    @pytest.mark.asyncio
    async def test_no_config_returns_original(self) -> None:
        result = await maybe_tts(_outbound(), True, None)
        assert result.content == "reply"

    @pytest.mark.asyncio
    async def test_inbound_mode_no_voice_returns_original(self) -> None:
        config = _voice_config(tts_mode=TTSMode.INBOUND)
        result = await maybe_tts(_outbound(), False, config)
        assert result.content == "reply"

    @pytest.mark.asyncio
    async def test_empty_content_returns_original(self) -> None:
        config = _voice_config(tts_mode=TTSMode.ALWAYS)
        result = await maybe_tts(_outbound(content=""), True, config)
        assert result.content == ""

    @pytest.mark.asyncio
    async def test_tts_off_directive_strips_tags(self) -> None:
        config = _voice_config(tts_mode=TTSMode.ALWAYS)
        result = await maybe_tts(_outbound(content="Hello [[tts:off]] world"), True, config)
        assert "[[tts:" not in result.content

    @pytest.mark.asyncio
    async def test_successful_synthesis_adds_audio(self) -> None:
        config = _voice_config(tts_mode=TTSMode.ALWAYS)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"fake audio data")
        tmp.close()
        audio_path = Path(tmp.name)
        try:
            with patch(
                "app.channels.voice.tts.synthesize",
                new_callable=AsyncMock,
                return_value=audio_path,
            ):
                result = await maybe_tts(_outbound(content="Hello world test"), True, config)
                assert any(a.media_type == MediaType.AUDIO for a in result.media)
        finally:
            audio_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_synthesis_failure_returns_clean_content(self) -> None:
        config = _voice_config(tts_mode=TTSMode.ALWAYS)
        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await maybe_tts(_outbound(content="Hello world test"), True, config)
            assert len(result.media) == 0

    @pytest.mark.asyncio
    async def test_voice_override_from_directive(self) -> None:
        config = _voice_config(tts_mode=TTSMode.ALWAYS)
        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_synth:
            await maybe_tts(_outbound(content="Hello [[tts:voice=nova]] world test"), True, config)
            called_config: VoiceConfig = mock_synth.call_args[1].get("config") or mock_synth.call_args[0][1]
            assert called_config.tts_voice == "nova"

    @pytest.mark.asyncio
    async def test_tts_text_block_used_for_synthesis(self) -> None:
        config = _voice_config(tts_mode=TTSMode.ALWAYS)
        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_synth:
            await maybe_tts(
                _outbound(content="Display text [[tts:text]]Speech only text here[[/tts:text]]"),
                True,
                config,
            )
            tts_input = mock_synth.call_args[0][0]
            assert tts_input == "Speech only text here"


# ══════════════════════════════════════════════════════════════════════
# handler.py — transcribe_inbound
# ══════════════════════════════════════════════════════════════════════


class TestTranscribeInbound:
    @pytest.mark.asyncio
    async def test_no_config_returns_original(self) -> None:
        result = await transcribe_inbound(_msg(), None, MagicMock())
        assert result.content == "hello"

    @pytest.mark.asyncio
    async def test_stt_disabled_returns_original(self) -> None:
        config = _voice_config(stt_enabled=False)
        result = await transcribe_inbound(_msg(), config, MagicMock())
        assert result.content == "hello"

    @pytest.mark.asyncio
    async def test_no_audio_returns_original(self) -> None:
        config = _voice_config()
        with patch(
            "app.channels.voice.handler.download_inbound_audio",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await transcribe_inbound(_msg(), config, MagicMock())
            assert result.content == "hello"

    @pytest.mark.asyncio
    async def test_successful_transcription(self) -> None:
        config = _voice_config()
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"fake audio")
        tmp.close()
        audio_path = Path(tmp.name)

        stt_result = STTResult(text="transcribed text", language="en")
        msg = _msg(content="", media=(_audio_attachment(path=str(audio_path)),))
        with patch(
            "app.channels.voice.stt.transcribe",
            new_callable=AsyncMock,
            return_value=stt_result,
        ):
            result = await transcribe_inbound(msg, config, lambda _: MagicMock())
            assert "transcribed text" in result.content
            assert "" in result.content

    @pytest.mark.asyncio
    async def test_empty_transcription_returns_original(self) -> None:
        config = _voice_config()
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"fake audio")
        tmp.close()
        audio_path = Path(tmp.name)

        msg = _msg(media=(_audio_attachment(path=str(audio_path)),))
        with patch(
            "app.channels.voice.stt.transcribe",
            new_callable=AsyncMock,
            return_value=STTResult(text=""),
        ):
            result = await transcribe_inbound(msg, config, lambda _: MagicMock())
            assert result.content == "hello"


# ══════════════════════════════════════════════════════════════════════
# handler.py — download_inbound_audio
# ══════════════════════════════════════════════════════════════════════


class TestDownloadInboundAudio:
    @pytest.mark.asyncio
    async def test_no_channel_returns_none(self) -> None:
        result = await download_inbound_audio(_msg(), lambda _: None)
        assert result is None

    @pytest.mark.asyncio
    async def test_whatsapp_voice_message(self) -> None:
        ch = MagicMock()
        ch.download_voice_message = AsyncMock(return_value=Path("/tmp/voice.ogg"))
        msg = _msg(channel="whatsapp", metadata={"voice_message_id": "wamid123"})
        result = await download_inbound_audio(msg, lambda _: ch)
        assert result == Path("/tmp/voice.ogg")

    @pytest.mark.asyncio
    async def test_telegram_voice_file(self) -> None:
        ch = MagicMock()
        ch.download_voice_message = AsyncMock(return_value=Path("/tmp/voice.ogg"))
        msg = _msg(channel="telegram", metadata={"voice_file_id": "file123"})
        result = await download_inbound_audio(msg, lambda _: ch)
        assert result == Path("/tmp/voice.ogg")

    @pytest.mark.asyncio
    async def test_audio_attachment_with_path(self) -> None:
        audio = _audio_attachment(path="/tmp/local.mp3")
        msg = _msg(media=(audio,))
        ch = MagicMock()
        result = await download_inbound_audio(msg, lambda _: ch)
        assert result == Path("/tmp/local.mp3")

    @pytest.mark.asyncio
    async def test_audio_attachment_with_url(self) -> None:
        audio = _audio_attachment(url="https://example.com/audio.mp3")
        msg = _msg(media=(audio,))
        ch = MagicMock()
        with patch(
            "app.channels.voice.stt.download_audio",
            new_callable=AsyncMock,
            return_value=Path("/tmp/downloaded.mp3"),
        ):
            result = await download_inbound_audio(msg, lambda _: ch)
            assert result == Path("/tmp/downloaded.mp3")


# ══════════════════════════════════════════════════════════════════════
# tts.py Tests
# ══════════════════════════════════════════════════════════════════════


class TestTtsSynthesize:
    @pytest.mark.asyncio
    async def test_short_text_returns_none(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config()
        result = await synthesize("Hi", config)
        assert result is None

    @pytest.mark.asyncio
    async def test_long_text_returns_none(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config(tts_max_length=50)
        result = await synthesize("x" * 100, config)
        assert result is None

    @pytest.mark.asyncio
    async def test_edge_provider_dispatch(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config(tts_provider="edge")
        with patch(
            "app.channels.voice.tts._synthesize_edge",
            new_callable=AsyncMock,
            return_value=Path("/tmp/edge.mp3"),
        ) as mock_edge:
            result = await synthesize("Hello world test text", config)
            assert result == Path("/tmp/edge.mp3")
            mock_edge.assert_called_once()

    @pytest.mark.asyncio
    async def test_api_provider_dispatch(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config(tts_provider="openai")
        with patch(
            "app.channels.voice.tts._synthesize_api",
            new_callable=AsyncMock,
            return_value=Path("/tmp/openai.mp3"),
        ) as mock_api:
            result = await synthesize("Hello world test text", config)
            assert result == Path("/tmp/openai.mp3")
            mock_api.assert_called_once()

    @pytest.mark.asyncio
    async def test_primary_failure_falls_back_to_edge(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config(tts_provider="openai")
        with (
            patch(
                "app.channels.voice.tts._synthesize_api",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
            patch(
                "app.channels.voice.tts._synthesize_edge",
                new_callable=AsyncMock,
                return_value=Path("/tmp/fallback.mp3"),
            ) as mock_edge,
        ):
            result = await synthesize("Hello world test text", config)
            assert result == Path("/tmp/fallback.mp3")
            mock_edge.assert_called_once()

    @pytest.mark.asyncio
    async def test_edge_failure_no_double_fallback(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config(tts_provider="edge")
        with patch(
            "app.channels.voice.tts._synthesize_edge",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Edge down"),
        ):
            result = await synthesize("Hello world test text", config)
            assert result is None

    @pytest.mark.asyncio
    async def test_both_fail_returns_none(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config(tts_provider="openai")
        with (
            patch(
                "app.channels.voice.tts._synthesize_api",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
            patch(
                "app.channels.voice.tts._synthesize_edge",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Edge down"),
            ),
        ):
            result = await synthesize("Hello world test text", config)
            assert result is None

    @pytest.mark.asyncio
    async def test_summary_triggered_for_long_text(self) -> None:
        from app.channels.voice.tts import synthesize

        config = _voice_config(
            tts_provider="edge",
            tts_summary_enabled=True,
            tts_summary_threshold=20,
        )
        with (
            patch(
                "app.channels.voice.tts._summarize_for_tts",
                new_callable=AsyncMock,
                return_value="short summary",
            ) as mock_summary,
            patch(
                "app.channels.voice.tts._synthesize_edge",
                new_callable=AsyncMock,
                return_value=Path("/tmp/edge.mp3"),
            ) as mock_edge,
        ):
            await synthesize("A" * 100, config)
            mock_summary.assert_called_once()
            called_text = mock_edge.call_args[0][0]
            assert called_text == "short summary"


class TestTtsRequestBuilders:
    def test_openai_request(self) -> None:
        from app.channels.voice.tts import _openai_request

        config = _voice_config(tts_api_key="sk-test", tts_voice="nova")
        url, headers, body = _openai_request(config, "Hello", "mp3")
        assert "/audio/speech" in url
        assert "Bearer sk-test" in headers["Authorization"]
        assert body["voice"] == "nova"

    def test_openai_custom_base_url(self) -> None:
        from app.channels.voice.tts import _openai_request

        config = _voice_config(tts_api_key="sk-test", tts_base_url="https://custom.api.com/v1/")
        url, _, _ = _openai_request(config, "Hello", "mp3")
        assert url.startswith("https://custom.api.com/v1")

    def test_elevenlabs_request(self) -> None:
        from app.channels.voice.tts import _elevenlabs_request

        config = _voice_config(tts_api_key="el-test")
        url, headers, params, body = _elevenlabs_request(config, "Hello", stream=False)
        assert "text-to-speech" in url
        assert headers["xi-api-key"] == "el-test"

    def test_fish_audio_request(self) -> None:
        from app.channels.voice.tts import _fish_audio_request

        config = _voice_config(tts_api_key="fa-test")
        url, headers, body = _fish_audio_request(config, "Hello", "mp3")
        assert "/tts" in url
        assert body["format"] == "mp3"

    def test_minimax_request(self) -> None:
        from app.channels.voice.tts import _minimax_request

        config = _voice_config(tts_api_key="mm-test")
        url, headers, body = _minimax_request(config, "Hello", stream=False)
        assert "/t2a_v2" in url
        assert body["model"] == "speech-2.8-hd"

    def test_resolve_base_url_openai_custom(self) -> None:
        from app.channels.voice.tts import _resolve_base_url

        config = _voice_config(tts_base_url="https://custom.com/v1/")
        assert _resolve_base_url(config, "openai") == "https://custom.com/v1"

    def test_resolve_base_url_non_openai_ignores_custom(self) -> None:
        from app.channels.voice.tts import _resolve_base_url

        config = _voice_config(tts_base_url="https://custom.com/v1/")
        assert _resolve_base_url(config, "elevenlabs") == "https://api.elevenlabs.io"


class TestTtsWriteTemp:
    def test_write_temp(self) -> None:
        from app.channels.voice.tts import _write_temp

        path = _write_temp(b"test data", ".mp3")
        try:
            assert path.exists()
            assert path.read_bytes() == b"test data"
            assert path.suffix == ".mp3"
        finally:
            path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════
# stt.py Tests
# ══════════════════════════════════════════════════════════════════════


class TestSttTranscribe:
    @pytest.mark.asyncio
    async def test_missing_file_returns_none(self) -> None:
        from app.channels.voice.stt import transcribe

        result = await transcribe(Path("/nonexistent/audio.mp3"), _voice_config())
        assert result is None

    @pytest.mark.asyncio
    async def test_too_small_file_returns_none(self) -> None:
        from app.channels.voice.stt import transcribe

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"tiny")
        tmp.close()
        try:
            result = await transcribe(Path(tmp.name), _voice_config())
            assert result is None
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_too_large_file_returns_none(self) -> None:
        from app.channels.voice.stt import transcribe

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"x" * (26 * 1024 * 1024))
        tmp.close()
        try:
            result = await transcribe(Path(tmp.name), _voice_config())
            assert result is None
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_openai_provider_dispatch(self) -> None:
        from app.channels.voice.stt import transcribe

        config = _voice_config(stt_provider="openai")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"x" * 2048)
        tmp.close()
        try:
            with patch(
                "app.channels.voice.stt._transcribe_openai_compatible",
                new_callable=AsyncMock,
                return_value=STTResult(text="hello"),
            ) as mock_fn:
                result = await transcribe(Path(tmp.name), config)
                assert result is not None
                assert result.text == "hello"
                mock_fn.assert_called_once()
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_groq_provider_dispatch(self) -> None:
        from app.channels.voice.stt import transcribe

        config = _voice_config(stt_provider="groq")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"x" * 2048)
        tmp.close()
        try:
            with patch(
                "app.channels.voice.stt._transcribe_openai_compatible",
                new_callable=AsyncMock,
                return_value=STTResult(text="groq result"),
            ):
                result = await transcribe(Path(tmp.name), config)
                assert result is not None
                assert result.text == "groq result"
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_deepgram_provider_dispatch(self) -> None:
        from app.channels.voice.stt import transcribe

        config = _voice_config(stt_provider="deepgram")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"x" * 2048)
        tmp.close()
        try:
            with patch(
                "app.channels.voice.stt._transcribe_deepgram",
                new_callable=AsyncMock,
                return_value=STTResult(text="deepgram result"),
            ):
                result = await transcribe(Path(tmp.name), config)
                assert result is not None
                assert result.text == "deepgram result"
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_unknown_provider_falls_back_to_openai(self) -> None:
        from app.channels.voice.stt import transcribe

        config = _voice_config(stt_provider="unknown")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"x" * 2048)
        tmp.close()
        try:
            with patch(
                "app.channels.voice.stt._transcribe_openai_compatible",
                new_callable=AsyncMock,
                return_value=STTResult(text="fallback"),
            ):
                result = await transcribe(Path(tmp.name), config)
                assert result is not None
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_exception_returns_none(self) -> None:
        from app.channels.voice.stt import transcribe

        config = _voice_config(stt_provider="openai")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"x" * 2048)
        tmp.close()
        try:
            with patch(
                "app.channels.voice.stt._transcribe_openai_compatible",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ):
                result = await transcribe(Path(tmp.name), config)
                assert result is None
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class TestSttDownloadAudio:
    @pytest.mark.asyncio
    async def test_successful_download(self) -> None:
        from app.channels.voice.stt import download_audio

        mock_resp = MagicMock()
        mock_resp.content = b"audio data"
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"content-type": "audio/mpeg"}

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_resp)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            result = await download_audio("https://example.com/audio.mp3")
            assert result is not None
            try:
                assert result.exists()
                assert result.read_bytes() == b"audio data"
            finally:
                result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_failure_returns_none(self) -> None:
        from app.channels.voice.stt import download_audio

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=RuntimeError("network error"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            result = await download_audio("https://example.com/audio.mp3")
            assert result is None


class TestSttHelpers:
    def test_guess_extension_from_url(self) -> None:
        from app.channels.voice.stt import _guess_extension

        assert _guess_extension("https://x.com/audio.ogg", "") == ".ogg"
        assert _guess_extension("https://x.com/audio.wav", "") == ".wav"
        assert _guess_extension("https://x.com/audio.m4a", "") == ".m4a"

    def test_guess_extension_from_content_type(self) -> None:
        from app.channels.voice.stt import _guess_extension

        assert _guess_extension("https://x.com/audio", "audio/ogg") == ".ogg"
        assert _guess_extension("https://x.com/audio", "audio/wav") == ".wav"
        assert _guess_extension("https://x.com/audio", "audio/webm") == ".webm"

    def test_guess_extension_default(self) -> None:
        from app.channels.voice.stt import _guess_extension

        assert _guess_extension("https://x.com/audio", "unknown") == ".mp3"

    def test_guess_mime(self) -> None:
        from app.channels.voice.stt import _guess_mime

        assert _guess_mime(Path("audio.mp3")) == "audio/mpeg"
        assert _guess_mime(Path("audio.wav")) == "audio/wav"
        assert _guess_mime(Path("audio.ogg")) == "audio/ogg"
        assert _guess_mime(Path("audio.unknown")) == "audio/mpeg"
