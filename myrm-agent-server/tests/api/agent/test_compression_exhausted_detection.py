"""Tests for compression exhausted SSE detection in the server layer.

Verifies _is_compression_exhausted correctly parses SSE chunks
to detect context overflow exhaustion signals from the framework layer.
"""

import json
from unittest.mock import patch

import pytest

from app.config.settings import ControlPlaneSettings
from app.services.agent.context_compaction_telemetry import (
    ContextCompactionTelemetryConfig,
    _build_context_compaction_envelope,
)
from app.services.agent.streaming_support.sse_helpers import clear_context_task_metrics, is_compression_exhausted


class TestIsCompressionExhausted:
    """Server-side SSE detection function tests."""

    def test_positive_detection(self):
        event = {
            "type": "error",
            "error": "context_length_exceeded",
            "error_kind": "context_overflow",
            "compression_exhausted": True,
            "messageId": "msg-123",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert is_compression_exhausted(chunk) is True

    def test_normal_error_no_detection(self):
        event = {
            "type": "error",
            "error": "rate limit exceeded",
            "error_kind": "rate_limit",
            "messageId": "msg-123",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert is_compression_exhausted(chunk) is False

    def test_non_error_type_no_detection(self):
        event = {
            "type": "message",
            "compression_exhausted": True,
            "messageId": "msg-123",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert is_compression_exhausted(chunk) is False

    def test_false_flag_no_detection(self):
        event = {
            "type": "error",
            "compression_exhausted": False,
            "messageId": "msg-123",
        }
        chunk = f"data: {json.dumps(event)}\n\n"
        assert is_compression_exhausted(chunk) is False

    def test_invalid_json_no_detection(self):
        assert is_compression_exhausted("data: {broken}\n\n") is False

    def test_non_sse_format_no_detection(self):
        assert is_compression_exhausted("not an sse chunk") is False

    def test_empty_string_no_detection(self):
        assert is_compression_exhausted("") is False

    def test_keyword_present_but_non_sse_prefix(self):
        assert is_compression_exhausted('{"compression_exhausted": true}\n\n') is False

    def test_malformed_json_with_keyword(self):
        assert is_compression_exhausted("data: compression_exhausted {broken}\n\n") is False


class TestClearContextTaskMetrics:
    """Server-side TaskMetrics lifecycle cleanup tests."""

    def test_noop_when_chat_id_missing(self):
        clear_context_task_metrics(None)

    def test_calls_harness_clear_when_chat_id_present(self):
        with patch("myrm_agent_harness.agent.context_management.tracking.task_metrics.clear_task_metrics") as mock_clear:
            clear_context_task_metrics("chat-123")

        mock_clear.assert_called_once_with("chat-123")

    def test_swallow_cleanup_errors(self, caplog: pytest.LogCaptureFixture):
        with patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.clear_task_metrics",
            side_effect=RuntimeError("boom"),
        ):
            clear_context_task_metrics("chat-123")

        assert "Failed to clear context task metrics" in caplog.text


class TestContextCompactionTelemetry:
    """Server-side context compaction telemetry snapshot tests."""

    def test_skip_when_context_not_configured(self, monkeypatch: pytest.MonkeyPatch):
        from app.config.settings import settings

        monkeypatch.setattr(
            settings,
            "control_plane",
            ControlPlaneSettings(),
        )

        config = ContextCompactionTelemetryConfig.from_settings()
        assert config is None

    def test_build_envelope_from_task_metrics_snapshot(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("CONTROL_PLANE_TELEMETRY_SUBJECT", "sandbox-42")
        config = ContextCompactionTelemetryConfig(
            control_plane_url="http://control-plane:8001",
            telemetry_token="secret-token",
            telemetry_subject="sandbox-42",
            batch_size=16,
            flush_interval_seconds=2.0,
            queue_size=256,
        )

        mock_metrics = patch("app.services.agent.context_compaction_telemetry.get_task_metrics")
        with mock_metrics as get_metrics:
            metrics = get_metrics.return_value
            metrics.compression_count = 2
            metrics.to_dict.return_value = {
                "compression_count": 2,
                "total_tokens_saved": 2048,
                "compression_events": [{"dedup_tokens_saved": 128, "integrity_skipped": 1}],
            }

            envelope = _build_context_compaction_envelope("chat-123", config)

        assert envelope is not None
        assert envelope.telemetry_subject == "sandbox-42"
        assert envelope.chat_id == "chat-123"
        assert envelope.snapshot.compression_count == 2
        assert envelope.snapshot.total_tokens_saved == 2048
