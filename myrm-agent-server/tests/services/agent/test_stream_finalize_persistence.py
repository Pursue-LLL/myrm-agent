"""Verify what finalize_agent_stream_session persists and emits for a finished turn."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_finalize import (
    finalize_agent_stream_session,
)
from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
)


def _make_session(content: str = "Result text", has_persistable_turn: bool = False) -> MagicMock:
    session = MagicMock()
    session.request = MagicMock()
    session.request.chat_id = "chat-finalize-1"
    session.request.use_workflow = False
    session.request.timezone = "UTC"
    session.request.resume_value = None
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "msg-test"
    session.params.enable_skill_manage = False
    session.params.model_cfg = MagicMock()
    session.params.locale = "en"
    session.collector = MagicMock()
    session.collector.has_persistable_turn = has_persistable_turn
    session.collector.has_content = True
    session.collector.content = content
    session.collector.extra_data = {}
    session.collector._progress_steps = [{}] * 3
    session.collector.sibling_group_id = None
    session.collector.has_pending_hitl_replay = MagicMock(return_value=False)
    session.collector.cleanup = MagicMock()
    session.extra_context = {}
    session.stream_ttft_ms = None
    session.had_fatal_error = False
    return session


def _make_approval() -> ApprovalTimeoutHolder:
    holder = ApprovalTimeoutHolder()
    return holder


def _make_clarification() -> ClarificationTimeoutHolder:
    return ClarificationTimeoutHolder()


@pytest.mark.asyncio
async def test_finalize_persists_memory_budget_without_citations() -> None:
    """memoryBudget must persist even when no citations were emitted."""
    session = _make_session(content="Result without citation tags", has_persistable_turn=True)
    session.extra_context = {"memory_brief_preview": {"snapshot_id": "snap-budget"}}

    with (
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
        patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
        patch("app.services.agent.goals.goal_registry.GoalRegistry"),
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value={"used": 64, "total": 512},
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value=None,
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval(), _make_clarification())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("memoryBudget") == {"used": 64, "total": 512}
    assert "citations" not in persisted_extra


@pytest.mark.asyncio
async def test_finalize_citations_preserve_first_seen_order() -> None:
    """Persisted citations should be de-duplicated in first-seen order."""
    session = _make_session(
        content="alpha <cite:doc-b> beta <cite:doc-a> gamma <cite:doc-b>",
        has_persistable_turn=True,
    )
    session.extra_context = {}

    with (
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
        patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
        patch("app.services.agent.goals.goal_registry.GoalRegistry"),
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value=None,
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval(), _make_clarification())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("citations") == ["doc-b", "doc-a"]


@pytest.mark.asyncio
async def test_finalize_persists_memory_brief_status_payload() -> None:
    """Memory brief snapshot/status should be persisted for chat reload."""
    session = _make_session(content="Result without citation tags", has_persistable_turn=True)
    session.extra_context = {
        "memory_brief_preview": {"snapshot_id": "snap-xyz"},
        "memory_brief_status": {"state": "skipped", "reason": "timeout"},
    }

    with (
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
        patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
        patch("app.services.agent.goals.goal_registry.GoalRegistry"),
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value={"used": 12, "total": 256},
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value={"state": "applied", "source": "fallback"},
        ),
        patch("app.services.agent.stream_session.stream_finalize.observe_memory_brief_status_payload") as mock_observe_status,
        patch(
            "app.services.agent.stream_session.stream_finalize.enqueue_memory_brief_status_telemetry"
        ) as mock_enqueue_status_telemetry,
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval(), _make_clarification())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("memoryBriefSnapshotId") == "snap-xyz"
    assert persisted_extra.get("memoryBriefStatus") == {
        "state": "skipped",
        "source": "preflight",
        "reason": "timeout",
        "injection": {"state": "applied", "source": "fallback"},
    }
    mock_observe_status.assert_called_once_with(
        phase="persist",
        payload={
            "state": "skipped",
            "source": "preflight",
            "reason": "timeout",
            "injection": {"state": "applied", "source": "fallback"},
        },
    )
    mock_enqueue_status_telemetry.assert_called_once_with(
        phase="persist",
        payload={
            "state": "skipped",
            "source": "preflight",
            "reason": "timeout",
            "injection": {"state": "applied", "source": "fallback"},
        },
    )


@pytest.mark.asyncio
async def test_finalize_skips_invalid_memory_budget_payload() -> None:
    """Invalid memory budget payload should not leak into persisted metadata."""
    session = _make_session(content="Result without citation tags", has_persistable_turn=True)
    session.extra_context = {"memory_brief_status": {"state": "ready"}}

    with (
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
        patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
        patch("app.services.agent.goals.goal_registry.GoalRegistry"),
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value=None,
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval(), _make_clarification())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert "memoryBudget" not in persisted_extra
    assert persisted_extra.get("memoryBriefStatus") == {"state": "ready"}


@pytest.mark.asyncio
async def test_finalize_persists_not_applied_injection_reason() -> None:
    session = _make_session(content="Result without citation tags", has_persistable_turn=True)
    session.extra_context = {
        "memory_brief_status": {"state": "skipped", "reason": "timeout"},
    }

    with (
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
        patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
        patch("app.services.agent.goals.goal_registry.GoalRegistry"),
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value={"used": 9, "total": 64},
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value={"state": "not_applied", "reason": "already_present"},
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval(), _make_clarification())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("memoryBriefStatus") == {
        "state": "skipped",
        "source": "preflight",
        "reason": "timeout",
        "injection": {"state": "not_applied", "reason": "already_present"},
    }


@pytest.mark.asyncio
async def test_finalize_emits_injection_status_when_brief_status_missing() -> None:
    session = _make_session(content="Result without citation tags", has_persistable_turn=True)
    session.extra_context = {}

    with (
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
        patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
        patch("app.services.agent.goals.goal_registry.GoalRegistry"),
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            return_value={"used": 5, "total": 50},
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value={"state": "not_applied", "reason": "missing_context"},
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval(), _make_clarification())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert persisted_extra.get("memoryBudget") == {"used": 5, "total": 50}
    assert persisted_extra.get("memoryBriefStatus") == {
        "state": "skipped",
        "source": "runtime_fallback",
        "injection": {"state": "not_applied", "reason": "missing_context"},
    }


@pytest.mark.asyncio
async def test_finalize_keeps_injection_status_when_budget_hook_fails() -> None:
    session = _make_session(content="Result without citation tags", has_persistable_turn=True)
    session.extra_context = {"memory_brief_status": {"state": "skipped", "reason": "timeout"}}

    with (
        patch("app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"),
        patch("app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"),
        patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
        patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
        patch("app.services.agent.goals.goal_registry.GoalRegistry"),
        patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
        patch(
            "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
            return_value=None,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
            side_effect=RuntimeError("budget boom"),
        ),
        patch(
            "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
            return_value={"state": "not_applied", "reason": "already_present"},
        ),
    ):
        mock_ctx.reset = MagicMock()
        await finalize_agent_stream_session(session, MagicMock(), _make_approval(), _make_clarification())

    persisted_extra = mock_persist.await_args.kwargs["extra_data"]
    assert "memoryBudget" not in persisted_extra
    assert persisted_extra.get("memoryBriefStatus") == {
        "state": "skipped",
        "source": "preflight",
        "reason": "timeout",
        "injection": {"state": "not_applied", "reason": "already_present"},
    }
