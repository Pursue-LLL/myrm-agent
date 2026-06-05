"""Unit tests for voice STT/TTS integration via voice_handler module."""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import PairingStatus
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
    has_audio_attachment as _has_audio_attachment,
)
from app.channels.voice.handler import (
    maybe_tts,
    transcribe_inbound,
)
from app.channels.voice.handler import (
    parse_tts_directives as _parse_tts_directives,
)
from app.channels.voice.handler import (
    strip_tts_tags as _strip_tts_tags,
)


def _voice(
    stt_enabled: bool = True,
    tts_mode: TTSMode = TTSMode.OFF,
) -> VoiceConfig:
    return VoiceConfig(
        stt_enabled=stt_enabled,
        stt_provider="openai",
        stt_api_key="sk-test",
        tts_mode=tts_mode,
        tts_provider="edge",
    )


def _inbound(
    content: str = "hello",
    media: tuple[MediaAttachment, ...] = (),
    channel: str = "whatsapp",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id="user1",
        content=content,
        chat_id="chat1",
        is_group=False,
        mentioned=False,
        media=media,
    )


def _outbound(content: str = "Agent reply") -> OutboundMessage:
    return OutboundMessage(
        channel="whatsapp",
        recipient_id="user1",
        content=content,
        user_id="system",
    )


def _audio_attachment() -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.AUDIO, mime_type="audio/ogg")


# ---------------------------------------------------------------------------
# _has_audio_attachment()
# ---------------------------------------------------------------------------


class TestHasAudioAttachment:
    def test_true_for_audio(self) -> None:
        msg = _inbound(media=(_audio_attachment(),))
        assert _has_audio_attachment(msg) is True

    def test_false_for_no_media(self) -> None:
        msg = _inbound()
        assert _has_audio_attachment(msg) is False

    def test_false_for_non_audio(self) -> None:
        img = MediaAttachment(media_type=MediaType.IMAGE, mime_type="image/png")
        msg = _inbound(media=(img,))
        assert _has_audio_attachment(msg) is False


# ---------------------------------------------------------------------------
# _transcribe_voice()
# ---------------------------------------------------------------------------


