"""Unit tests for Speech-to-Text module."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.channels.types import VoiceConfig
from app.channels.voice.stt import (
    _guess_extension,
    _guess_mime,
    _LocalWhisperManager,
    download_audio,
    get_local_status,
    is_local_available,
    transcribe,
)


def _voice(
    provider: str = "openai",
    api_key: str = "sk-test",
    local_model: str = "base",
    local_device: str = "auto",
    local_compute_type: str = "auto",
) -> VoiceConfig:
    return VoiceConfig(
        stt_enabled=True,
        stt_provider=provider,
        stt_api_key=api_key,
        stt_local_model=local_model,
        stt_local_device=local_device,
        stt_local_compute_type=local_compute_type,
    )


@dataclass
class _FakeSegment:
    """Mimics faster_whisper TranscriptionSegment for testing."""

    text: str


@dataclass
class _FakeTranscriptionInfo:
    """Mimics faster_whisper TranscriptionInfo for testing."""

    language: str
    duration: float


def _audio_file(size: int = 8192, suffix: str = ".mp3") -> Path:
    """Create a temporary audio file with given size."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(b"\x00" * size)
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# transcribe() — validation
# ---------------------------------------------------------------------------


class TestTranscribeValidation:
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_file(self) -> None:
        result = await transcribe(Path("/nonexistent/audio.mp3"), _voice())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_tiny_file(self) -> None:
        path = _audio_file(size=512)
        try:
            result = await transcribe(path, _voice())
            assert result is None
        finally:
            path.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_returns_none_for_oversized_file(self) -> None:
        path = _audio_file(size=1024)
        try:
            with patch("app.channels.voice.stt._MAX_AUDIO_SIZE_BYTES", 512):
                result = await transcribe(path, _voice())
                assert result is None
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# transcribe() — OpenAI-compatible provider
# ---------------------------------------------------------------------------


class TestTranscribeOpenAI:
    @pytest.mark.asyncio
    async def test_openai_transcription_success(self) -> None:
        path = _audio_file()
        response_body = {"text": "Hello world", "language": "en", "duration": 2.5}

        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("openai"))
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration == 2.5

    @pytest.mark.asyncio
    async def test_groq_uses_correct_model(self) -> None:
        path = _audio_file()
        response_body = {"text": "Test", "language": "en"}

        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("groq"))
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Test"
        call_kwargs = mock_client.post.call_args
        assert "groq.com" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self) -> None:
        path = _audio_file()

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "500",
                request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
                response=httpx.Response(500),
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice())
            finally:
                path.unlink(missing_ok=True)

        assert result is None


# ---------------------------------------------------------------------------
# transcribe() — Deepgram provider
# ---------------------------------------------------------------------------


class TestTranscribeDeepgram:
    @pytest.mark.asyncio
    async def test_deepgram_transcription_success(self) -> None:
        path = _audio_file()
        response_body = {
            "results": {
                "channels": [
                    {
                        "alternatives": [{"transcript": "Deepgram test"}],
                    }
                ],
            },
            "metadata": {"language": "en", "duration": 3.0},
        }

        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.deepgram.com/v1/listen"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("deepgram"))
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Deepgram test"
        assert result.language == "en"


# ---------------------------------------------------------------------------
# download_audio()
# ---------------------------------------------------------------------------


