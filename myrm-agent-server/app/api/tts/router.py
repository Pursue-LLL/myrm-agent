"""Text-to-Speech API

Provides synthesis endpoints for the web frontend:
- /synthesize: Full synthesis (returns complete audio file)
- /synthesize-stream: Streaming synthesis (chunked MP3 for low-latency playback)

Edge TTS requests return 503 when the optional voice-tts extra is not installed.
Empty synthesis results return 422 on both endpoints.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.api.dependencies import get_deploy_identity, verify_voice_enabled
from app.channels.types import VoiceConfig

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_voice_enabled)])

_MAX_TEXT_LENGTH = 10000
_VALID_PROVIDERS = frozenset({"openai", "elevenlabs", "fish_audio", "minimax", "edge"})


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_TEXT_LENGTH)
    provider: str | None = Field(None, description="Override TTS provider")
    voice: str | None = Field(None, description="Override voice ID")
    speed: float | None = Field(None, ge=0.5, le=2.0, description="Override speech speed")
    pitch: float | None = Field(None, ge=-10.0, le=10.0, description="Override pitch in Hz")


def _ensure_edge_tts_if_needed(voice_config: VoiceConfig) -> None:
    """Reject Edge TTS requests when the optional voice-tts extra is not installed."""
    if voice_config.tts_provider.lower() != "edge":
        return
    from app.channels.voice.tts import EDGE_TTS_INSTALL_HINT, is_edge_tts_available

    if not is_edge_tts_available():
        raise HTTPException(
            status_code=503,
            detail=f"Edge TTS is not installed. Install with: {EDGE_TTS_INSTALL_HINT}",
        )


@router.post("/synthesize")
async def synthesize_text(
    req: TTSRequest,
    user_id: str = Depends(get_deploy_identity),
) -> FileResponse:
    """Synthesize text to speech (full file download)."""
    voice_config = await _resolve_voice_config("sandbox", req)
    _ensure_edge_tts_if_needed(voice_config)

    from app.channels.voice.tts import synthesize

    try:
        audio_path = await synthesize(req.text, voice_config, output_format="mp3")
    except Exception as exc:
        logger.exception("TTS synthesis failed for sandbox user")
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {exc}") from exc

    if not audio_path or not audio_path.exists():
        raise HTTPException(status_code=422, detail="TTS synthesis returned no audio")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename="tts_output.mp3",
        background=_cleanup_task(audio_path),
    )


@router.post("/synthesize-stream")
async def synthesize_text_stream(
    req: TTSRequest,
    user_id: str = Depends(get_deploy_identity),
) -> StreamingResponse:
    """Stream-synthesize text to speech (chunked MP3 for low-latency playback)."""
    voice_config = await _resolve_voice_config("sandbox", req)
    _ensure_edge_tts_if_needed(voice_config)

    from app.channels.voice.tts import synthesize_stream

    stream = synthesize_stream(req.text, voice_config)
    first_chunk: bytes | None = None

    try:
        async for chunk in stream:
            if not chunk:
                continue
            first_chunk = chunk
            break
    except Exception as exc:
        logger.exception("TTS stream failed for sandbox user")
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {exc}") from exc

    if first_chunk is None:
        raise HTTPException(status_code=422, detail="TTS synthesis returned no audio")

    async def _generate() -> AsyncGenerator[bytes, None]:
        yield first_chunk
        try:
            async for chunk in stream:
                if chunk:
                    yield chunk
        except Exception:
            logger.exception("TTS stream failed mid-stream for sandbox user")

    return StreamingResponse(
        _generate(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache",
            "Transfer-Encoding": "chunked",
        },
    )


async def _resolve_voice_config(user_id: str, req: TTSRequest) -> VoiceConfig:
    """Load user VoiceConfig and apply request overrides."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import extract_web_tts_config

    try:
        configs = await load_user_configs()
        voice_config = extract_web_tts_config(configs.voice_dict)
    except Exception as exc:
        logger.exception("Failed to load voice config for sandbox user")
        raise HTTPException(
            status_code=400,
            detail="Voice config not found. Configure it in Settings > Voice.",
        ) from exc

    if not voice_config:
        raise HTTPException(
            status_code=400,
            detail="Voice config not found. Configure it in Settings > Voice.",
        )

    if req.provider:
        if req.provider not in _VALID_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {req.provider}")

    has_overrides = req.provider or req.voice or req.speed is not None or req.pitch is not None
    if has_overrides:
        voice_config = _override_config(
            voice_config,
            provider=req.provider,
            voice=req.voice,
            speed=req.speed,
            pitch=req.pitch,
        )

    return voice_config


def _override_config(
    base: VoiceConfig,
    *,
    provider: str | None = None,
    voice: str | None = None,
    speed: float | None = None,
    pitch: float | None = None,
) -> VoiceConfig:
    """Create a new VoiceConfig with overridden fields (frozen dataclass)."""
    from dataclasses import asdict

    from app.channels.types import VoiceConfig

    fields = asdict(base)
    if provider:
        fields["tts_provider"] = provider
    if voice:
        fields["tts_voice"] = voice
    if speed is not None:
        fields["tts_speed"] = speed
    if pitch is not None:
        fields["tts_pitch"] = pitch
    return VoiceConfig(**fields)


def _cleanup_task(path: Path) -> BackgroundTask:
    """Background task to delete temporary audio file after response."""
    return BackgroundTask(path.unlink, missing_ok=True)
