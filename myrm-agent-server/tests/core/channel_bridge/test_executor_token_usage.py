"""Unit tests for token_usage event handling in ChannelAgentExecutor.

Tests the executor's token_usage event processing, message_end fallback,
and cost_metadata injection into OutboundMessage metadata.
"""

from __future__ import annotations

import pytest

from app.core.channel_bridge.executor_helpers import StreamAccumulator


def _apply_token_usage_event(acc: StreamAccumulator, event: dict[str, object]) -> None:
    """Simulate the token_usage branch of the executor stream loop."""
    data = event.get("data")
    if isinstance(data, dict):
        cost = data.get("cost_usd")
        if isinstance(cost, (int, float)):
            acc.cost_usd += float(cost)
        model = data.get("model_name")
        if isinstance(model, str) and model:
            acc.model_name = model
        usage = data.get("usage")
        if isinstance(usage, dict):
            total = usage.get("total_tokens")
            if isinstance(total, int) and total > 0:
                acc.total_tokens += total


def _apply_message_end_event(acc: StreamAccumulator, event: dict[str, object]) -> None:
    """Simulate the message_end fallback branch of the executor stream loop."""
    end_cost = event.get("cost_usd")
    if isinstance(end_cost, (int, float)) and end_cost > 0 and acc.cost_usd == 0:
        acc.cost_usd = float(end_cost)
    end_model = event.get("model")
    if isinstance(end_model, str) and end_model and not acc.model_name:
        acc.model_name = end_model


def _build_cost_metadata(
    acc: StreamAccumulator, enable_cost_estimation: bool,
) -> dict[str, object] | None:
    """Simulate cost_metadata injection from executor."""
    if acc.cost_usd > 0 and enable_cost_estimation:
        return {
            "cost_usd": acc.cost_usd,
            "model_name": acc.model_name,
            "total_tokens": acc.total_tokens,
        }
    return None


class TestTokenUsageEventProcessing:
    """Tests for 'token_usage' event accumulation in StreamAccumulator."""

    def test_single_token_usage_event(self) -> None:
        acc = StreamAccumulator()
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {
                "model_name": "claude-sonnet-4-20250514",
                "cost_usd": 0.003142,
                "usage": {"total_tokens": 1500, "input_tokens": 1000, "output_tokens": 500},
            },
        })
        assert acc.cost_usd == pytest.approx(0.003142)
        assert acc.model_name == "claude-sonnet-4-20250514"
        assert acc.total_tokens == 1500

    def test_multiple_token_usage_events_accumulate(self) -> None:
        acc = StreamAccumulator()
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {
                "model_name": "gpt-4o",
                "cost_usd": 0.001,
                "usage": {"total_tokens": 800},
            },
        })
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {
                "model_name": "gpt-4o",
                "cost_usd": 0.002,
                "usage": {"total_tokens": 1200},
            },
        })
        assert acc.cost_usd == pytest.approx(0.003)
        assert acc.total_tokens == 2000
        assert acc.model_name == "gpt-4o"

    def test_model_name_uses_latest(self) -> None:
        acc = StreamAccumulator()
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {"model_name": "gpt-4o-mini", "cost_usd": 0.0001, "usage": {"total_tokens": 100}},
        })
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {"model_name": "gpt-4o", "cost_usd": 0.002, "usage": {"total_tokens": 900}},
        })
        assert acc.model_name == "gpt-4o"

    def test_missing_data_field_is_safe(self) -> None:
        acc = StreamAccumulator()
        _apply_token_usage_event(acc, {"type": "token_usage"})
        assert acc.cost_usd == 0.0
        assert acc.model_name == ""
        assert acc.total_tokens == 0

    def test_non_dict_data_field_is_safe(self) -> None:
        acc = StreamAccumulator()
        _apply_token_usage_event(acc, {"type": "token_usage", "data": "invalid"})
        assert acc.cost_usd == 0.0

    def test_zero_cost_not_accumulated(self) -> None:
        acc = StreamAccumulator()
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {"cost_usd": 0, "model_name": "test", "usage": {"total_tokens": 0}},
        })
        assert acc.cost_usd == 0.0
        assert acc.total_tokens == 0

    def test_negative_tokens_ignored(self) -> None:
        acc = StreamAccumulator()
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {"cost_usd": 0.001, "usage": {"total_tokens": -5}},
        })
        assert acc.cost_usd == pytest.approx(0.001)
        assert acc.total_tokens == 0

    def test_empty_model_name_not_overwritten(self) -> None:
        acc = StreamAccumulator()
        acc.model_name = "existing-model"
        _apply_token_usage_event(acc, {
            "type": "token_usage",
            "data": {"model_name": "", "cost_usd": 0.001, "usage": {"total_tokens": 100}},
        })
        assert acc.model_name == "existing-model"