class TestDownloadAudio:
    @pytest.mark.asyncio
    async def test_download_success(self) -> None:
        mock_resp = httpx.Response(
            200,
            content=b"\x00" * 1024,
            headers={"content-type": "audio/mpeg"},
            request=httpx.Request("GET", "https://example.com/voice.mp3"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await download_audio("https://example.com/voice.mp3")

        assert result is not None
        assert result.exists()
        assert result.suffix == ".mp3"
        result.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_download_failure_returns_none(self) -> None:
        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await download_audio("https://example.com/voice.mp3")

        assert result is None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestGuessExtension:
    def test_from_url_path(self) -> None:
        assert _guess_extension("https://cdn.example.com/file.ogg", "") == ".ogg"
        assert _guess_extension("https://cdn.example.com/file.wav", "") == ".wav"
        assert _guess_extension("https://cdn.example.com/file.m4a", "") == ".m4a"

    def test_from_content_type(self) -> None:
        assert _guess_extension("https://cdn.example.com/file", "audio/ogg") == ".ogg"
        assert _guess_extension("https://cdn.example.com/file", "audio/wav") == ".wav"
        assert _guess_extension("https://cdn.example.com/file", "audio/webm") == ".webm"

    def test_default_mp3(self) -> None:
        assert _guess_extension("https://cdn.example.com/file", "application/octet-stream") == ".mp3"


class TestGuessMime:
    def test_known_extensions(self) -> None:
        assert _guess_mime(Path("test.mp3")) == "audio/mpeg"
        assert _guess_mime(Path("test.ogg")) == "audio/ogg"
        assert _guess_mime(Path("test.wav")) == "audio/wav"
        assert _guess_mime(Path("test.m4a")) == "audio/mp4"

    def test_unknown_extension_defaults_to_mpeg(self) -> None:
        assert _guess_mime(Path("test.xyz")) == "audio/mpeg"


# ---------------------------------------------------------------------------
# Local Whisper provider
# ---------------------------------------------------------------------------


def _mock_whisper_model() -> MagicMock:
    """Create a mock WhisperModel that returns fake segments + info."""
    model = MagicMock()
    model.transcribe.return_value = (
        [_FakeSegment(text="Hello local"), _FakeSegment(text=" world")],
        _FakeTranscriptionInfo(language="en", duration=2.1),
    )
    return model


class TestTranscribeLocal:
    @pytest.mark.asyncio
    async def test_local_transcription_success(self) -> None:
        path = _audio_file()
        mock_model = _mock_whisper_model()

        with patch.object(
            _LocalWhisperManager, "get_model", new_callable=AsyncMock, return_value=mock_model
        ):
            try:
                result = await transcribe(path, _voice("local"))
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Hello local world"
        assert result.language == "en"
        assert result.duration == 2.1
        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs.kwargs.get("vad_filter") is True
        assert call_kwargs.kwargs.get("beam_size") == 5

    @pytest.mark.asyncio
    async def test_local_transcription_empty_text_raises(self) -> None:
        path = _audio_file()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [_FakeSegment(text="  "), _FakeSegment(text="")],
            _FakeTranscriptionInfo(language="en", duration=1.0),
        )

        with patch.object(
            _LocalWhisperManager, "get_model", new_callable=AsyncMock, return_value=mock_model
        ):
            try:
                result = await transcribe(path, _voice("local"))
            finally:
                path.unlink(missing_ok=True)

        # Empty text triggers fallback → no cloud key → returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_local_passes_language_config(self) -> None:
        path = _audio_file()
        mock_model = _mock_whisper_model()
        config = VoiceConfig(
            stt_enabled=True, stt_provider="local", stt_language="zh",
        )

        with patch.object(
            _LocalWhisperManager, "get_model", new_callable=AsyncMock, return_value=mock_model
        ):
            try:
                await transcribe(path, config)
            finally:
                path.unlink(missing_ok=True)

        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs.kwargs.get("language") == "zh"


# ---------------------------------------------------------------------------
# _LocalWhisperManager
# ---------------------------------------------------------------------------


class TestLocalWhisperManager:
    def test_resolve_device_auto_no_torch(self) -> None:
        mgr = _LocalWhisperManager()
        with patch.dict("sys.modules", {"torch": None}):
            assert mgr._resolve_device("auto") == "cpu"

    def test_resolve_device_explicit(self) -> None:
        mgr = _LocalWhisperManager()
        assert mgr._resolve_device("cuda") == "cuda"
        assert mgr._resolve_device("cpu") == "cpu"

    def test_resolve_compute_type_auto_cuda(self) -> None:
        mgr = _LocalWhisperManager()
        assert mgr._resolve_compute_type("auto", "cuda") == "float16"

    def test_resolve_compute_type_auto_cpu(self) -> None:
        mgr = _LocalWhisperManager()
        assert mgr._resolve_compute_type("auto", "cpu") == "int8"

    def test_resolve_compute_type_explicit(self) -> None:
        mgr = _LocalWhisperManager()
        assert mgr._resolve_compute_type("float32", "cpu") == "float32"

    def test_is_loaded_default_false(self) -> None:
        mgr = _LocalWhisperManager()
        assert mgr.is_loaded is False

    def test_current_config_empty_before_load(self) -> None:
        mgr = _LocalWhisperManager()
        config = mgr.current_config
        assert config["model_size"] == ""
        assert config["device"] == ""

    @pytest.mark.asyncio
    async def test_get_model_loads_and_caches(self) -> None:
        mgr = _LocalWhisperManager()
        mock_model = MagicMock()

        with patch(
            "app.channels.voice.stt.WhisperModel",
            return_value=mock_model,
            create=True,
        ), patch.dict("sys.modules", {"faster_whisper": SimpleNamespace(WhisperModel=lambda *a, **kw: mock_model)}):
            config = _voice("local", local_model="tiny", local_device="cpu", local_compute_type="int8")
            model = await mgr.get_model(config)
            assert model is mock_model
            assert mgr.is_loaded is True
            assert mgr.current_config["model_size"] == "tiny"
            assert mgr.current_config["device"] == "cpu"
            assert mgr.current_config["compute_type"] == "int8"


# ---------------------------------------------------------------------------
# is_local_available() / get_local_status()
# ---------------------------------------------------------------------------


class TestLocalAvailability:
    def test_is_local_available_when_installed(self) -> None:
        with patch.dict("sys.modules", {"faster_whisper": MagicMock()}):
            assert is_local_available() is True

    def test_is_local_available_when_not_installed(self) -> None:
        with patch.dict("sys.modules", {"faster_whisper": None}):
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(ImportError) if name == "faster_whisper" else __builtins__.__import__(name, *a, **kw),
            ):
                assert is_local_available() is False

    def test_get_local_status_not_loaded(self) -> None:
        with patch(
            "app.channels.voice.stt.is_local_available", return_value=False
        ), patch(
            "app.channels.voice.stt._whisper_manager"
        ) as mock_mgr:
            mock_mgr.is_loaded = False
            status = get_local_status()
            assert status["available"] is False
            assert status["model_loaded"] is False
            assert status["config"] is None


