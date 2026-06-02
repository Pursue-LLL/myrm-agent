from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.context_management.archive_checkpoint import (
    ArchiveCheckpointRecord,
    EpisodicMemoryArchiveCheckpointStore,
)
from myrm_agent_harness.agent.context_management.archive_checkpoint.summary_service import (
    ArchiveCheckpointNotifier,
)
from myrm_agent_harness.agent.extensions.protocols import AgentExtension

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.runnables.config import RunnableConfig
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.agent.context_management.archive_checkpoint.store import (
        ArchiveCheckpointStore,
    )
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ArchiveCheckpointMemoryExtension(AgentExtension):
    """Persist pruned tool-output summaries and emit ledger / SSE notifications."""

    def __init__(
        self,
        *,
        enabled: bool,
        is_subagent: bool,
        channel_name: str,
        memory_manager: MemoryManager | None,
        effective_chat_id: str,
    ) -> None:
        self.enabled = enabled
        self.is_subagent = is_subagent
        self.channel_name = channel_name
        self.memory_manager = memory_manager
        self.effective_chat_id = effective_chat_id

    @property
    def name(self) -> str:
        return "ArchiveCheckpointMemoryExtension"

    def build_archive_checkpoint_store(self) -> ArchiveCheckpointStore | None:
        if not self.enabled or self.memory_manager is None:
            return None
        if self.is_subagent or self.channel_name == "subagent":
            logger.info("[ArchiveCheckpoint] Skipped for subagent to prevent cross-agent checkpoint pollution.")
            return None
        return EpisodicMemoryArchiveCheckpointStore(self.memory_manager)

    def build_archive_checkpoint_notifier(self) -> ArchiveCheckpointNotifier | None:
        if not self.enabled or self.memory_manager is None:
            return None
        if self.is_subagent or self.channel_name == "subagent":
            return None
        effective_chat_id = self.effective_chat_id

        async def _notify(
            record: ArchiveCheckpointRecord,
            runnable_config: RunnableConfig | None,
        ) -> None:
            asyncio.create_task(
                _record_archive_checkpoint_event(
                    chat_id=record.chat_id or effective_chat_id,
                    record=record,
                )
            )
            await _dispatch_archive_checkpoint_status(record, runnable_config=runnable_config)

        return _notify

    async def on_agent_init(self, agent: BaseAgent) -> None:
        return None

    async def on_agent_shutdown(self, agent: BaseAgent) -> None:
        return None

    def get_tools(self) -> list[object] | None:
        return None

    def get_middlewares(self) -> list[AgentMiddleware[object, object]] | None:
        return None


async def _record_archive_checkpoint_event(*, chat_id: str, record: ArchiveCheckpointRecord) -> None:
    try:
        from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

        from app.database.connection import get_session
        from app.services.memory.operation_ledger import MemoryOperationLedgerService

        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.WRITE,
                status=MemoryOperationStatus.SUCCESS,
                summary=(
                    f"Archive checkpoint stored for {record.tool_name} "
                    f"({record.archive_path})"
                )[:240],
                source="cache_ttl_prune_processor",
                target_kind="chat",
                target_id=chat_id,
                metadata={
                    "trigger": "archive_checkpoint",
                    "event_type": "archive_checkpoint",
                    "memory_id": record.memory_id,
                    "tool_name": record.tool_name,
                    "archive_path": record.archive_path,
                    "tool_call_id": record.tool_call_id or "",
                    "chat_id": chat_id,
                },
                commit=True,
            )
    except Exception as exc:
        logger.warning("Failed to record archive checkpoint ledger event: %s", exc)


async def _dispatch_archive_checkpoint_status(
    record: ArchiveCheckpointRecord,
    *,
    runnable_config: RunnableConfig | None = None,
) -> None:
    try:
        from myrm_agent_harness.utils.event_utils import dispatch_custom_event

        await dispatch_custom_event(
            "agent_status",
            {
                "step_key": "archive_checkpoint",
                "message": f"Archive summary stored for {record.tool_name}",
                "tool_name": record.tool_name,
                "archive_path": record.archive_path,
                "memory_id": record.memory_id,
            },
            config=runnable_config,
        )
    except Exception as exc:
        logger.debug("Failed to dispatch archive_checkpoint status event: %s", exc)
