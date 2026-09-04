"""Tests for Continual session overlay graduation service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.continual.overlay import (
    OverlayScope,
    OverlayShellType,
    SessionOverlay,
)
from app.services.continual.session_overlay_service import (
    graduate_session_overlay_to_growth,
)


@pytest.mark.asyncio
async def test_graduate_session_overlay_to_growth_success() -> None:
    """Test successful graduation of an overlay into a persisted growth record."""
    overlay = SessionOverlay(
        overlay_id="cso_test123",
        scope=OverlayScope.SESSION,
        target_type=OverlayShellType.SUBAGENT_CONFIG,
        target_name="stripe_charges",
        patch_payload={
            "tool_name": "stripe_charges",
            "advisory_instruction": "Use small batches for Stripe charges to avoid 429.",
        },
        failure_signature="RateLimit 429 on stripe_charges",
    )

    with patch(
        "app.services.continual.session_overlay_service.persist_skill_draft_record",
        new=AsyncMock(return_value="rec_999"),
    ) as mock_persist:
        record_id = await graduate_session_overlay_to_growth(
            overlay,
            user_id="user_123",
            chat_id="chat_456",
        )
        assert record_id == "rec_999"
        mock_persist.assert_called_once()
        _, kwargs = mock_persist.call_args
        assert kwargs["user_id"] == "user_123"
        assert kwargs["action_type"] == "continual_subagent_config"
        assert kwargs["payload"]["source"] == "continual"
        assert "stripe_charges" in kwargs["payload"]["skill_name"]


@pytest.mark.asyncio
async def test_graduate_session_overlay_to_growth_failure_handled() -> None:
    """Test exception in persist_skill_draft_record is safely caught and returns None."""
    overlay = SessionOverlay(
        overlay_id="cso_err",
        scope=OverlayScope.SESSION,
        target_type=OverlayShellType.PROMPT_PATCH,
        target_name="global",
        patch_payload={},
        failure_signature="General failure",
    )

    with patch(
        "app.services.continual.session_overlay_service.persist_skill_draft_record",
        new=AsyncMock(side_effect=RuntimeError("DB disconnected")),
    ):
        record_id = await graduate_session_overlay_to_growth(
            overlay,
            user_id="user_123",
        )
        assert record_id is None
