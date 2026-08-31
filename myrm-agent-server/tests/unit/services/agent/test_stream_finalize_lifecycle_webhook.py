"""Unit tests for session lifecycle outbound webhook event publishing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase

from app.services.agent.stream_session.stream_finalize import (
    _publish_session_lifecycle_webhook_event,
)
from app.services.event.app_event_bus import AppEventType


def test_publish_session_completed_event() -> None:
    with patch("app.services.event.app_event_bus.get_event_bus") as mock_get_bus:
        bus = MagicMock()
        mock_get_bus.return_value = bus

        _publish_session_lifecycle_webhook_event(
            chat_id="chat-123",
            phase=RunDigestPhase.COMPLETED,
            agent_id="agent-abc",
            was_cancelled=False,
            had_fatal_error=False,
        )

        bus.publish.assert_called_once()
        event = bus.publish.call_args[0][0]
        assert event.event_type == AppEventType.SESSION_COMPLETED
        assert event.data["chat_id"] == "chat-123"
        assert event.data["agent_id"] == "agent-abc"
        assert event.data["phase"] == "completed"


def test_publish_session_failed_event_on_error_phase() -> None:
    with patch("app.services.event.app_event_bus.get_event_bus") as mock_get_bus:
        bus = MagicMock()
        mock_get_bus.return_value = bus

        _publish_session_lifecycle_webhook_event(
            chat_id="chat-456",
            phase=RunDigestPhase.ERROR,
            agent_id=None,
            was_cancelled=False,
            had_fatal_error=True,
        )

        bus.publish.assert_called_once()
        event = bus.publish.call_args[0][0]
        assert event.event_type == AppEventType.SESSION_FAILED
        assert event.data["phase"] == "error"
        assert event.data["had_fatal_error"] is True
