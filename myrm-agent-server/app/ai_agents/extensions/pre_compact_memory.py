from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage
from myrm_agent_harness.agent.context_management.infra.schemas import (
    ContextPreCompactCallback,
    PreCompactInjection,
)
from myrm_agent_harness.agent.context_management.pre_compact_service import (
    MemoryPreCompactConfig,
    MemoryPreCompactService,
)
from myrm_agent_harness.agent.extensions.protocols import AgentExtension

if TYPE_CHECKING:
    from langchain.agents.middleware import AgentMiddleware
    from myrm_agent_harness.agent.base_agent import BaseAgent
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class PreCompactMemoryExtension(AgentExtension):
    """Inject semantic memory recall before context compaction and record ledger events."""

    def __init__(
        self,
        *,
        enabled: bool,
        is_subagent: bool,
        channel_name: str,
        memory_manager: MemoryManager | None,
        effective_chat_id: str,
        budget_tokens: int = 1500,
    ) -> None:
        self.enabled = enabled
        self.is_subagent = is_subagent
        self.channel_name = channel_name
        self.memory_manager = memory_manager
        self.effective_chat_id = effective_chat_id
        self.budget_tokens = budget_tokens

    @property
    def name(self) -> str:
        return "PreCompactMemoryExtension"

    def build_pre_compact_callback(self) -> ContextPreCompactCallback | None:
        if not self.enabled or self.memory_manager is None:
            return None
        if self.is_subagent or self.channel_name == "subagent":
            logger.info("[PreCompact] Skipped for subagent to prevent cross-agent recall pollution.")
            return None

        service = MemoryPreCompactService(
            self.memory_manager,
            config=MemoryPreCompactConfig(
                enabled=True,
                budget_tokens=max(800, min(self.budget_tokens, 2000)),
            ),
        )
        effective_chat_id = self.effective_chat_id

        async def _pre_compact_cb(
            *,
            messages: list[BaseMessage],
            chat_id: str | None,
            user_id: str | None,
            compaction_tier: str,
            token_pressure_ratio: float,
            user_goal_hint: str,
        ) -> PreCompactInjection | None:
            injection = await service.build_injection(
                messages=messages,
                chat_id=chat_id or effective_chat_id,
                user_id=user_id,
                compaction_tier=compaction_tier,
                token_pressure_ratio=token_pressure_ratio,
                user_goal_hint=user_goal_hint,
            )
            if injection is None:
                return None
            asyncio.create_task(
                _record_pre_compact_event(
                    chat_id=chat_id or effective_chat_id,
                    injection=injection,
                )
            )
            return injection

        return _pre_compact_cb

    async def on_agent_init(self, agent: BaseAgent) -> None:
        return None

    async def on_agent_shutdown(self, agent: BaseAgent) -> None:
        return None

    def get_tools(self) -> list[object] | None:
        return None

    def get_middlewares(self) -> list[AgentMiddleware[object, object]] | None:
        return None


async def _record_pre_compact_event(*, chat_id: str, injection: PreCompactInjection) -> None:
    try:
        from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

        from app.database.connection import get_session
        from app.services.memory.operation_ledger import MemoryOperationLedgerService

        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.INJECT,
                status=MemoryOperationStatus.SUCCESS,
                summary=(
                    f"Pre-compaction recall injected {len(injection.recalled_ids)} memories "
                    f"({injection.compaction_tier})"
                )[:240],
                source="pre_compact_processor",
                target_kind="chat",
                target_id=chat_id,
                metadata={
                    "trigger": "pre_compact",
                    "compaction_tier": injection.compaction_tier,
                    "recalled_ids": ",".join(injection.recalled_ids),
                    "token_estimate": injection.token_estimate,
                    "query_preview": injection.query[:180],
                    "chat_id": chat_id,
                },
                commit=True,
            )
    except Exception as exc:
        logger.warning("Failed to record pre-compact ledger event: %s", exc)
