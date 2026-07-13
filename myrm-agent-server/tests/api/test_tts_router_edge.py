"""Tests for Edge TTS availability guard on TTS API routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from myrm_agent_harness.core.features import _reset_for_testing

from app.api.tts.router import _ensure_edge_tts_if_needed
from app.channels.types import TTSMode, VoiceConfig
from tests.support.feature_flags import seed_voice_interaction_flags
from tests.support.minimal_app import API_PREFIX, build_minimal_app


def _edge_voice() -> VoiceConfig:
    return VoiceConfig(
        tts_mode=TTSMode.ALWAYS,
        tts_provider="edge",
    )


@pytest.fixture
def client() -> TestClient:
    seed_voice_interaction_flags()
    app = build_minimal_app("tts")
    with TestClient(app) as test_client:
        yield test_client
    _reset_for_testing()


def test_ensure_edge_passes_when_available() -> None:
    with patch("app.channels.voice.tts.is_edge_tts_available", return_value=True):
        _ensure_edge_tts_if_needed(_edge_voice())


def test_ensure_edge_raises_503_when_unavailable() -> None:
    with patch("app.channels.voice.tts.is_edge_tts_available", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            _ensure_edge_tts_if_needed(_edge_voice())

    assert exc_info.value.status_code == 503
    assert "voice-tts" in str(exc_info.value.detail)


def test_ensure_edge_skips_non_edge_provider() -> None:
    voice = VoiceConfig(tts_mode=TTSMode.ALWAYS, tts_provider="openai", tts_api_key="sk-test")
    with patch("app.channels.voice.tts.is_edge_tts_available", return_value=False):
        _ensure_edge_tts_if_needed(voice)


def test_synthesize_returns_503_when_edge_unavailable(client: TestClient) -> None:
    with (
        patch("app.api.tts.router._resolve_voice_config", new_callable=AsyncMock) as mock_resolve,
        patch("app.channels.voice.tts.is_edge_tts_available", return_value=False),
    ):
        mock_resolve.return_value = _edge_voice()
        response = client.post(
            f"{API_PREFIX}/tts/synthesize",
            json={"text": "Hello from the test suite."},
        )

    assert response.status_code == 503
    assert "voice-tts" in response.json()["detail"]


def test_synthesize_stream_returns_503_when_edge_unavailable(client: TestClient) -> None:
    with (
        patch("app.api.tts.router._resolve_voice_config", new_callable=AsyncMock) as mock_resolve,
        patch("app.channels.voice.tts.is_edge_tts_available", return_value=False),
    ):
        mock_resolve.return_value = _edge_voice()
        response = client.post(
            f"{API_PREFIX}/tts/synthesize-stream",
            json={"text": "Hello from the test suite."},
        )

    assert response.status_code == 503
    assert "voice-tts" in response.json()["detail"]


async def _empty_stream(_text: str, _config: VoiceConfig) -> AsyncIterator[bytes]:
    if False:
        yield b""


def test_synthesize_stream_returns_422_when_no_audio(client: TestClient) -> None:
    with (
        patch("app.api.tts.router._resolve_voice_config", new_callable=AsyncMock) as mock_resolve,
        patch("app.channels.voice.tts.is_edge_tts_available", return_value=True),
        patch("app.channels.voice.tts.synthesize_stream", side_effect=_empty_stream),
    ):
        mock_resolve.return_value = VoiceConfig(
            tts_mode=TTSMode.ALWAYS,
            tts_provider="openai",
            tts_api_key="sk-test",
        )
        response = client.post(
            f"{API_PREFIX}/tts/synthesize-stream",
            json={"text": "Hello from the test suite."},
        )

    assert response.status_code == 422
    assert "no audio" in response.json()["detail"].lower()