class TestTranscribeVoice:
    @staticmethod
    def _get_channel_stub(_name: str) -> MagicMock:
        ch = MagicMock()
        ch.download_media = AsyncMock(return_value=None)
        return ch

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_stt_disabled(self) -> None:
        msg = _inbound(media=(_audio_attachment(),))
        result = await transcribe_inbound(msg, _voice(stt_enabled=False), self._get_channel_stub)
        assert result is msg

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_no_voice_config(self) -> None:
        msg = _inbound(media=(_audio_attachment(),))
        result = await transcribe_inbound(msg, None, self._get_channel_stub)
        assert result is msg

    @pytest.mark.asyncio
    async def test_injects_transcript_into_content(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        tmp.write(b"\x00" * 2048)
        tmp.close()
        audio_path = Path(tmp.name)

        msg = _inbound(
            content="",
            media=(_audio_attachment(),),
            channel="whatsapp",
        )
        msg = dataclasses.replace(msg, metadata={"voice_message_id": "msg123"})

        stt_result = STTResult(text="Transcribed text", language="en", duration=2.0)

        with (
            patch(
                "app.channels.voice.handler.download_inbound_audio",
                new_callable=AsyncMock,
                return_value=audio_path,
            ),
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=stt_result,
            ),
        ):
            result = await transcribe_inbound(msg, _voice(), self._get_channel_stub)

        assert "[ Voice] Transcribed text" in result.content
        assert not audio_path.exists()

    @pytest.mark.asyncio
    async def test_preserves_original_content(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        tmp.write(b"\x00" * 2048)
        tmp.close()
        audio_path = Path(tmp.name)

        msg = _inbound(
            content="caption text",
            media=(_audio_attachment(),),
        )
        msg = dataclasses.replace(msg, metadata={"voice_message_id": "msg123"})

        stt_result = STTResult(text="Voice content")

        with (
            patch(
                "app.channels.voice.handler.download_inbound_audio",
                new_callable=AsyncMock,
                return_value=audio_path,
            ),
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=stt_result,
            ),
        ):
            result = await transcribe_inbound(msg, _voice(), self._get_channel_stub)

        assert result.content.startswith("[ Voice] Voice content")
        assert "caption text" in result.content

    @pytest.mark.asyncio
    async def test_returns_unchanged_on_transcription_failure(self) -> None:
        msg = _inbound(media=(_audio_attachment(),))

        with patch(
            "app.channels.voice.handler.download_inbound_audio",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await transcribe_inbound(msg, _voice(), self._get_channel_stub)

        assert result is msg


# ---------------------------------------------------------------------------
# _maybe_tts()
# ---------------------------------------------------------------------------


class TestMaybeTTS:
    @pytest.mark.asyncio
    async def test_returns_unchanged_when_tts_off(self) -> None:
        result = await maybe_tts(_outbound(), inbound_had_voice=True, voice_config=_voice(tts_mode=TTSMode.OFF))
        assert result.media == ()

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_no_voice_config(self) -> None:
        result = await maybe_tts(_outbound(), inbound_had_voice=True, voice_config=None)
        assert result.media == ()

    @pytest.mark.asyncio
    async def test_inbound_mode_skips_when_no_voice(self) -> None:
        result = await maybe_tts(_outbound(), inbound_had_voice=False, voice_config=_voice(tts_mode=TTSMode.INBOUND))
        assert result.media == ()

    @pytest.mark.asyncio
    async def test_always_mode_synthesizes(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"\x00" * 1024)
        tmp.close()
        audio_path = Path(tmp.name)

        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=audio_path,
        ):
            result = await maybe_tts(_outbound(), inbound_had_voice=False, voice_config=_voice(tts_mode=TTSMode.ALWAYS))

        assert len(result.media) == 1
        assert result.media[0].media_type == MediaType.AUDIO
        assert result.media[0].path == str(audio_path)
        audio_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_inbound_mode_synthesizes_when_voice(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"\x00" * 1024)
        tmp.close()
        audio_path = Path(tmp.name)

        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=audio_path,
        ):
            result = await maybe_tts(_outbound(), inbound_had_voice=True, voice_config=_voice(tts_mode=TTSMode.INBOUND))

        assert len(result.media) == 1
        audio_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_returns_unchanged_on_synthesis_failure(self) -> None:
        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await maybe_tts(_outbound(), inbound_had_voice=False, voice_config=_voice(tts_mode=TTSMode.ALWAYS))

        assert result.media == ()

    @pytest.mark.asyncio
    async def test_skips_empty_content(self) -> None:
        out = _outbound(content="")
        result = await maybe_tts(out, inbound_had_voice=False, voice_config=_voice(tts_mode=TTSMode.ALWAYS))
        assert result.media == ()

    @pytest.mark.asyncio
    async def test_tts_off_directive_skips_synthesis(self) -> None:
        """[[tts:off]] directive should skip TTS and strip tags."""
        out = _outbound(content="Hello [[tts:off]] world")
        result = await maybe_tts(out, inbound_had_voice=False, voice_config=_voice(tts_mode=TTSMode.ALWAYS))
        assert result.media == ()
        assert "[[tts" not in result.content
        assert "Hello" in result.content

    @pytest.mark.asyncio
    async def test_tts_voice_override(self) -> None:
        """[[tts:voice=xxx]] should override the voice in synthesis."""
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"\x00" * 1024)
        tmp.close()
        audio_path = Path(tmp.name)

        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=audio_path,
        ) as mock_synth:
            out = _outbound(content="Hello [[tts:voice=nova]] world")
            result = await maybe_tts(out, inbound_had_voice=False, voice_config=_voice(tts_mode=TTSMode.ALWAYS))

        assert len(result.media) == 1
        assert "[[tts" not in result.content
        call_config = mock_synth.call_args[0][1]
        assert call_config.tts_voice == "nova"
        audio_path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_tts_text_block(self) -> None:
        """[[tts:text]]...[[/tts:text]] should use block content for TTS."""
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.write(b"\x00" * 1024)
        tmp.close()
        audio_path = Path(tmp.name)

        with patch(
            "app.channels.voice.tts.synthesize",
            new_callable=AsyncMock,
            return_value=audio_path,
        ) as mock_synth:
            out = _outbound(content="Full reply with details. [[tts:text]]Short summary for audio.[[/tts:text]]")
            result = await maybe_tts(out, inbound_had_voice=False, voice_config=_voice(tts_mode=TTSMode.ALWAYS))

        assert len(result.media) == 1
        assert "[[tts" not in result.content
        tts_input = mock_synth.call_args[0][0]
        assert tts_input == "Short summary for audio."
        audio_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# _parse_tts_directives()
