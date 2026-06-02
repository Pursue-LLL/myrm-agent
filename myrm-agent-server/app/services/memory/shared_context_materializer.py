"""
[INPUT]
app.core.memory.adapters.setup::create_memory_manager (POS: 业务层记忆适配器入口)
app.database.models::SharedContextWriteProposalModel (POS: 记忆域模型)
app.services.memory.shared_context::SharedContextService (POS: 共享上下文业务服务)
myrm_agent_harness.toolkits.memory.manager::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)

[OUTPUT]
SharedContextProposalMaterializer: 共享上下文写入提案批准与记忆物化服务

[POS]
共享上下文写入物化服务。把已审批 proposal 安全、幂等地写入目标 shared namespace，
并把 API 层从 MemoryManager 副作用细节中解耦。
"""

from __future__ import annotations

from typing import TypeAlias

from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, MemorySearchResult, MemoryType, SemanticMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.memory.adapters.setup import create_memory_manager, resolve_memory_binding
from app.database.models import SharedContextWriteProposalModel
from app.services.agent.platform_config import require_platform_embedding_config
from app.services.memory.shared_context import SharedContextService

ScalarMetadataValue: TypeAlias = str | int | float | bool

_DEFAULT_IMPORTANCE = 0.5


def _scalar_metadata(metadata: dict[str, object]) -> dict[str, ScalarMetadataValue]:
    """Keep only scalar metadata accepted by Harness BaseMemory."""
    return {
        key: value
        for key, value in metadata.items()
        if isinstance(key, str) and isinstance(value, str | int | float | bool)
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _bounded_importance(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return _DEFAULT_IMPORTANCE
    return min(max(float(value), 0.0), 1.0)


def _event_type(value: object) -> str:
    normalized = _optional_string(value)
    return normalized or "shared_context"


def _proposal_memory_type(proposal: SharedContextWriteProposalModel) -> MemoryType:
    if proposal.memory_type == MemoryType.SEMANTIC.value:
        return MemoryType.SEMANTIC
    if proposal.memory_type == MemoryType.EPISODIC.value:
        return MemoryType.EPISODIC
    raise ValueError("Unsupported shared context memory type")


def _proposal_metadata(proposal: SharedContextWriteProposalModel) -> dict[str, ScalarMetadataValue]:
    metadata = _scalar_metadata(proposal.metadata_json or {})
    metadata["shared_context_id"] = proposal.context_id
    metadata["shared_context_proposal_id"] = proposal.id
    metadata["shared_context_source_type"] = proposal.source_type
    if proposal.source_id:
        metadata["shared_context_source_id"] = proposal.source_id
    return metadata


def _source_chat_id(metadata: dict[str, object]) -> str | None:
    return _optional_string(metadata.get("source_chat_id"))


def _source_message_id(metadata: dict[str, object], proposal: SharedContextWriteProposalModel) -> str | None:
    return _optional_string(metadata.get("source_message_id")) or (
        proposal.source_id if proposal.source_type == "chat_history" else None
    )


def _is_same_proposal(result: MemorySearchResult, proposal_id: str) -> bool:
    proposal_marker: object = result.memory.metadata.get("shared_context_proposal_id")
    return proposal_marker == proposal_id


class SharedContextProposalMaterializer:
    """Approve proposals and persist them into the governed shared namespace."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def approve_write_proposal(self, proposal_id: str) -> SharedContextWriteProposalModel | None:
        """Approve a pending proposal and materialize it exactly once when retrying."""
        service = SharedContextService(self._session)
        proposal = await service.get_write_proposal(proposal_id)
        if proposal is None:
            return None
        if proposal.status == "approved":
            return proposal
        if proposal.status != "pending":
            raise ValueError("Shared context write proposal is not pending")

        context = await service.get_context(proposal.context_id)
        if context is None or context.status != "active":
            raise ValueError("Shared context is not active")

        manager = await self._create_memory_manager(context.namespace)
        if await self._already_materialized(manager, proposal):
            updated = await service.set_write_proposal_status(proposal_id, "approved")
            return updated or proposal

        raw_metadata = proposal.metadata_json or {}
        memory_type = _proposal_memory_type(proposal)
        memory: SemanticMemory | EpisodicMemory
        if memory_type == MemoryType.SEMANTIC:
            memory = SemanticMemory(
                content=proposal.content,
                metadata=_proposal_metadata(proposal),
                importance=_bounded_importance(raw_metadata.get("importance")),
                tags=_string_list(raw_metadata.get("tags")),
                source_chat_id=_source_chat_id(raw_metadata),
                source_message_id=_source_message_id(raw_metadata, proposal),
            )
        else:
            memory = EpisodicMemory(
                content=proposal.content,
                metadata=_proposal_metadata(proposal),
                event_type=_event_type(raw_metadata.get("event_type")),
                related_entities=_string_list(raw_metadata.get("related_entities")),
                source_chat_id=_source_chat_id(raw_metadata),
                source_message_id=_source_message_id(raw_metadata, proposal),
                importance=_bounded_importance(raw_metadata.get("importance")),
            )

        await manager.store(memory, _bypass_approval=True)
        updated = await service.set_write_proposal_status(proposal_id, "approved")
        return updated or proposal

    async def _create_memory_manager(self, namespace: str) -> MemoryManager:
        return await create_memory_manager(
            resolve_memory_binding(
                namespaces=[namespace],
                agent_id="shared-context",
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            await require_platform_embedding_config(),
            approval_required=False,
        )

    async def _already_materialized(
        self,
        manager: MemoryManager,
        proposal: SharedContextWriteProposalModel,
    ) -> bool:
        results = await manager.search(
            proposal.content,
            memory_types=[_proposal_memory_type(proposal)],
            limit=10,
            use_rrf=False,
        )
        return any(_is_same_proposal(result, proposal.id) for result in results)
