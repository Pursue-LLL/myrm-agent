"""Speech-to-Text transcription for inbound voice messages.

Supports multiple providers with automatic fallback:
  1. Local Whisper (faster-whisper, free, no API key, privacy-first)
  2. OpenAI Whisper (whisper-1, gpt-4o-mini-transcribe)
  3. Groq (whisper-large-v3) — OpenAI-compatible endpoint
  4. Deepgram (nova-3)

Fallback strategy (mirrors TTS Edge-TTS fallback design):
  - Primary provider fails → try local if available (free fallback)
  - Local fails → try cloud API if configured

[INPUT]
- channels.types::VoiceConfig, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- transcribe(): Audio file -> STTResult (text + language + duration)
- is_local_available(): Check if faster-whisper is installed
- get_local_status(): Check model download status

[POS]
Inbound speech-to-text. Called by Router when InboundMessage contains AUDIO attachment.
Transcribes voice content to text and injects it into the message.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.channels.types import STTResult, VoiceConfig

logger = logging.getLogger(__name__)

_OPENAI_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"
_GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_DEEPGRAM_LISTEN_URL = "https://api.deepgram.com/v1/listen"

_SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {
        ".mp3",
        ".mp4",
        ".mpeg",
        ".mpga",
        ".m4a",
        ".wav",
        ".webm",
        ".ogg",
        ".opus",
        ".flac",
    }
)

_MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

_MIME_MAP: dict[str, str] = {
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
}


# ---------------------------------------------------------------------------
# Local Whisper Model Manager (Singleton)
# ---------------------------------------------------------------------------


class _LocalWhisperManager:
    """Process-level singleton for the faster-whisper model.

    Loads the model lazily on first transcription call and reuses it
    across subsequent calls. Reloads when configuration changes.
    """

    def __init__(self) -> None:
        self._model: object | None = None
        self._model_size: str = ""
        self._device: str = ""
        self._compute_type: str = ""
        self._lock = asyncio.Lock()

    def _resolve_device(self, requested: str) -> str:
        """Resolve 'auto' to actual device."""
        if requested != "auto":
            return requested
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _resolve_compute_type(self, requested: str, device: str) -> str:
        """Resolve 'auto' to optimal compute type for the device."""
        if requested != "auto":
            return requested
        return "float16" if device == "cuda" else "int8"

    async def get_model(self, config: VoiceConfig) -> object:
        """Get or load the WhisperModel, reloading if config changed."""
        async with self._lock:
            model_size = config.stt_local_model or "base"
            device = self._resolve_device(config.stt_local_device)
            compute_type = self._resolve_compute_type(config.stt_local_compute_type, device)

            if (
                self._model is not None
                and self._model_size == model_size
                and self._device == device
                and self._compute_type == compute_type
            ):
                return self._model

            from faster_whisper import WhisperModel

            loop = asyncio.get_running_loop()
            model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(model_size, device=device, compute_type=compute_type),
            )

            self._model = model
            self._model_size = model_size
            self._device = device
            self._compute_type = compute_type

            logger.info(
                "STT: local whisper model loaded (size=%s, device=%s, compute=%s)",
                model_size,
                device,
                compute_type,
            )
            return model

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def current_config(self) -> dict[str, str]:
        return {
            "model_size": self._model_size,
            "device": self._device,
            "compute_type": self._compute_type,
        }


_whisper_manager = _LocalWhisperManager()


def is_local_available() -> bool:
    """Check if faster-whisper is installed and importable."""
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def get_local_status() -> dict[str, object]:
    """Get local STT status for the /stt/status API."""
    available = is_local_available()
    return {
        "available": available,
        "model_loaded": _whisper_manager.is_loaded,
        "config": (_whisper_manager.current_config if _whisper_manager.is_loaded else None),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def transcribe(audio_path: Path | None, config: VoiceConfig, audio_bytes: bytes | None = None) -> STTResult | None:
    """Transcribe an audio file or bytes using the configured STT provider.

    Fallback strategy (mirrors TTS pattern):
      - Primary provider fails → try local if available
      - Local provider fails → try first available cloud API

    Returns None if transcription fails (best-effort, never blocks message flow).
    """
    if audio_bytes is None:
        if audio_path is None or not audio_path.exists():
            logger.warning("STT: audio file not found: %s", audio_path)
            return None
        file_size = audio_path.stat().st_size
    else:
        file_size = len(audio_bytes)

    if file_size < 1024:
        logger.warning("STT: audio file too small (%d bytes), skipping", file_size)
        return None
    if file_size > _MAX_AUDIO_SIZE_BYTES:
        logger.warning("STT: audio file too large (%d bytes), skipping", file_size)
        return None

    provider = config.stt_provider.lower()

    try:
        if provider == "local":
            return await _transcribe_local(audio_path, config, audio_bytes)
        if provider in ("openai", "groq"):
            return await _transcribe_openai_compatible(audio_path, config, audio_bytes)
        if provider == "deepgram":
            return await _transcribe_deepgram(audio_path, config, audio_bytes)
        logger.warning("STT: unknown provider '%s', trying OpenAI-compatible", provider)
        return await _transcribe_openai_compatible(audio_path, config, audio_bytes)
    except Exception:
        logger.exception("STT: primary provider '%s' failed", provider)

    # Fallback: if primary was cloud, try local; if primary was local, try cloud
    if provider != "local" and is_local_available():
        try:
            logger.warning("STT: falling back to local whisper (free)")
            return await _transcribe_local(audio_path, config, audio_bytes)
        except Exception:
            logger.exception("STT: local whisper fallback also failed")
    elif provider == "local" and config.stt_api_key:
        try:
            logger.warning("STT: local failed, falling back to cloud API")
            return await _transcribe_openai_compatible(audio_path, config, audio_bytes)
        except Exception:
            logger.exception("STT: cloud API fallback also failed")

    return None


async def download_audio(url: str, *, timeout: float = 30.0) -> Path | None:
    """Download a remote audio file to a temporary path.

    Returns None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            suffix = _guess_extension(url, resp.headers.get("content-type", ""))
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(resp.content)
            tmp.close()
            return Path(tmp.name)
    except Exception:
        logger.exception("STT: failed to download audio from %s", url)
        return None


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


