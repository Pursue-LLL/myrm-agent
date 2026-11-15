"""Tests for the tts_generate tool: success carries the stored reference, everything else is an explicit error."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.tts import TTSConfig, TTSGenerationError, TTSResult

from app.ai_agents.media_tools.tts_agent_tool import MAX_TTS_TEXT_LENGTH, TTSTool, create_tts_tool


@pytest.fixture
def config() -> TTSConfig:
    return TTSConfig(provider="openai", model="gpt-4o-mini-tts", voice="alloy", api_key="test-key")


@pytest.fixture
def engine_generate():
    with patch(
        "app.ai_agents.media_tools.tts_agent_tool.AsyncTTSEngine.generate",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


def _result(*, persisted_ref: str | None = "media://media_speech", duration_seconds: float | None = 3.24) -> TTSResult:
    return TTSResult(
        audio_bytes=b"audio",
        mime_type="audio/mpeg",
        provider="openai",
        model="gpt-4o-mini-tts",
        latency_ms=150.4,
        persisted_ref=persisted_ref,
        duration_seconds=duration_seconds,
    )


def test_factory_returns_the_named_tool(config: TTSConfig) -> None:
    tool = create_tts_tool(config)

    assert isinstance(tool, TTSTool)
    assert tool.name == "tts_generate"
    assert tool.config == config


def test_the_tool_is_async_only(config: TTSConfig) -> None:
    with pytest.raises(NotImplementedError, match="only supports async"):
        TTSTool(config)._run(text="hello")


@pytest.mark.asyncio
async def test_success_carries_the_stored_reference_and_what_produced_it(config: TTSConfig, engine_generate) -> None:
    engine_generate.return_value = _result()

    payload = json.loads(await TTSTool(config).ainvoke({"text": "Hello"}))

    assert payload == {
        "status": "success",
        "provider": "openai",
        "model": "gpt-4o-mini-tts",
        "latency_ms": 150,
        "audio_url": "media://media_speech",
        "message": "Audio generated; it appears in the chat for the user to play.",
        "duration_seconds": 3.2,
    }


@pytest.mark.asyncio
async def test_a_result_without_a_stored_reference_is_an_error(config: TTSConfig, engine_generate) -> None:
    engine_generate.return_value = _result(persisted_ref=None)

    payload = json.loads(await TTSTool(config).ainvoke({"text": "Hello"}))

    assert payload["status"] == "error"
    assert "not stored" in payload["error"]
    assert "audio_url" not in payload


@pytest.mark.asyncio
async def test_an_engine_failure_is_reported_not_swallowed(config: TTSConfig, engine_generate) -> None:
    engine_generate.side_effect = TTSGenerationError("provider down")

    payload = json.loads(await TTSTool(config).ainvoke({"text": "Hello"}))

    assert payload["status"] == "error"
    assert "provider down" in payload["error"]


@pytest.mark.asyncio
async def test_empty_text_is_rejected(config: TTSConfig, engine_generate) -> None:
    payload = json.loads(await TTSTool(config).ainvoke({"text": "   "}))

    assert payload["status"] == "error"
    engine_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_text_over_the_limit_is_rejected(config: TTSConfig, engine_generate) -> None:
    payload = json.loads(await TTSTool(config).ainvoke({"text": "x" * (MAX_TTS_TEXT_LENGTH + 1)}))

    assert payload["status"] == "error"
    assert str(MAX_TTS_TEXT_LENGTH) in payload["error"]
    engine_generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_style_is_trimmed_and_clamped_before_it_reaches_the_engine(config: TTSConfig, engine_generate) -> None:
    engine_generate.return_value = _result(duration_seconds=None)

    payload = json.loads(await TTSTool(config).ainvoke({"text": "Hi", "style": "  " + "calm " * 80}))

    engine_generate.assert_awaited_once()
    style = engine_generate.await_args.kwargs["style"]
    assert style == ("calm " * 80).strip()[:200]
    assert len(style) == 200
    assert "duration_seconds" not in payload
