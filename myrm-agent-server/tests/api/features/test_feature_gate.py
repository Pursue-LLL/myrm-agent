"""Feature gate enforcement tests.

Validates that disabled features are correctly rejected (403) at the API layer,
and that enabled features pass through normally.

Covers:
- action_mode gate (deep_research, consensus) via orchestrator
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

    def test_consensus_registered(self):
        _init_with_overrides({})
        spec = registry.get("consensus")
        assert spec is not None
        assert spec.stage == FeatureStage.EXPERIMENTAL
        assert spec.default_enabled is False

    def test_deep_research_registered_as_removed(self):
        _init_with_overrides({})
        spec = registry.get("deep_research")
        assert spec is not None
        assert spec.stage == FeatureStage.REMOVED
        assert spec.default_enabled is False

    def test_deep_research_override_is_ignored(self):
        fs = _init_with_overrides({"deep_research": True})
        assert not fs.enabled("deep_research")
        assert any("removed" in w.lower() for w in fs.warnings())

    def test_voice_interaction_registered(self):
        _init_with_overrides({})
        spec = registry.get("voice_interaction")
        assert spec is not None
        assert spec.stage == FeatureStage.EXPERIMENTAL
        assert spec.default_enabled is False

    def test_consensus_has_experimental_info(self):
        _init_with_overrides({})
        spec = registry.get("consensus")
        assert spec is not None
        assert spec.experimental_info is not None
        assert spec.experimental_info.name == "Consensus Mode"

    def test_all_gated_features_default_disabled(self):
        """consensus, voice_interaction should be off by default; deep_research is removed."""
        fs = _init_with_overrides({})
        assert not fs.enabled("deep_research")
        assert not fs.enabled("consensus")
        assert not fs.enabled("voice_interaction")

    def test_override_enables_features(self):
        fs = _init_with_overrides(
            {
                "consensus": True,
                "voice_interaction": True,
            }
        )
        assert not fs.enabled("deep_research")
        assert fs.enabled("consensus")
        assert fs.enabled("voice_interaction")

    def test_sanitize_user_overrides_strips_removed_features(self):
        from app.services.features.feature_config_service import sanitize_user_overrides

        _init_with_overrides({})
        cleaned = sanitize_user_overrides(
            {
                "deep_research": True,
                "consensus": True,
            }
        )
        assert "deep_research" not in cleaned
        assert cleaned["consensus"] is True


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
# 3. Action mode gate in orchestrator
# ---------------------------------------------------------------------------


class TestActionModeGate:
    """Test _ACTION_MODE_FEATURE_GATE mapping and logic."""

    def test_gate_mapping_has_deep_research(self):
        from app.services.agent.stream_session.orchestrator import (
            _ACTION_MODE_FEATURE_GATE,
        )

        assert "deep_research" in _ACTION_MODE_FEATURE_GATE
        assert _ACTION_MODE_FEATURE_GATE["deep_research"] == "deep_research"

    def test_gate_mapping_has_consensus(self):
        from app.services.agent.stream_session.orchestrator import (
            _ACTION_MODE_FEATURE_GATE,
        )

        assert "consensus" in _ACTION_MODE_FEATURE_GATE
        assert _ACTION_MODE_FEATURE_GATE["consensus"] == "consensus"

    def test_fast_mode_not_gated(self):
        from app.services.agent.stream_session.orchestrator import (
            _ACTION_MODE_FEATURE_GATE,
        )

        assert "fast" not in _ACTION_MODE_FEATURE_GATE

    def test_agent_mode_not_gated(self):
        from app.services.agent.stream_session.orchestrator import (
            _ACTION_MODE_FEATURE_GATE,
        )

        assert "agent" not in _ACTION_MODE_FEATURE_GATE

    def test_none_mode_not_gated(self):
        from app.services.agent.stream_session.orchestrator import (
            _ACTION_MODE_FEATURE_GATE,
        )

        assert _ACTION_MODE_FEATURE_GATE.get(None or "") is None
        assert _ACTION_MODE_FEATURE_GATE.get("") is None


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
    async def test_experimental_list_excludes_deep_research(self, async_client: AsyncClient):
        _init_with_overrides({"deep_research": True, "consensus": True})
        response = await async_client.get("/api/v1/features/experimental")
        assert response.status_code == 200
        payload = response.json()
        keys = [item["key"] for item in payload.get("features", []) if isinstance(item, dict)]
        assert "deep_research" not in keys