async def _transcribe_local(
    audio_path: Path | None,
    config: VoiceConfig,
    audio_bytes: bytes | None = None,
) -> STTResult:
    """Local transcription via faster-whisper (free, no API key, privacy-first)."""
    model = await _whisper_manager.get_model(config)
    loop = asyncio.get_running_loop()

    language = config.stt_language or None

    def _run_transcription() -> tuple[list[object], object]:
        import io

        audio_input = io.BytesIO(audio_bytes) if audio_bytes is not None else str(audio_path)
        segments, info = model.transcribe(  # type: ignore[union-attr]
            audio_input,
            beam_size=5,
            language=language,
            vad_filter=True,
        )
        return list(segments), info

    segments, info = await loop.run_in_executor(None, _run_transcription)

    text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())  # type: ignore[union-attr]
    if not text:
        raise ValueError("Empty transcript returned from local whisper")

    logger.info(
        "STT: local transcription ok (model=%s, chars=%d, lang=%s)",
        config.stt_local_model,
        len(text),
        info.language,  # type: ignore[union-attr]
    )
    return STTResult(
        text=text,
        language=info.language,  # type: ignore[union-attr]
        duration=info.duration,  # type: ignore[union-attr]
    )


async def _transcribe_openai_compatible(
    audio_path: Path | None,
    config: VoiceConfig,
    audio_bytes: bytes | None = None,
) -> STTResult:
    """OpenAI / Groq transcription (same API format)."""
    provider = config.stt_provider.lower()
    base_url = _GROQ_TRANSCRIPTION_URL if provider == "groq" else _OPENAI_TRANSCRIPTION_URL
    model = config.stt_model or ("whisper-large-v3" if provider == "groq" else "whisper-1")

    async with httpx.AsyncClient(timeout=60.0) as client:
        data: dict[str, str] = {"model": model, "response_format": "json"}
        if config.stt_language:
            data["language"] = config.stt_language

        if audio_bytes is not None:
            filename = "audio.wav"
            mime_type = "audio/wav"
            files = {"file": (filename, audio_bytes, mime_type)}
            resp = await client.post(
                base_url,
                headers={"Authorization": f"Bearer {config.stt_api_key}"},
                files=files,
                data=data,
            )
            resp.raise_for_status()
        else:
            with audio_path.open("rb") as f:
                files = {"file": (audio_path.name, f, _guess_mime(audio_path))}
                resp = await client.post(
                    base_url,
                    headers={"Authorization": f"Bearer {config.stt_api_key}"},
                    files=files,
                    data=data,
                )
                resp.raise_for_status()

    body = resp.json()
    text = body.get("text", "").strip()
    if not text:
        raise ValueError("Empty transcript returned")

    logger.info(
        "STT: %s transcription ok (model=%s, chars=%d)",
        provider,
        model,
        len(text),
    )
    return STTResult(
        text=text,
        language=body.get("language"),
        duration=body.get("duration"),
    )


async def _transcribe_deepgram(
    audio_path: Path | None,
    config: VoiceConfig,
    audio_bytes: bytes | None = None,
) -> STTResult:
    """Deepgram transcription API."""
    model = config.stt_model or "nova-3"
    mime = "audio/wav" if audio_bytes is not None else _guess_mime(audio_path)

    params: dict[str, str] = {"model": model, "smart_format": "true"}
    if config.stt_language:
        params["language"] = config.stt_language

    async with httpx.AsyncClient(timeout=60.0) as client:
        payload = audio_bytes if audio_bytes is not None else audio_path.read_bytes()
        resp = await client.post(
            _DEEPGRAM_LISTEN_URL,
            headers={
                "Authorization": f"Token {config.stt_api_key}",
                "Content-Type": mime,
            },
            params=params,
            content=payload,
        )
        resp.raise_for_status()

    body = resp.json()
    channels = body.get("results", {}).get("channels", [])
    if not channels:
        raise ValueError("No channels in Deepgram response")

    alternatives = channels[0].get("alternatives", [])
    if not alternatives:
        raise ValueError("No alternatives in Deepgram response")

    text = alternatives[0].get("transcript", "").strip()
    if not text:
        raise ValueError("Empty transcript returned")

    metadata = body.get("metadata", {})
    logger.info(
        "STT: deepgram transcription ok (model=%s, chars=%d)",
        model,
        len(text),
    )
    return STTResult(
        text=text,
        language=metadata.get("language"),
        duration=metadata.get("duration"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guess_extension(url: str, content_type: str) -> str:
    """Guess file extension from URL or Content-Type."""
    path = urlparse(url).path.lower()
    for ext in _SUPPORTED_AUDIO_EXTENSIONS:
        if path.endswith(ext):
            return ext

    ct = content_type.lower()
    if "ogg" in ct or "opus" in ct:
        return ".ogg"
    if "mp4" in ct or "m4a" in ct:
        return ".m4a"
    if "wav" in ct:
        return ".wav"
    if "webm" in ct:
        return ".webm"
    return ".mp3"


def _guess_mime(audio_path: Path) -> str:
    """Guess MIME type from file extension."""
    return _MIME_MAP.get(audio_path.suffix.lower(), "audio/mpeg")
