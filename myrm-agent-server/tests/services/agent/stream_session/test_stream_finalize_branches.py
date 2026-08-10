"""Cover remaining branch paths in finalize_agent_stream_session.

These tests exercise timeout scheduling, compaction debt drain, residual slice
flush, artifact patching, turn-capability terminal recording and the failure
fallbacks of the persistence hooks. They complement
test_stream_finalize_evolution_trigger.py and test_stream_finalize_queue_timeout.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.params.models import TurnCapabilityTelemetryRequest
from app.services.agent.stream_session.stream_finalize import (
    finalize_agent_stream_session,
)
from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    ClarificationTimeoutHolder,
)
from app.services.copilot.run_digest_store import RunDigestPhase


def _make_session(**overrides) -> MagicMock:
    session = MagicMock()
    session.request = MagicMock(
        chat_id="chat-branch",
        use_workflow=False,
        timezone="UTC",
        resume_value=None,
        agent_id="agent-1",
        turn_capability_telemetry=None,
    )
    session.cancel_token = MagicMock()
    session.cancel_token.is_cancelled = False
    session.params = MagicMock()
    session.params.message_id = "msg-branch"
    session.params.enable_skill_manage = True
    session.params.model_cfg = MagicMock()
    session.params.locale = "en"
    session.collector = MagicMock()
    session.collector.has_persistable_turn = False
    session.collector.has_content = True
    session.collector.content = "Result text"
    session.collector.extra_data = {}
    session.collector._progress_steps = [{}]
    session.collector.sibling_group_id = None
    session.collector.cross_turn_data_updates = {}
    session.collector.has_pending_hitl_replay = MagicMock(return_value=False)
    session.collector.cleanup = MagicMock()
    session.monitor = MagicMock()
    session.monitor.stop = AsyncMock()
    session.extra_context = {}
    session.stream_ttft_ms = None
    session.had_fatal_error = False
    session.migration_live_readiness_status = None
    session.turn_capability_terminal_recorded = False
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


def _approval(value: dict[str, object] | None = None) -> ApprovalTimeoutHolder:
    return ApprovalTimeoutHolder(value=value)


def _clarification(
    pending: bool = False, directory_pending: bool = False
) -> ClarificationTimeoutHolder:
    return ClarificationTimeoutHolder(pending=pending, directory_pending=directory_pending)


class TestFinalizeBranchCoverage:
    @pytest.mark.asyncio
    async def test_approval_timeout_scheduled_when_no_clarification(self) -> None:
        """approval timeout must be scheduled when no clarification/directory pending."""
        session = _make_session()
        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
            ),
            patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=None,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.schedule_approval_timeout"
            ) as mock_schedule_approval,
            patch(
                "app.services.agent.evolution.engine.trigger_skill_evolution"
            ),
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session,
                MagicMock(),
                _approval({"type": "approve", "expires_at": 999}),
                _clarification(),
            )

        mock_schedule_approval.assert_called_once()

    @pytest.mark.asyncio
    async def test_compaction_debt_schedules_drain_and_error_digest(self) -> None:
        """Compaction debt must trigger background drain and an ERROR run digest."""
        session = _make_session()
        session.had_fatal_error = True
        metrics = MagicMock(compaction_debt_pending=True)
        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
            ),
            patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=metrics,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.chat.chat_service.ChatService.schedule_background_drain"
            ) as mock_drain,
            patch(
                "app.services.copilot.run_digest_store.RunDigestStore.end_run"
            ) as mock_end_run,
            patch(
                "app.services.agent.evolution.engine.trigger_skill_evolution"
            ),
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session, MagicMock(), _approval(), _clarification()
            )

        mock_drain.assert_called_once_with("chat-branch")
        mock_end_run.assert_called_once_with(
            "chat-branch", phase=RunDigestPhase.ERROR, progress_steps=[{}]
        )

    @pytest.mark.asyncio
    async def test_slice_flush_and_artifact_patch_and_turn_completed(self) -> None:
        """Residual slice flush, UI artifact patch and turn-capability completed record."""
        session = _make_session()
        session.collector.has_persistable_turn = True
        session.collector.content = "Result <cite:doc-1> text"
        session.collector.cross_turn_data_updates = {"ui": {"card": "closed"}}
        session.request.turn_capability_telemetry = TurnCapabilityTelemetryRequest(
            source="direct", effective_skill_count=2, effective_mcp_count=0
        )
        manager = MagicMock()
        manager.record_citations = AsyncMock()
        evo_integration = MagicMock()
        evo_integration._slice_cursors = {"chat-branch": (2, ["tool-a", "tool-b"])}
        evo_integration.queue = AsyncMock()
        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
            ),
            patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=None,
            ),
            patch(
                "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.merge_memory_citation_fallback"
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_manager",
                return_value=manager,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
                return_value={"used": 3, "total": 64},
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
                return_value={"state": "applied"},
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_turn_capability_send_completed",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration",
                return_value=evo_integration,
            ),
            patch(
                "app.services.chat.ui_artifact_patch.patch_ui_artifact_data_updates",
                new_callable=AsyncMock,
            ) as mock_patch_artifact,
            patch(
                "app.services.agent.evolution.engine.trigger_skill_evolution"
            ),
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session, MagicMock(), _approval(), _clarification()
            )

        manager.record_citations.assert_awaited_once()
        assert evo_integration.queue.enqueue.await_count == 1
        mock_patch_artifact.assert_awaited_once_with(
            "chat-branch", {"ui": {"card": "closed"}}
        )
        assert session.turn_capability_terminal_recorded is True

    @pytest.mark.asyncio
    async def test_memory_hooks_failure_swallowed(self) -> None:
        """Persistence hook failures must not break finalize teardown."""
        session = _make_session()
        session.collector.has_persistable_turn = True
        session.collector.content = "Result <cite:doc-1> text"
        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
            ),
            patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=None,
            ),
            patch(
                "app.services.chat.chat_service.ChatService.persist_assistant_message_safe",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.merge_memory_citation_fallback"
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_manager",
                side_effect=RuntimeError("manager gone"),
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_budget",
                return_value={"used": 1, "total": 16},
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_memory_runtime_injection",
                side_effect=RuntimeError("injection gone"),
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize._clear_interrupted_turn_marker",
                side_effect=RuntimeError("marker gone"),
            ),
            patch(
                "app.services.agent.evolution.engine.trigger_skill_evolution"
            ),
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session, MagicMock(), _approval(), _clarification()
            )

        session.collector.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_marks_pending_clarification_answered(self) -> None:
        """Resumed turns mark the pending clarification and directory requests answered."""
        session = _make_session()
        session.request.resume_value = "resume-payload"
        session.collector.extra_data = {"clarification": {"answered": False}}
        clarification_msg = MagicMock(id="m-clarify", role="assistant")
        clarification_msg.extra_data = {"clarification": {"answered": False}}
        directory_msg = MagicMock(id="m-directory", role="assistant")
        directory_msg.extra_data = {"directoryRequest": {"answered": False}}
        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
            ),
            patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=None,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.chat.chat_service.ChatService.get_all_messages",
                return_value=[directory_msg, clarification_msg],
            ),
            patch(
                "app.services.chat.chat_service.ChatService.update_message_extra_data",
                new_callable=AsyncMock,
            ) as mock_update_extra,
            patch(
                "app.services.agent.stream_session.stream_finalize.schedule_clarification_timeout"
            ) as mock_schedule_clarification,
            patch(
                "app.services.agent.evolution.engine.trigger_skill_evolution"
            ),
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session, MagicMock(), _approval(), _clarification()
            )

        assert mock_update_extra.await_count == 2
        mock_schedule_clarification.assert_called_once()

    @pytest.mark.asyncio
    async def test_directory_timeout_scheduled_via_holder(self) -> None:
        """directory_pending in the holder schedules the directory timeout."""
        session = _make_session()
        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
            ),
            patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=None,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.schedule_directory_timeout"
            ) as mock_schedule_directory,
            patch(
                "app.services.agent.evolution.engine.trigger_skill_evolution"
            ),
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session, MagicMock(), _approval(), _clarification(directory_pending=True)
            )

        mock_schedule_directory.assert_called_once()

    @pytest.mark.asyncio
    async def test_clarification_timeout_scheduled_via_holder(self) -> None:
        """pending in the holder schedules the clarification timeout."""
        session = _make_session()
        with (
            patch(
                "app.services.agent.stream_session.stream_finalize.enqueue_context_compaction_telemetry"
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.clear_context_task_metrics"
            ),
            patch("app.services.agent.stream_session.stream_finalize.CancellationRegistry"),
            patch("app.services.agent.stream_session.stream_finalize.SteeringRegistry"),
            patch("app.services.agent.goal_registry.GoalRegistry"),
            patch("myrm_agent_harness.agent.security.user_credentials_ctx") as mock_ctx,
            patch(
                "myrm_agent_harness.agent.context_management.tracking.task_metrics.get_task_metrics",
                return_value=None,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.record_migration_first_turn_outcome",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.agent.stream_session.stream_finalize.schedule_clarification_timeout"
            ) as mock_schedule_clarification,
            patch(
                "app.services.agent.evolution.engine.trigger_skill_evolution"
            ),
        ):
            mock_ctx.reset = MagicMock()
            await finalize_agent_stream_session(
                session, MagicMock(), _approval(), _clarification(pending=True)
            )

        mock_schedule_clarification.assert_called_once()