# ---------------------------------------------------------------------------


class TestParseTTSDirectives:
    def test_empty_text(self) -> None:
        directives, text_block = _parse_tts_directives("")
        assert directives == {}
        assert text_block is None

    def test_no_directives(self) -> None:
        directives, text_block = _parse_tts_directives("Hello world")
        assert directives == {}
        assert text_block is None

    def test_off_directive(self) -> None:
        directives, _ = _parse_tts_directives("Hello [[tts:off]] world")
        assert directives == {"off": "true"}

    def test_voice_directive(self) -> None:
        directives, _ = _parse_tts_directives("Hello [[tts:voice=nova]] world")
        assert directives == {"voice": "nova"}

    def test_provider_directive(self) -> None:
        directives, _ = _parse_tts_directives("Hello [[tts:provider=openai]] world")
        assert directives == {"provider": "openai"}

    def test_multiple_directives(self) -> None:
        directives, _ = _parse_tts_directives("Hello [[tts:voice=nova]] [[tts:provider=openai]] world")
        assert directives == {"voice": "nova", "provider": "openai"}

    def test_text_block(self) -> None:
        _, text_block = _parse_tts_directives("Full reply. [[tts:text]]Short summary.[[/tts:text]]")
        assert text_block == "Short summary."

    def test_text_block_multiline(self) -> None:
        _, text_block = _parse_tts_directives("Full reply.\n[[tts:text]]Line one.\nLine two.[[/tts:text]]")
        assert text_block == "Line one.\nLine two."


# ---------------------------------------------------------------------------
# _strip_tts_tags()
# ---------------------------------------------------------------------------


class TestStripTTSTags:
    def test_no_tags(self) -> None:
        assert _strip_tts_tags("Hello world") == "Hello world"

    def test_strips_directive(self) -> None:
        result = _strip_tts_tags("Hello [[tts:voice=nova]] world")
        assert result == "Hello  world"

    def test_strips_text_block(self) -> None:
        result = _strip_tts_tags("Full reply. [[tts:text]]Short summary.[[/tts:text]]")
        assert result == "Full reply."

    def test_strips_off_directive(self) -> None:
        result = _strip_tts_tags("Hello [[tts:off]] world")
        assert result == "Hello  world"

    def test_strips_all_combined(self) -> None:
        result = _strip_tts_tags("Hello [[tts:voice=nova]] reply. [[tts:text]]Summary.[[/tts:text]]")
        assert result == "Hello  reply."


# ---------------------------------------------------------------------------
# AgentRouter._handle_merged — error reply source message after STT
# ---------------------------------------------------------------------------


class _StubPairingStore:
    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return None

    async def bind(self, channel: str, sender_id: str, user_id: str, *, status: PairingStatus = PairingStatus.ACTIVE) -> None:
        return None

    async def unbind(self, channel: str, sender_id: str) -> None:
        return None

    async def get_status(self, channel: str, sender_id: str) -> PairingStatus | None:
        return None


class TestRouterHandleMergedExecForError:
    @pytest.mark.asyncio
    async def test_error_reply_uses_post_stt_inbound_when_prepare_raises(self) -> None:
        """send_error_reply uses the inbound message produced after STT when prepare fails."""
        from app.channels.core.bus import MessageBus
        from app.channels.routing.router import AgentRouter

        bus = MessageBus()
        router = AgentRouter(
            bus,
            _StubPairingStore(),
            AsyncMock(),
            voice_config=_voice(),
        )
        original = dataclasses.replace(
            _inbound(content="", media=(_audio_attachment(),)),
            user_id="stt-user",
        )

        async def fake_transcribe(
            msg: InboundMessage,
            voice_config: VoiceConfig | None,
            get_channel_fn: object,
        ) -> InboundMessage:
            return dataclasses.replace(msg, content="[ Voice] transcript line")

        captured: list[tuple[InboundMessage, str | Exception]] = []

        async def capture_reply(inbound: InboundMessage, err: str | Exception) -> None:
            captured.append((inbound, err))

        router._prepare_execution_context = AsyncMock(side_effect=RuntimeError("prepare failed"))
        router._fx.send_error_reply = capture_reply

        with patch(
            "app.channels.routing.router.transcribe_inbound",
            new=fake_transcribe,
        ):
            await router._handle_merged(original)

        assert len(captured) == 1
        assert "[ Voice] transcript line" in captured[0][0].content
        assert "[ref:" in str(captured[0][1])
