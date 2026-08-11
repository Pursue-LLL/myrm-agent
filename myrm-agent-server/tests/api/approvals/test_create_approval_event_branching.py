"""Unit tests for ApprovalRegistry.create_approval event-type branching.

Covers the three-branch event determination introduced by Optimization B:
1. Background growth drafts (no thread_id) must NOT emit SSE from the registry —
   draft_notification owns SKILL_GROWTH_UPDATED / NEW_SKILL_DRAFT for them.
2. PENDING (non-background) approvals emit APPROVAL_REQUIRED.
3. Non-PENDING (resolved) approvals emit SKILL_GROWTH_UPDATED.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.approvals.registry import ApprovalRegistry
from app.services.event.app_event_bus import AppEventType


@pytest.mark.asyncio
async def test_background_growth_draft_skips_sse_emit(client) -> None:
    """Background growth drafts never emit SSE from the registry."""
    bus = MagicMock()
    with patch("app.services.approvals.registry.get_event_bus", return_value=bus):
        record = await ApprovalRegistry.create_approval(
            agent_id="bg_agent",
            action_type="skill_draft",
            payload={"skill_name": "bg", "content": "# x"},
            reason="background growth",
        )

    bus.publish.assert_not_called()
    assert record.status == "PENDING"
    assert record.action_type == "skill_draft"


@pytest.mark.asyncio
async def test_pending_approval_emits_approval_required(client) -> None:
    """Inline PENDING approval emits APPROVAL_REQUIRED."""
    bus = MagicMock()
    with patch("app.services.approvals.registry.get_event_bus", return_value=bus):
        await ApprovalRegistry.create_approval(
            agent_id="inline_agent",
            action_type="tool_call",
            payload={"tool": "read"},
            reason="inline HITL",
            thread_id="thread-123",
        )

    bus.publish.assert_called_once()
    event = bus.publish.call_args.args[0]
    assert event.event_type == AppEventType.APPROVAL_REQUIRED
    assert event.data["action_type"] == "tool_call"
    assert event.data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_resolved_status_emits_skill_growth_updated(client) -> None:
    """Non-PENDING (resolved) approvals emit SKILL_GROWTH_UPDATED."""
    bus = MagicMock()
    with patch("app.services.approvals.registry.get_event_bus", return_value=bus):
        await ApprovalRegistry.create_approval(
            agent_id="growth_agent",
            action_type="skill_draft",
            payload={"skill_name": "resolved", "content": "# y"},
            reason="auto applied",
            thread_id="thread-456",
            status="APPROVED",
        )

    bus.publish.assert_called_once()
    event = bus.publish.call_args.args[0]
    assert event.event_type == AppEventType.SKILL_GROWTH_UPDATED
    assert event.data["status"] == "APPROVED"