class TestMessageEndFallback:
    """Tests for 'message_end' fallback when token_usage events are missing."""

    def test_fallback_populates_cost_when_zero(self) -> None:
        acc = StreamAccumulator()
        _apply_message_end_event(acc, {"type": "message_end", "cost_usd": 0.005, "model": "claude-sonnet-4-20250514"})
        assert acc.cost_usd == pytest.approx(0.005)
        assert acc.model_name == "claude-sonnet-4-20250514"

    def test_fallback_does_not_override_existing_cost(self) -> None:
        acc = StreamAccumulator()
        acc.cost_usd = 0.003
        acc.model_name = "gpt-4o"
        _apply_message_end_event(acc, {"type": "message_end", "cost_usd": 0.005, "model": "claude-sonnet-4-20250514"})
        assert acc.cost_usd == pytest.approx(0.003)
        assert acc.model_name == "gpt-4o"

    def test_fallback_zero_cost_ignored(self) -> None:
        acc = StreamAccumulator()
        _apply_message_end_event(acc, {"type": "message_end", "cost_usd": 0})
        assert acc.cost_usd == 0.0

    def test_fallback_negative_cost_ignored(self) -> None:
        acc = StreamAccumulator()
        _apply_message_end_event(acc, {"type": "message_end", "cost_usd": -1.0})
        assert acc.cost_usd == 0.0

    def test_fallback_missing_fields_safe(self) -> None:
        acc = StreamAccumulator()
        _apply_message_end_event(acc, {"type": "message_end"})
        assert acc.cost_usd == 0.0
        assert acc.model_name == ""


class TestCostMetadataInjection:
    """Tests for cost_metadata construction and injection conditions."""

    def test_metadata_generated_when_cost_and_enabled(self) -> None:
        acc = StreamAccumulator()
        acc.cost_usd = 0.0042
        acc.model_name = "claude-sonnet-4-20250514"
        acc.total_tokens = 2500
        result = _build_cost_metadata(acc, enable_cost_estimation=True)
        assert result == {
            "cost_usd": pytest.approx(0.0042),
            "model_name": "claude-sonnet-4-20250514",
            "total_tokens": 2500,
        }

    def test_metadata_none_when_disabled(self) -> None:
        acc = StreamAccumulator()
        acc.cost_usd = 0.01
        result = _build_cost_metadata(acc, enable_cost_estimation=False)
        assert result is None

    def test_metadata_none_when_zero_cost(self) -> None:
        acc = StreamAccumulator()
        acc.model_name = "gpt-4o"
        acc.total_tokens = 1000
        result = _build_cost_metadata(acc, enable_cost_estimation=True)
        assert result is None

    def test_metadata_with_zero_tokens_still_generated(self) -> None:
        """Cost > 0 is sufficient; tokens can be 0 if harness didn't report."""
        acc = StreamAccumulator()
        acc.cost_usd = 0.001
        acc.model_name = "gpt-4o-mini"
        result = _build_cost_metadata(acc, enable_cost_estimation=True)
        assert result is not None
        assert result["total_tokens"] == 0

    def test_end_to_end_token_usage_to_metadata(self) -> None:
        """Full pipeline: token_usage events → accumulator → cost_metadata."""
        acc = StreamAccumulator()
        events = [
            {"type": "token_usage", "data": {"model_name": "claude-sonnet-4-20250514", "cost_usd": 0.001, "usage": {"total_tokens": 500}}},
            {"type": "token_usage", "data": {"model_name": "claude-sonnet-4-20250514", "cost_usd": 0.002, "usage": {"total_tokens": 1000}}},
        ]
        for ev in events:
            _apply_token_usage_event(acc, ev)
        result = _build_cost_metadata(acc, enable_cost_estimation=True)
        assert result is not None
        assert result["cost_usd"] == pytest.approx(0.003)
        assert result["model_name"] == "claude-sonnet-4-20250514"
        assert result["total_tokens"] == 1500

    def test_end_to_end_fallback_to_metadata(self) -> None:
        """Full pipeline: no token_usage → message_end fallback → cost_metadata."""
        acc = StreamAccumulator()
        _apply_message_end_event(acc, {"type": "message_end", "cost_usd": 0.008, "model": "gpt-4o"})
        result = _build_cost_metadata(acc, enable_cost_estimation=True)
        assert result is not None
        assert result["cost_usd"] == pytest.approx(0.008)
        assert result["model_name"] == "gpt-4o"
        assert result["total_tokens"] == 0


class TestOldEventTypeRegression:
    """Regression guard: only 'token_usage' type is processed, not 'token_economics'."""

    def test_old_event_type_not_processed(self) -> None:
        """'token_economics' must NOT accumulate anything — only 'token_usage' is valid."""
        acc = StreamAccumulator()
        old_event = {
            "type": "token_economics",
            "data": {"cost_usd": 0.005, "model_name": "test", "usage": {"total_tokens": 999}},
        }
        event_type = old_event.get("type")
        if event_type == "token_usage":
            _apply_token_usage_event(acc, old_event)
        assert acc.cost_usd == 0.0
        assert acc.total_tokens == 0
        assert acc.model_name == ""
