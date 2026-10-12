"""Tests for the harness idle-task event forwarder started by ``start_idle_task_listeners``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.runtime.events.idle_events import IdleTaskProgressEvent

from app.lifecycle.system import start_idle_task_listeners
from app.services.event.app_event_bus import AppEventType

IdleForwarder = Callable[[IdleTaskProgressEvent], Awaitable[None]]


async def _start_forwarder() -> tuple[IdleForwarder, MagicMock]:
    """Start the listeners against mock buses and return the registered forwarder and server bus."""
    harness_bus = MagicMock()
    server_bus = MagicMock()
    with (
        patch("myrm_agent_harness.runtime.events.bus.get_event_bus", return_value=harness_bus),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=server_bus),
    ):
        await start_idle_task_listeners()

    harness_bus.subscribe.assert_called_once()
    event_type, forwarder = harness_bus.subscribe.call_args.args
    assert event_type is IdleTaskProgressEvent
    return forwarder, server_bus


@pytest.mark.asyncio
async def test_forwards_structural_idle_status_without_localized_text() -> None:
    forwarder, server_bus = await _start_forwarder()

    await forwarder(
        IdleTaskProgressEvent(
            session_id="s1",
            status="working",
            task_name="cognitive_derivation",
            progress_pct=40,
            data={"count": 2},
        )
    )

    server_bus.publish.assert_called_once()
    forwarded = server_bus.publish.call_args.args[0]
    assert forwarded.event_type is AppEventType.IDLE_STATUS
    assert forwarded.data == {
        "session_id": "s1",
        "status": "working",
        "task_name": "cognitive_derivation",
        "progress_pct": 40,
        "data": {"count": 2},
    }


@pytest.mark.asyncio
async def test_completed_idle_task_does_not_create_notification() -> None:
    """Routine idle completions are not user-actionable: no inbox row, no web push or IM fan-out."""
    forwarder, server_bus = await _start_forwarder()

    with patch("app.database.connection.get_session") as mock_get_session:
        await forwarder(
            IdleTaskProgressEvent(
                session_id="s1",
                status="completed",
                task_name="cognitive_consolidation",
                progress_pct=100,
                data={"consolidated": 3},
            )
        )

    mock_get_session.assert_not_called()
    published_types = [call.args[0].event_type for call in server_bus.publish.call_args_list]
    assert published_types == [AppEventType.IDLE_STATUS]


@pytest.mark.asyncio
async def test_completed_session_evidence_routes_captured_proposal_to_growth_lifecycle() -> None:
    forwarder, server_bus = await _start_forwarder()
    proposal = {
        "skill_id": "error_handling_v1",
        "reasoning": "Learned from repeated failures",
        "proposed_content": "# Skill",
        "score": 0.85,
        "agent_id": "agent_1",
        "chat_id": "chat_42",
    }

    with patch(
        "app.services.skills.growth.lifecycle.process_skill_review_result",
        new_callable=AsyncMock,
    ) as mock_process:
        await forwarder(
            IdleTaskProgressEvent(
                session_id="s1",
                status="completed",
                task_name="session_evidence_extraction",
                progress_pct=100,
                data={"proposal": proposal},
            )
        )

    mock_process.assert_awaited_once_with(
        {
            "type": "skill_draft",
            "has_value": True,
            "skill_name": "error_handling_v1",
            "skill_description": "Learned from repeated failures",
            "content": "# Skill",
            "score": 0.85,
            "agent_id": "agent_1",
            "chat_id": "chat_42",
        }
    )
    assert [call.args[0].event_type for call in server_bus.publish.call_args_list] == [AppEventType.IDLE_STATUS]


@pytest.mark.asyncio
async def test_captured_proposal_with_skip_form_is_not_routed() -> None:
    forwarder, _ = await _start_forwarder()

    with patch(
        "app.services.skills.growth.lifecycle.process_skill_review_result",
        new_callable=AsyncMock,
    ) as mock_process:
        await forwarder(
            IdleTaskProgressEvent(
                session_id="s1",
                status="completed",
                task_name="session_evidence_extraction",
                data={"proposal": {"skill_id": "x", "recommended_form": "skip"}},
            )
        )

    mock_process.assert_not_awaited()
