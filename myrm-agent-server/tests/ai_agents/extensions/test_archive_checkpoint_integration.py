"""Integration tests for archive checkpoint dispatch and health metrics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables.config import RunnableConfig
from myrm_agent_harness.agent.context_management.archive_checkpoint import (
    ArchiveSummaryService,
    reset_archive_summary_pending_state,
)
from myrm_agent_harness.agent.context_management.archive_checkpoint.types import ArchiveCheckpointRecord
from myrm_agent_harness.agent.context_management.infra.schemas import CacheTtlPruneConfig
from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
    clear_task_metrics,
    create_task_metrics,
)

from app.ai_agents.extensions.archive_checkpoint_memory import (
    ArchiveCheckpointMemoryExtension,
    _dispatch_archive_checkpoint_status,
)
from app.api.statistics.context_health import build_chat_compaction_snapshot, build_context_health


@pytest.mark.asyncio
async def test_archive_summary_service_forwards_runnable_config_to_notifier() -> None:
    chat_id = "config-forward"
    clear_task_metrics(chat_id)
    create_task_metrics(chat_id)
    config = CacheTtlPruneConfig(archive_summary_enabled=True, archive_summary_min_tokens=1)
    mock_store = AsyncMock()
    record = ArchiveCheckpointRecord(
        memory_id="mem-1",
        tool_name="grep_tool",
        archive_path=".context/config-forward/compacted/out.txt",
        summary="summary",
        chat_id=chat_id,
    )
    mock_store.store_checkpoint.return_value = record
    runnable_config = RunnableConfig(configurable={"thread_id": chat_id})
    captured: dict[str, RunnableConfig | None] = {}

    async def _capture_notifier(
        checkpoint: ArchiveCheckpointRecord,
        run_config: RunnableConfig | None,
    ) -> None:
        _ = checkpoint
        captured["config"] = run_config

    service = ArchiveSummaryService(
        config=config,
        store=mock_store,
        on_checkpoint=_capture_notifier,
    )
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = MagicMock(content="summary body")
    reset_archive_summary_pending_state()

    service.dispatch(
        tool_name="grep_tool",
        content="x" * 100,
        archive_path=record.archive_path,
        chat_id=chat_id,
        summarizer_llm=mock_llm,
        runnable_config=runnable_config,
    )

    import asyncio

    await asyncio.sleep(0.1)
    assert captured.get("config") is runnable_config


@pytest.mark.asyncio
async def test_dispatch_archive_checkpoint_status_passes_config() -> None:
    record = ArchiveCheckpointRecord(
        memory_id="mem-2",
        tool_name="grep_tool",
        archive_path=".context/chat/compacted/out.txt",
        summary="summary",
        chat_id="chat-2",
    )
    runnable_config = RunnableConfig(configurable={"thread_id": "chat-2"})

    with patch(
        "myrm_agent_harness.utils.event_utils.dispatch_custom_event",
        new_callable=AsyncMock,
    ) as dispatch_event:
        await _dispatch_archive_checkpoint_status(record, runnable_config=runnable_config)

    dispatch_event.assert_awaited_once()
    assert dispatch_event.await_args.kwargs.get("config") is runnable_config


def test_context_health_reflects_archive_summary_metrics_after_dispatch() -> None:
    chat_id = "health-metrics"
    clear_task_metrics(chat_id)
    metrics = create_task_metrics(chat_id)
    metrics.record_archive_summary_checkpoint("queued")
    metrics.record_archive_summary_checkpoint("succeeded")

    health = build_context_health(
        message_stats={},
        task_metrics=metrics.to_dict(),
        chat_compaction=build_chat_compaction_snapshot(compacted_at=None, compacted_tokens_saved=None),
    )

    assert health.pruning.archive_summary_queued_count == 1
    assert health.pruning.archive_summary_succeeded_count == 1
    assert health.pruning.active is True


def test_extension_notifier_builds_when_memory_enabled() -> None:
    ext = ArchiveCheckpointMemoryExtension(
        enabled=True,
        is_subagent=False,
        channel_name="default",
        memory_manager=MagicMock(),
        effective_chat_id="chat-1",
    )
    assert ext.build_archive_checkpoint_store() is not None
    assert ext.build_archive_checkpoint_notifier() is not None
