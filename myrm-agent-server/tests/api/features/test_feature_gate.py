"""Feature gate enforcement tests.

Validates that disabled features are correctly rejected (403) at the API layer,
and that enabled features pass through normally.

Covers:
- voice_interaction gate via router-level Depends (STT/TTS/Voice)
- registration completeness
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.core.features import (
    FeatureSet,
    _reset_for_testing,
    init_features,
    registry,
)
from myrm_agent_harness.core.features.types import FeatureStage


@pytest.fixture(autouse=True)
def _reset_features():
    """Reset feature flags before each test."""
    _reset_for_testing()
    from app.services.features.registration import register_all_features

    register_all_features()
    yield
    _reset_for_testing()


def _init_with_overrides(overrides: dict[str, bool]) -> FeatureSet:
    """Initialize features with specific overrides."""
    return init_features(overrides=overrides)


@pytest.fixture
async def async_client():
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="features")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Registration completeness
# ---------------------------------------------------------------------------


class TestFeatureRegistration:
    """Verify all gated features are registered with correct metadata."""

    def test_consensus_registered_as_removed(self):
        _init_with_overrides({})
        spec = registry.get("consensus")
        assert spec is not None
        assert spec.stage == FeatureStage.REMOVED
        assert spec.default_enabled is False

    def test_consensus_override_is_ignored(self):
        fs = _init_with_overrides({"consensus": True})
        assert not fs.enabled("consensus")
        assert any("removed" in w.lower() for w in fs.warnings())

    def test_voice_interaction_registered(self):
        _init_with_overrides({})
        spec = registry.get("voice_interaction")
        assert spec is not None
        assert spec.stage == FeatureStage.EXPERIMENTAL
        assert spec.default_enabled is False

    def test_all_gated_features_default_disabled(self):
        """voice_interaction off by default; consensus is removed."""
        fs = _init_with_overrides({})
        assert not fs.enabled("consensus")
        assert not fs.enabled("voice_interaction")

    def test_override_enables_features(self):
        fs = _init_with_overrides(
            {
                "consensus": True,
                "voice_interaction": True,
            }
        )
        assert not fs.enabled("consensus")
        assert fs.enabled("voice_interaction")

    def test_sanitize_user_overrides_strips_removed_features(self):
        from app.services.features.feature_config_service import sanitize_user_overrides

        _init_with_overrides({})
        cleaned = sanitize_user_overrides({"consensus": True})
        assert "consensus" not in cleaned


# ---------------------------------------------------------------------------
# 2. verify_voice_enabled dependency
# ---------------------------------------------------------------------------


class TestVerifyVoiceEnabled:
    """Test the verify_voice_enabled dependency function."""

    def test_raises_403_when_disabled(self):
        from fastapi import HTTPException

        _init_with_overrides({"voice_interaction": False})

        from app.api.dependencies import verify_voice_enabled

        with pytest.raises(HTTPException) as exc_info:
            verify_voice_enabled()
        assert exc_info.value.status_code == 403
        assert "Feature Gate" in exc_info.value.detail

    def test_passes_when_enabled(self):
        _init_with_overrides({"voice_interaction": True})

        from app.api.dependencies import verify_voice_enabled

        verify_voice_enabled()


# ---------------------------------------------------------------------------
# 4. STT/TTS API gate (HTTP endpoints)
# ---------------------------------------------------------------------------


class TestVoiceAPIGate:
    """Test that STT/TTS HTTP endpoints return 403 when voice is disabled."""

    @pytest.mark.asyncio
    async def test_stt_transcribe_blocked_when_disabled(self, async_client: AsyncClient):
        _init_with_overrides({"voice_interaction": False})
        response = await async_client.post(
            "/api/v1/stt/transcribe",
            files={"file": ("test.webm", b"\x00" * 2048, "audio/webm")},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_stt_status_blocked_when_disabled(self, async_client: AsyncClient):
        _init_with_overrides({"voice_interaction": False})
        response = await async_client.get("/api/v1/stt/status")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_tts_synthesize_blocked_when_disabled(self, async_client: AsyncClient):
        _init_with_overrides({"voice_interaction": False})
        response = await async_client.post(
            "/api/v1/tts/synthesize",
            json={"text": "hello"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_tts_stream_blocked_when_disabled(self, async_client: AsyncClient):
        _init_with_overrides({"voice_interaction": False})
        response = await async_client.post(
            "/api/v1/tts/synthesize-stream",
            json={"text": "hello"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_realtime_token_blocked_when_disabled(self, async_client: AsyncClient):
        _init_with_overrides({"voice_interaction": False})
        response = await async_client.post(
            "/api/v1/voice/realtime-token",
            json={},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_realtime_tool_exec_blocked_when_disabled(self, async_client: AsyncClient):
        _init_with_overrides({"voice_interaction": False})
        response = await async_client.post(
            "/api/v1/voice/realtime-tool-exec",
            json={"tool_name": "test", "arguments": {}},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_realtime_transcript_blocked_when_disabled(self, async_client: AsyncClient):
        _init_with_overrides({"voice_interaction": False})
        response = await async_client.post(
            "/api/v1/voice/realtime-transcript",
            json={"chat_id": "test", "entries": []},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# 5. Experimental features API (product surface)
# ---------------------------------------------------------------------------


class TestExperimentalFeaturesAPI:
    """Experimental settings API must not expose removed features."""

    @pytest.mark.asyncio
    async def test_experimental_list_excludes_removed_features(self, async_client: AsyncClient):
        _init_with_overrides({"consensus": True})
        response = await async_client.get("/api/v1/features/experimental")
        assert response.status_code == 200
        payload = response.json()
        keys = [item["key"] for item in payload.get("features", []) if isinstance(item, dict)]
        assert "consensus" not in keys
