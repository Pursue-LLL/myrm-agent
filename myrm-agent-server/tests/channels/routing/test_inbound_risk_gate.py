"""Tests for inbound risk gate in router.py:_handle_merged."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router import _record_inbound_risk_hits
from app.channels.types import InboundMessage
from app.services.risk.detection import DetectionResult, RiskMatch


def _make_inbound(
    content: str = "hello",
    sender_id: str = "user1",
    channel: str = "test",
    chat_id: str = "chat1",
    is_group: bool = False,
    message_id: str = "msg1",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        message_id=message_id,
        mentioned=False,
    )


def _blocked_result(display_name: str = "API Key Pattern") -> DetectionResult:
    match = RiskMatch(
        rule_id="r1",
        display_name=display_name,
        severity="critical",
        action="block",
        category="security",
        match_summary="sk-proj-abc123",
    )
    return DetectionResult(blocked=True, matches=(match,))


def _safe_result() -> DetectionResult:
    return DetectionResult(blocked=False, matches=())


class TestInboundRiskGateUnit:
    """Unit tests for the inbound risk gate logic extracted from _handle_merged."""

    def test_detect_returns_blocked_for_api_key(self) -> None:
        result = _blocked_result()
        assert result.blocked is True
        assert len(result.matches) == 1
        assert result.matches[0].display_name == "API Key Pattern"

    def test_detect_returns_safe_for_normal_content(self) -> None:
        result = _safe_result()
        assert result.blocked is False
        assert len(result.matches) == 0


class TestRecordInboundRiskHits:
    """Tests for _record_inbound_risk_hits fire-and-forget auditing."""

    @pytest.mark.asyncio
    async def test_records_hits_successfully(self) -> None:
        msg = _make_inbound(content="sk-proj-abc123")
        match = RiskMatch(
            rule_id="r1",
            display_name="API Key",
            severity="critical",
            action="block",
            category="security",
            match_summary="sk-proj-abc123",
        )

        mock_service = MagicMock()
        mock_service.record_hits = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with (
            patch(
                "app.services.risk.detection.get_detection_service",
                return_value=mock_service,
            ),
            patch(
                "app.platform_utils.get_session_factory",
                return_value=mock_factory,
            ),
        ):
            await _record_inbound_risk_hits((match,), msg)

        mock_service.record_hits.assert_called_once()
        call_args = mock_service.record_hits.call_args
        assert call_args.kwargs.get("session_id") == "user1"

    @pytest.mark.asyncio
    async def test_swallows_exception_gracefully(self) -> None:
        msg = _make_inbound(content="sk-proj-abc123")
        match = RiskMatch(
            rule_id="r1",
            display_name="API Key",
            severity="critical",
            action="block",
            category="security",
            match_summary="sk-proj-abc123",
        )

        with patch(
            "app.platform_utils.get_session_factory",
            side_effect=RuntimeError("DB unavailable"),
        ):
            await _record_inbound_risk_hits((match,), msg)