# ---------------------------------------------------------------------------
# transcribe() — audio_bytes path
# ---------------------------------------------------------------------------


class TestTranscribeAudioBytes:
    @pytest.mark.asyncio
    async def test_audio_bytes_too_small_returns_none(self) -> None:
        result = await transcribe(None, _voice(), audio_bytes=b"\x00" * 512)
        assert result is None

    @pytest.mark.asyncio
    async def test_audio_bytes_openai_success(self) -> None:
        audio_data = b"\x00" * 8192
        response_body = {"text": "Bytes transcribed", "language": "en", "duration": 1.5}
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await transcribe(None, _voice("openai"), audio_bytes=audio_data)

        assert result is not None
        assert result.text == "Bytes transcribed"

    @pytest.mark.asyncio
    async def test_audio_bytes_deepgram_success(self) -> None:
        audio_data = b"\x00" * 8192
        response_body = {
            "results": {
                "channels": [{"alternatives": [{"transcript": "Deepgram bytes"}]}],
            },
            "metadata": {"language": "en", "duration": 2.0},
        }
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.deepgram.com/v1/listen"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await transcribe(
                None, _voice("deepgram"), audio_bytes=audio_data
            )

        assert result is not None
        assert result.text == "Deepgram bytes"


# ---------------------------------------------------------------------------
# transcribe() — unknown provider fallback
# ---------------------------------------------------------------------------


class TestTranscribeUnknownProvider:
    @pytest.mark.asyncio
    async def test_unknown_provider_falls_back_to_openai_compatible(self) -> None:
        path = _audio_file()
        response_body = {"text": "Unknown handled", "language": "en"}
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(
                    path,
                    VoiceConfig(
                        stt_enabled=True,
                        stt_provider="some_unknown_provider",
                        stt_api_key="sk-test",
                    ),
                )
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Unknown handled"


# ---------------------------------------------------------------------------
# transcribe() — Deepgram edge cases
# ---------------------------------------------------------------------------


