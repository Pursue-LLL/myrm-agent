"""Speech-to-Text API

Provides a transcription endpoint for the web frontend.
Reuses the existing stt.py engine and user VoiceConfig.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.api.dependencies import get_deploy_identity, verify_voice_enabled

if TYPE_CHECKING:
    from app.channels.types import VoiceConfig

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_voice_enabled)])

_MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "audio/webm",
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "audio/wav",
        "audio/flac",
        "audio/x-m4a",
        "audio/mp3",
        "video/webm",  # Chrome records webm as video/webm
    }
)
_EXT_MAP: dict[str, str] = {
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/flac": ".flac",
}


class TranscribeResponse(BaseModel):
    text: str = Field(..., description="Transcribed text")
    language: str | None = Field(None, description="Detected language")
    duration: float | None = Field(None, description="Audio duration in seconds")


class LocalSTTStatus(BaseModel):
    available: bool = Field(..., description="Whether faster-whisper is installed")
    model_loaded: bool = Field(..., description="Whether model is currently loaded in memory")
    config: dict[str, str] | None = Field(None, description="Current model configuration")


@router.get("/status", response_model=LocalSTTStatus)
async def stt_status() -> LocalSTTStatus:
    """Check local STT availability and model status."""
    from app.channels.voice.stt import get_local_status

    status = get_local_status()
    return LocalSTTStatus(
        available=bool(status["available"]),
        model_loaded=bool(status["model_loaded"]),
        config=status["config"] if isinstance(status["config"], dict) else None,
    )


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile,
    user_id: str = Depends(get_deploy_identity),
) -> TranscribeResponse:
    """Transcribe an uploaded audio file using the user's STT configuration."""
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {content_type}")

    audio_bytes = await file.read()
    if len(audio_bytes) > _MAX_AUDIO_SIZE:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25 MB)")
    if len(audio_bytes) < 1024:
        raise HTTPException(status_code=400, detail="Audio file too small")

    voice_config = await _load_user_voice_config("sandbox")
    if not voice_config or not voice_config.stt_enabled:
        raise HTTPException(status_code=400, detail="STT is not enabled. Configure it in Settings > Voice.")

    suffix = _EXT_MAP.get(content_type, ".webm")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        from app.channels.voice.stt import transcribe

        result = await transcribe(tmp_path, voice_config)
        if not result or not result.text:
            raise HTTPException(status_code=422, detail="Transcription returned empty text")

        return TranscribeResponse(
            text=result.text,
            language=result.language,
            duration=result.duration,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("STT transcription failed for sandbox user")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


async def _load_user_voice_config(user_id: str) -> VoiceConfig | None:
    """Load VoiceConfig from the user's config store."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import extract_voice_config

    try:
        configs = await load_user_configs()
        return extract_voice_config(configs.voice_dict)
    except Exception:
        logger.exception("Failed to load voice config for sandbox user")
        return None
