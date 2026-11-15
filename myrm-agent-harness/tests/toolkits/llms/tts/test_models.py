"""Unit tests for llms/tts data models."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.tts.models import (
    SUPPORTED_TTS_PROVIDERS,
    MediaMeta,
    TTSConfig,
    TTSGenerationError,
    TTSResult,
)


def test_media_meta_fields() -> None:
    meta = MediaMeta(prompt="hello", model="tts-1", provider="openai")
    assert meta.prompt == "hello"
    assert meta.model == "tts-1"
    assert meta.provider == "openai"


def test_tts_generation_error_stores_latency() -> None:
    err = TTSGenerationError("failed", latency_ms=42.5)
    assert str(err) == "failed"
    assert err.latency_ms == 42.5


def test_tts_result_frozen() -> None:
    result = TTSResult(
        audio_bytes=b"x",
        mime_type="audio/mpeg",
        provider="openai",
        model="tts-1",
    )
    with pytest.raises(AttributeError):
        result.provider = "elevenlabs"  # type: ignore[misc]


def test_tts_config_requires_provider_model_and_voice() -> None:
    with pytest.raises(ValueError, match="provider"):
        TTSConfig()  # type: ignore[call-arg]


def test_tts_config_keeps_the_selection_and_default_tuning() -> None:
    cfg = TTSConfig(provider="elevenlabs", model="eleven_v2", voice="v1")
    assert (cfg.provider, cfg.model, cfg.voice) == ("elevenlabs", "eleven_v2", "v1")
    assert cfg.speed == 1.0
    assert cfg.media_callback is None


def test_supported_providers_cover_the_engine_request_builders() -> None:
    assert sorted(SUPPORTED_TTS_PROVIDERS) == ["elevenlabs", "openai", "volcengine"]
