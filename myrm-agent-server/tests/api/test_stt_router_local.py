"""Tests for local STT availability guard on STT API routes."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from myrm_agent_harness.core.features import _reset_for_testing

from app.api.stt.router import _ensure_local_stt_if_needed
from app.channels.types import VoiceConfig
from app.channels.voice.stt import local_stt_unavailable_detail
from tests.support.feature_flags import seed_voice_interaction_flags
from tests.support.minimal_app import API_PREFIX, build_minimal_app


def _local_voice() -> VoiceConfig:
    return VoiceConfig(
        stt_enabled=True,
        stt_provider="local",
    )


@pytest.fixture
def client() -> TestClient:
    seed_voice_interaction_flags()
    app = build_minimal_app("stt")
    with TestClient(app) as test_client:
        yield test_client
    _reset_for_testing()


def test_ensure_local_passes_when_available() -> None:
    with patch("app.channels.voice.stt.is_local_available", return_value=True):
        _ensure_local_stt_if_needed(_local_voice())


def test_ensure_local_raises_503_when_unavailable() -> None:
    with patch("app.channels.voice.stt.is_local_available", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            _ensure_local_stt_if_needed(_local_voice())

    assert exc_info.value.status_code == 503
    assert "local-stt" in str(exc_info.value.detail)


def test_ensure_local_skips_non_local_provider() -> None:
    voice = VoiceConfig(stt_enabled=True, stt_provider="openai", stt_api_key="sk-test")
    with patch("app.channels.voice.stt.is_local_available", return_value=False):
        _ensure_local_stt_if_needed(voice)


def test_local_stt_unavailable_detail_returns_hint() -> None:
    with patch("app.channels.voice.stt.is_local_available", return_value=False):
        detail = local_stt_unavailable_detail(_local_voice())

    assert detail is not None
    assert "local-stt" in detail


def test_local_stt_unavailable_detail_none_for_cloud() -> None:
    voice = VoiceConfig(stt_enabled=True, stt_provider="openai")
    assert local_stt_unavailable_detail(voice) is None


def test_transcribe_returns_503_when_local_unavailable(client: TestClient) -> None:
    with (
        patch("app.api.stt.router._load_user_voice_config", new_callable=AsyncMock) as mock_load,
        patch("app.channels.voice.stt.is_local_available", return_value=False),
    ):
        mock_load.return_value = _local_voice()
        response = client.post(
            f"{API_PREFIX}/stt/transcribe",
            files={"file": ("recording.webm", BytesIO(b"x" * 2048), "audio/webm")},
        )

    assert response.status_code == 503
    assert "local-stt" in response.json()["detail"]
