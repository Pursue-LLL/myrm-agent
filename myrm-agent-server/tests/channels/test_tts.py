"""Unit tests for Text-to-Speech module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.types import TTSMode, VoiceConfig
from app.channels.voice.tts import (
    _write_temp,
    synthesize,
)


def _voice(
    provider: str = "openai",
    api_key: str = "sk-test",
    voice: str = "",
    max_length: int = 4000,
) -> VoiceConfig:
    return VoiceConfig(
        tts_mode=TTSMode.ALWAYS,
        tts_provider=provider,
        tts_api_key=api_key,
        tts_voice=voice,
        tts_max_length=max_length,
    )


# ---------------------------------------------------------------------------
# synthesize() — validation
# ---------------------------------------------------------------------------


class TestSynthesizeValidation:
    @pytest.mark.asyncio
    async def test_skips_short_text(self) -> None:
        result = await synthesize("Hi", _voice())
        assert result is None

    @pytest.mark.asyncio
    async def test_skips_long_text(self) -> None:
        result = await synthesize("x" * 5000, _voice(max_length=100))
        assert result is None


# ---------------------------------------------------------------------------
# synthesize() — OpenAI provider
# ---------------------------------------------------------------------------


class TestSynthesizeOpenAI:
    @pytest.mark.asyncio
    async def test_openai_success(self) -> None:
        audio_bytes = b"\xff\xfb\x90\x00" * 256

        mock_resp = httpx.Response(
            200,
            content=audio_bytes,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/speech"),
        )

        with patch("app.channels.voice.tts.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await synthesize("Hello, this is a test message.", _voice("openai"))

        assert result is not None
        assert result.exists()
        assert result.suffix == ".mp3"
        assert result.stat().st_size == len(audio_bytes)
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_openai_opus_format(self) -> None:
        audio_bytes = b"\x00" * 512

        mock_resp = httpx.Response(
            200,
            content=audio_bytes,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/speech"),
        )

        with patch("app.channels.voice.tts.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await synthesize(
                "Hello, this is a test message.",
                _voice("openai"),
                output_format="opus",
            )

        assert result is not None
        assert result.suffix == ".opus"
        result.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# synthesize() — ElevenLabs provider
# ---------------------------------------------------------------------------


class TestSynthesizeElevenLabs:
    @pytest.mark.asyncio
    async def test_elevenlabs_success(self) -> None:
        audio_bytes = b"\xff\xfb\x90\x00" * 256

        mock_resp = httpx.Response(
            200,
            content=audio_bytes,
            request=httpx.Request("POST", "https://api.elevenlabs.io/v1/text-to-speech/voice123"),
        )

        with patch("app.channels.voice.tts.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await synthesize(
                "Hello, this is a test message.",
                _voice("elevenlabs", voice="voice123"),
            )

        assert result is not None
        assert result.suffix == ".mp3"
        result.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# synthesize() — Edge TTS provider
# ---------------------------------------------------------------------------


class TestSynthesizeEdge:
    @pytest.mark.asyncio
    async def test_edge_success(self) -> None:
        mock_edge = MagicMock()
        mock_communicate = MagicMock()

        async def fake_save(path: str) -> None:
            Path(path).write_bytes(b"\x00" * 1024)

        mock_communicate.save = fake_save
        mock_edge.Communicate.return_value = mock_communicate

        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            result = await synthesize(
                "Hello, this is a test message.",
                _voice("edge"),
            )

        assert result is not None
        assert result.exists()
        assert result.suffix == ".mp3"
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_edge_empty_audio_raises(self) -> None:
        mock_edge = MagicMock()
        mock_communicate = MagicMock()

        async def fake_save(path: str) -> None:
            Path(path).write_bytes(b"\x00" * 10)

        mock_communicate.save = fake_save
        mock_edge.Communicate.return_value = mock_communicate

        with patch.dict("sys.modules", {"edge_tts": mock_edge}):
            result = await synthesize(
                "Hello, this is a test message.",
                _voice("edge"),
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_edge_not_installed_returns_none(self) -> None:
        with patch(
            "app.channels.voice.tts._import_edge_tts",
            side_effect=ImportError("edge-tts is not installed"),
        ):
            result = await synthesize(
                "Hello, this is a test message.",
                _voice("edge"),
            )
        assert result is None


# ---------------------------------------------------------------------------
# synthesize() — Fallback behavior
# ---------------------------------------------------------------------------


class TestSynthesizeFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_edge_on_openai_failure(self) -> None:
        mock_edge = MagicMock()
        mock_communicate = MagicMock()

        async def fake_save(path: str) -> None:
            Path(path).write_bytes(b"\x00" * 1024)

        mock_communicate.save = fake_save
        mock_edge.Communicate.return_value = mock_communicate

        with (
            patch("app.channels.voice.tts.httpx.AsyncClient") as mock_cls,
            patch.dict("sys.modules", {"edge_tts": mock_edge}),
        ):
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await synthesize(
                "Hello, this is a test message.",
                _voice("openai"),
            )

        assert result is not None
        assert result.exists()
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_openai_failure_without_edge_returns_none(self) -> None:
        with (
            patch("app.channels.voice.tts.httpx.AsyncClient") as mock_cls,
            patch("app.channels.voice.tts.is_edge_tts_available", return_value=False),
        ):
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await synthesize(
                "Hello, this is a test message.",
                _voice("openai"),
            )

        assert result is None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestSummarizeForTTS:
    """Tests for long text summarization before TTS."""

    @pytest.mark.asyncio
    async def test_summary_triggered_above_threshold(self) -> None:
        """Text above threshold triggers summarization."""
        long_text = "A" * 2000
        config = VoiceConfig(
            tts_mode=TTSMode.ALWAYS,
            tts_provider="edge",
            tts_summary_enabled=True,
            tts_summary_threshold=1500,
            tts_max_length=5000,
        )

        mock_edge = MagicMock()
        mock_communicate = MagicMock()

        async def fake_save(path: str) -> None:
            Path(path).write_bytes(b"\x00" * 1024)

        mock_communicate.save = fake_save
        mock_edge.Communicate.return_value = mock_communicate

        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Short summary."

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        with patch.dict("sys.modules", {"edge_tts": mock_edge, "litellm": mock_litellm}):
            result = await synthesize(long_text, config)

        assert result is not None
        mock_litellm.acompletion.assert_called_once()
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_summary_not_triggered_below_threshold(self) -> None:
        """Text below threshold skips summarization."""
        short_text = "A" * 100
        config = VoiceConfig(
            tts_mode=TTSMode.ALWAYS,
            tts_provider="edge",
            tts_summary_enabled=True,
            tts_summary_threshold=1500,
        )

        mock_edge = MagicMock()
        mock_communicate = MagicMock()

        async def fake_save(path: str) -> None:
            Path(path).write_bytes(b"\x00" * 1024)

        mock_communicate.save = fake_save
        mock_edge.Communicate.return_value = mock_communicate

        with (
            patch.dict("sys.modules", {"edge_tts": mock_edge}),
            patch(
                "app.channels.voice.tts._summarize_for_tts",
                new_callable=AsyncMock,
            ) as mock_summarize,
        ):
            result = await synthesize(short_text, config)

        assert result is not None
        mock_summarize.assert_not_called()
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_summary_disabled_skips(self) -> None:
        """Disabled summary skips even for long text."""
        long_text = "A" * 2000
        config = VoiceConfig(
            tts_mode=TTSMode.ALWAYS,
            tts_provider="edge",
            tts_summary_enabled=False,
            tts_summary_threshold=1500,
        )

        mock_edge = MagicMock()
        mock_communicate = MagicMock()

        async def fake_save(path: str) -> None:
            Path(path).write_bytes(b"\x00" * 1024)

        mock_communicate.save = fake_save
        mock_edge.Communicate.return_value = mock_communicate

        with (
            patch.dict("sys.modules", {"edge_tts": mock_edge}),
            patch(
                "app.channels.voice.tts._summarize_for_tts",
                new_callable=AsyncMock,
            ) as mock_summarize,
        ):
            result = await synthesize(long_text, config)

        assert result is not None
        mock_summarize.assert_not_called()
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_summary_failure_uses_original(self) -> None:
        """Summarization failure falls back to original text."""
        from app.channels.voice.tts import _summarize_for_tts

        config = VoiceConfig(
            tts_mode=TTSMode.ALWAYS,
            tts_provider="edge",
            tts_summary_enabled=True,
            tts_summary_threshold=100,
        )

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(side_effect=RuntimeError("API error"))

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            result = await _summarize_for_tts("A" * 200, config)

        assert result is None


class TestWriteTemp:
    def test_creates_file_with_correct_suffix(self) -> None:
        path = _write_temp(b"test data", ".mp3")
        assert path.exists()
        assert path.suffix == ".mp3"
        assert path.read_bytes() == b"test data"
        path.unlink(missing_ok=True)
