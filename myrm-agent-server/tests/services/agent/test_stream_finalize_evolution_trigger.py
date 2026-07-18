"""Verify skill evolution trigger integration in finalize_agent_stream_session.

The finalize hook fires `trigger_skill_evolution` as fire-and-forget when the
stream produced content and tool steps were used (or DW mode streamed output).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_finalize import finalize_agent_stream_session
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder


def _make_session(
    chat_id: str | None = "chat-evo-1",
    has_content: bool = True,
    use_workflow: bool = False,
    tool_steps: int = 3,
    content: str = "Result text",
    is_cancelled: bool = False,
) -> MagicMock:
    session = MagicMock()
    session.request = MagicMock()
    session.request.chat_id = chat_id
    session.request.use_workflow = use_workflow
    session.request.timezone = "UTC"
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = is_cancelled
    session.params = MagicMock()
    session.params.message_id = "msg-test"
    session.params.model_cfg = MagicMock()
    session.params.locale = "en"
    session.collector = MagicMock()
    session.collector.has_content = has_content
    session.collector.content = content
    session.collector.extra_data = {}
    session.collector._progress_steps = [{}] * tool_steps
    session.collector.sibling_group_id = None
    session.collector.cleanup = MagicMock()
    session.monitor = MagicMock()
    session.monitor.stop = AsyncMock()
    return session


def _make_approval() -> ApprovalTimeoutHolder:
    holder = ApprovalTimeoutHolder()
    return holder


@pytest.mark.asyncio
async def test_evolution_triggered_when_tools_used() -> None:
    """trigger_skill_evolution is called when tool_steps > 0."""
    session = _make_session(tool_steps=5)

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ) as mock_trigger,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    mock_trigger.assert_called_once_with(
        chat_id="chat-evo-1",
        model_cfg=session.params.model_cfg,
        tool_steps_count=5,
        conversation_text=None,
        agent_id=session.request.agent_id,
    )


@pytest.mark.asyncio
async def test_evolution_passes_dw_content_when_workflow() -> None:
    """DW mode passes collector.content as conversation_text."""
    session = _make_session(use_workflow=True, content="DW orchestrated result")

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ) as mock_trigger,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    mock_trigger.assert_called_once_with(
        chat_id="chat-evo-1",
        model_cfg=session.params.model_cfg,
        tool_steps_count=3,
        conversation_text="DW orchestrated result",
        agent_id=session.request.agent_id,
    )


@pytest.mark.asyncio
async def test_evolution_not_triggered_without_content() -> None:
    """No trigger when collector has no content."""
    session = _make_session(has_content=False)

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ) as mock_trigger,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_evolution_not_triggered_without_chat_id() -> None:
    """No trigger when no chat_id."""
    session = _make_session(chat_id=None)

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ) as mock_trigger,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_evolution_trigger_exception_swallowed() -> None:
    """Exceptions in evolution trigger must not break finalize."""
    session = _make_session(tool_steps=2)

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution",
            side_effect=RuntimeError("import broke"),
        ),
    ):
        mock_ctx.reset = MagicMock()
        # Must not raise
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    session.collector.cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_evolution_not_triggered_when_cancelled() -> None:
    """Cancelled streams must not trigger evolution (incomplete task)."""
    session = _make_session(tool_steps=5, is_cancelled=True)

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ) as mock_trigger,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    mock_trigger.assert_not_called()


@pytest.mark.asyncio
async def test_finalize_persists_memory_budget_without_citations() -> None:
    """memoryBudget must persist even when no citations were emitted."""
    session = _make_session(content="Result without citation tags")
    session.extra_context = {"memory_brief_preview": {"snapshot_id": "snap-budget"}}

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value={"used": 64, "total": 512},
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("memoryBudget") == {"used": 64, "total": 512}
    assert "citations" not in persisted_extra


@pytest.mark.asyncio
async def test_finalize_persists_memory_brief_status_payload() -> None:
    """Memory brief snapshot/status should be persisted for chat reload."""
    session = _make_session(content="Result without citation tags")
    session.extra_context = {
        "memory_brief_preview": {"snapshot_id": "snap-xyz"},
        "memory_brief_status": {"state": "skipped", "reason": "timeout"},
    }

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value={"used": 12, "total": 256},
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value={"state": "applied", "source": "fallback"},
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("memoryBriefSnapshotId") == "snap-xyz"
    assert persisted_extra.get("memoryBriefStatus") == {
        "state": "skipped",
        "reason": "timeout",
        "injection": {"state": "applied", "source": "fallback"},
    }


@pytest.mark.asyncio
async def test_finalize_skips_invalid_memory_budget_payload() -> None:
    """Invalid manager budget payload should not leak into persisted metadata."""
    session = _make_session(content="Result without citation tags")
    session.extra_context = {"memory_brief_status": {"state": "ready"}}

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value=None,
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert "memoryBudget" not in persisted_extra
    assert persisted_extra.get("memoryBriefStatus") == {"state": "ready"}


@pytest.mark.asyncio
async def test_finalize_persists_not_applied_injection_reason() -> None:
    session = _make_session(content="Result without citation tags")
    session.extra_context = {
        "memory_brief_status": {"state": "skipped", "reason": "timeout"},
    }

    with (
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.CancellationRegistry"
        ),
        patch(
            "app.services.agent.stream_session.stream_finalize.SteeringRegistry"
        ),
        patch("app.services.agent.goal_registry.GoalRegistry"),
        patch(
            "myrm_agent_harness.agent.security.user_credentials_ctx"
        ) as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_manager",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value={"used": 9, "total": 64},
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value={"state": "not_applied", "reason": "already_present"},
        ),
        patch(
            "app.services.agent.evolution.engine.trigger_skill_evolution"
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("memoryBriefStatus") == {
        "state": "skipped",
        "reason": "timeout",
        "injection": {"state": "not_applied", "reason": "already_present"},
    }
