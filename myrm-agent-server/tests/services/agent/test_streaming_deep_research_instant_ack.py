"""Tests for Deep Research streaming instant ack progress event.

Verifies that ai_deep_research_service_stream yields an immediate progress
event (status=started, progress_pct=5) before creating the orchestrator,
matching the General Agent pattern.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.streaming import ai_deep_research_service_stream


@pytest.mark.asyncio
async def test_deep_research_stream_yields_instant_ack_progress() -> None:
    """First non-budget event must be progress with status=started."""
    mock_llm = MagicMock()

    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.budget.enforcer.reset_session_budget",
        ),
        patch(
            "myrm_agent_harness.agent.deep_research.DeepResearchOrchestrator",
        ) as mock_orch_cls,
    ):
        mock_orch = MagicMock()

        async def _empty_run(**kwargs):  # type: ignore[no-untyped-def]
            return
            yield  # make it an async generator

        mock_orch.run = _empty_run
        mock_orch_cls.return_value = mock_orch

        events: list[dict[str, object]] = []
        async for event in ai_deep_research_service_stream(
            llm=mock_llm,
            query="test query",
            message_id="msg-test",
            context={"session_id": "test-session"},
        ):
            events.append(event)
            if len(events) >= 2:
                break

    assert len(events) >= 1, "Should yield at least the instant ack progress event"
    first = events[0]
    assert first["type"] == "progress", f"First event type should be 'progress', got '{first['type']}'"
    data = first["data"]
    assert isinstance(data, dict)
    assert data["status"] == "started"
    assert data["progress_pct"] == 5


@pytest.mark.asyncio
async def test_deep_research_budget_blocked_skips_progress() -> None:
    """When budget is blocked, progress event should NOT be yielded."""
    mock_llm = MagicMock()

    with patch(
        "app.services.budget.enforcer.should_block_execution",
        new_callable=AsyncMock,
        return_value=True,
    ):
        events = [
            event
            async for event in ai_deep_research_service_stream(
                llm=mock_llm,
                query="test query",
                message_id="msg-test",
            )
        ]

    assert len(events) == 2
    assert events[0]["type"] == "message"
    assert events[1]["type"] == "message_end"
    assert events[1]["completion_status"] == "budget_blocked"
    progress_events = [e for e in events if e.get("type") == "progress"]
    assert len(progress_events) == 0, "Budget-blocked should not yield progress event"