class TestDeepgramEdgeCases:
    @pytest.mark.asyncio
    async def test_deepgram_no_channels_returns_none(self) -> None:
        path = _audio_file()
        response_body = {"results": {"channels": []}, "metadata": {}}
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.deepgram.com/v1/listen"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("deepgram"))
            finally:
                path.unlink(missing_ok=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_deepgram_no_alternatives_returns_none(self) -> None:
        path = _audio_file()
        response_body = {
            "results": {"channels": [{"alternatives": []}]},
            "metadata": {},
        }
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.deepgram.com/v1/listen"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("deepgram"))
            finally:
                path.unlink(missing_ok=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_deepgram_empty_transcript_returns_none(self) -> None:
        path = _audio_file()
        response_body = {
            "results": {"channels": [{"alternatives": [{"transcript": "  "}]}]},
            "metadata": {},
        }
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.deepgram.com/v1/listen"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("deepgram"))
            finally:
                path.unlink(missing_ok=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_deepgram_with_language_param(self) -> None:
        path = _audio_file()
        response_body = {
            "results": {
                "channels": [{"alternatives": [{"transcript": "Hola mundo"}]}],
            },
            "metadata": {"language": "es", "duration": 1.0},
        }
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.deepgram.com/v1/listen"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            config = VoiceConfig(
                stt_enabled=True,
                stt_provider="deepgram",
                stt_api_key="dg-test",
                stt_language="es",
            )
            try:
                result = await transcribe(path, config)
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Hola mundo"


# ---------------------------------------------------------------------------
# OpenAI-compatible — language & empty transcript
# ---------------------------------------------------------------------------


class TestOpenAIEdgeCases:
    @pytest.mark.asyncio
    async def test_openai_with_language_config(self) -> None:
        path = _audio_file()
        response_body = {"text": "Bonjour", "language": "fr", "duration": 1.2}
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            config = VoiceConfig(
                stt_enabled=True,
                stt_provider="openai",
                stt_api_key="sk-test",
                stt_language="fr",
            )
            try:
                result = await transcribe(path, config)
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Bonjour"

    @pytest.mark.asyncio
    async def test_openai_empty_transcript_returns_none(self) -> None:
        path = _audio_file()
        response_body = {"text": "  ", "language": "en"}
        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("openai"))
            finally:
                path.unlink(missing_ok=True)

        assert result is None


# ---------------------------------------------------------------------------
# _LocalWhisperManager — model cache hit
# ---------------------------------------------------------------------------


class TestWhisperManagerCacheHit:
    @pytest.mark.asyncio
    async def test_cached_model_reused_on_same_config(self) -> None:
        mgr = _LocalWhisperManager()
        mock_model = MagicMock()

        with patch(
            "app.channels.voice.stt.WhisperModel",
            return_value=mock_model,
            create=True,
        ), patch.dict(
            "sys.modules",
            {"faster_whisper": SimpleNamespace(WhisperModel=lambda *a, **kw: mock_model)},
        ):
            config = _voice("local", local_model="tiny", local_device="cpu", local_compute_type="int8")
            model1 = await mgr.get_model(config)
            model2 = await mgr.get_model(config)
            assert model1 is model2
            assert model1 is mock_model


# ---------------------------------------------------------------------------
# _guess_extension — additional content types
# ---------------------------------------------------------------------------


class TestGuessExtensionContentType:
    def test_mp4_content_type(self) -> None:
        assert _guess_extension("https://cdn.example.com/file", "audio/mp4") == ".m4a"

    def test_m4a_content_type(self) -> None:
        assert _guess_extension("https://cdn.example.com/file", "audio/m4a") == ".m4a"

    def test_opus_content_type(self) -> None:
        assert _guess_extension("https://cdn.example.com/file", "audio/opus") == ".ogg"


# ---------------------------------------------------------------------------
# _LocalWhisperManager — torch CUDA detection
# ---------------------------------------------------------------------------


class TestWhisperManagerCudaDetection:
    def test_resolve_device_auto_with_cuda(self) -> None:
        mgr = _LocalWhisperManager()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert mgr._resolve_device("auto") == "cuda"

    def test_resolve_device_auto_without_cuda(self) -> None:
        mgr = _LocalWhisperManager()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        with patch.dict("sys.modules", {"torch": mock_torch}):
            assert mgr._resolve_device("auto") == "cpu"


# ---------------------------------------------------------------------------
# Fallback behavior
# ---------------------------------------------------------------------------


class TestFallback:
    @pytest.mark.asyncio
    async def test_cloud_fails_fallback_to_local(self) -> None:
        """When cloud provider fails and local is available, fallback to local."""
        path = _audio_file()
        mock_model = _mock_whisper_model()

        with (
            patch(
                "app.channels.voice.stt._transcribe_openai_compatible",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
            patch(
                "app.channels.voice.stt.is_local_available",
                return_value=True,
            ),
            patch.object(
                _LocalWhisperManager, "get_model", new_callable=AsyncMock, return_value=mock_model
            ),
        ):
            try:
                result = await transcribe(path, _voice("openai"))
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Hello local world"

    @pytest.mark.asyncio
    async def test_local_fails_fallback_to_cloud(self) -> None:
        """When local provider fails and cloud API key is configured, fallback to cloud."""
        path = _audio_file()
        response_body = {"text": "Cloud fallback", "language": "en"}

        mock_resp = httpx.Response(
            200,
            json=response_body,
            request=httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions"),
        )

        with (
            patch.object(
                _LocalWhisperManager,
                "get_model",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Model load failed"),
            ),
            patch("app.channels.voice.stt.httpx.AsyncClient") as mock_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            try:
                result = await transcribe(path, _voice("local", api_key="sk-fallback"))
            finally:
                path.unlink(missing_ok=True)

        assert result is not None
        assert result.text == "Cloud fallback"

    @pytest.mark.asyncio
    async def test_local_fails_no_cloud_key_returns_none(self) -> None:
        """When local fails and no cloud API key, returns None."""
        path = _audio_file()

        with patch.object(
            _LocalWhisperManager,
            "get_model",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Model load failed"),
        ):
            try:
                result = await transcribe(path, _voice("local", api_key=""))
            finally:
                path.unlink(missing_ok=True)

        assert result is None

    @pytest.mark.asyncio
    async def test_cloud_fails_no_local_returns_none(self) -> None:
        """When cloud fails and local is not available, returns None."""
        path = _audio_file()

        with (
            patch(
                "app.channels.voice.stt._transcribe_openai_compatible",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API down"),
            ),
            patch(
                "app.channels.voice.stt.is_local_available",
                return_value=False,
            ),
        ):
            try:
                result = await transcribe(path, _voice("openai"))
            finally:
                path.unlink(missing_ok=True)

        assert result is None
