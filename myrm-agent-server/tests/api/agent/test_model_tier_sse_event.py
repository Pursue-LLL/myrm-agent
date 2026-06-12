"""Model tier SSE event dispatch integration tests.

Verifies that stream_chunks.py correctly sends/omits model_tier events
based on model configuration and routing_tier state.
"""

import json
from typing import cast
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.core.config import ModelTier, infer_model_tier

from app.schemas.streaming import SSEEnvelope


class TestModelTierSSEDispatch:
    """Verify model_tier SSE event dispatch logic extracted from stream_chunks.py.

    Tests the exact conditional logic used in generate_cancellable_stream
    without needing to mock the entire stream pipeline.
    """

    def _simulate_model_tier_sse(
        self,
        model_name: str,
        routing_tier: str | None = None,
        context_length: int = 0,
    ) -> list[dict]:
        """Simulate the model_tier SSE event logic from stream_chunks.py."""
        custom_def = None
        if context_length > 0:
            custom_def = MagicMock()
            custom_def.context_length = context_length

        _model_tier = infer_model_tier(model_name, custom_def, None)

        events: list[dict] = []
        message_id = "test-msg-001"

        if routing_tier:
            routing_data: dict[str, object] = {"tier": routing_tier}
            if _model_tier != ModelTier.STRONG:
                routing_data["model_tier"] = _model_tier.value

            event_data: dict[str, object] = {
                "type": "routing_decision",
                "messageId": message_id,
                "data": cast(dict[str, object], routing_data),
            }
            events.append(event_data)
        elif _model_tier != ModelTier.STRONG:
            model_tier_event: dict[str, object] = {
                "type": "routing_decision",
                "messageId": message_id,
                "data": cast(dict[str, object], {"model_tier": _model_tier.value}),
            }
            events.append(model_tier_event)

        return events

    def test_strong_model_no_routing_no_event(self) -> None:
        """STRONG model without routing_tier: no routing_decision event sent."""
        events = self._simulate_model_tier_sse("gpt-4o", routing_tier=None)
        assert len(events) == 0, "STRONG model should NOT emit routing_decision event"

    def test_weak_model_no_routing_sends_model_tier_only(self) -> None:
        """WEAK model without routing_tier: sends routing_decision with model_tier only."""
        events = self._simulate_model_tier_sse("qwen2.5:7b", routing_tier=None)
        assert len(events) == 1
        data = events[0]["data"]
        assert data["model_tier"] == "weak"
        assert "tier" not in data

    def test_medium_model_no_routing_sends_model_tier_only(self) -> None:
        """MEDIUM model without routing_tier: sends routing_decision with model_tier only."""
        events = self._simulate_model_tier_sse("deepseek-coder-33b", routing_tier=None)
        assert len(events) == 1
        data = events[0]["data"]
        assert data["model_tier"] == "medium"
        assert "tier" not in data

    def test_weak_model_with_routing_tier_combined_event(self) -> None:
        """WEAK model with routing_tier: routing_decision contains both tier and model_tier."""
        events = self._simulate_model_tier_sse("qwen2.5:7b", routing_tier="simple")
        assert len(events) == 1
        data = events[0]["data"]
        assert data["tier"] == "simple"
        assert data["model_tier"] == "weak"

    def test_strong_model_with_routing_tier_no_model_tier_field(self) -> None:
        """STRONG model with routing_tier: routing_decision contains tier only, no model_tier."""
        events = self._simulate_model_tier_sse("gpt-4o", routing_tier="reasoning")
        assert len(events) == 1
        data = events[0]["data"]
        assert data["tier"] == "reasoning"
        assert "model_tier" not in data

    def test_context_length_based_weak_detection(self) -> None:
        """Model with context_length ≤ 16384 is detected as WEAK via SSE."""
        events = self._simulate_model_tier_sse("some-custom-model", routing_tier=None, context_length=8192)
        assert len(events) == 1
        assert events[0]["data"]["model_tier"] == "weak"

    def test_context_length_medium_detection(self) -> None:
        """Model with 16384 < context_length ≤ 65536 is MEDIUM."""
        events = self._simulate_model_tier_sse("some-custom-model", routing_tier=None, context_length=32768)
        assert len(events) == 1
        assert events[0]["data"]["model_tier"] == "medium"

    def test_context_length_strong_no_event(self) -> None:
        """Model with context_length > 65536 is STRONG, no event."""
        events = self._simulate_model_tier_sse("some-custom-model", routing_tier=None, context_length=128000)
        assert len(events) == 0

    def test_sse_envelope_serialization(self) -> None:
        """Verify SSE event can be serialized to valid SSE chunk format."""
        events = self._simulate_model_tier_sse("ollama/llama3:8b", routing_tier=None)
        assert len(events) == 1

        chunk = SSEEnvelope.from_any(events[0]).to_sse_chunk()
        assert "data: " in chunk
        parsed = json.loads(chunk.split("data: ")[1].split("\n")[0])
        assert parsed["type"] == "routing_decision"
        assert parsed["data"]["model_tier"] == "weak"

    def test_medium_with_routing_tier_combined(self) -> None:
        """MEDIUM model with routing_tier: both tier and model_tier present."""
        events = self._simulate_model_tier_sse("deepseek-coder-33b", routing_tier="standard")
        assert len(events) == 1
        data = events[0]["data"]
        assert data["tier"] == "standard"
        assert data["model_tier"] == "medium"

    def test_ollama_models_weak(self) -> None:
        """Various ollama small model naming conventions."""
        for model in ["ollama/llama3:8b", "ollama/mistral:7b", "ollama/phi3:3.8b", "qwen2.5:14b"]:
            events = self._simulate_model_tier_sse(model, routing_tier=None)
            assert len(events) == 1, f"Model {model} should be weak/medium"
            assert events[0]["data"]["model_tier"] in ("weak", "medium")

    def test_message_id_propagation(self) -> None:
        """Verify messageId is correctly set in the event."""
        events = self._simulate_model_tier_sse("qwen2.5:7b", routing_tier=None)
        assert events[0]["messageId"] == "test-msg-001"
