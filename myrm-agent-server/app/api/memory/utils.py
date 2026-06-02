"""Memory API utility functions.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::MemoryItem (POS: 记忆 API 通用 Schema 层)

[OUTPUT]
get_crud_memory_manager: MemoryManager 依赖注入工厂
memory_to_item: 记忆实体到 MemoryItem 响应模型的转换器（含投影映射）
parse_memory_type: 记忆类型验证器

[POS]
记忆 API 辅助工具层。提供依赖注入、数据转换和类型验证。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from datetime import datetime

from fastapi import Depends, HTTPException
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryStatus, MemoryType
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    EpisodicMemory,
    ProceduralMemory,
    ProfileEntry,
    SemanticMemory,
)

from app.api.dependencies import get_deploy_identity
from app.schemas.memory.crud import MemoryItem

logger = logging.getLogger(__name__)

_ManagerDep = Callable[..., Coroutine[object, object, MemoryManager]]


def _make_manager_dependency(*, approval_required: bool) -> _ManagerDep:
    """Factory: creates a FastAPI dependency with specific approval setting."""

    async def _dep(
        user_id: str = Depends(get_deploy_identity),
    ) -> MemoryManager:
        try:
            from app.core.memory.adapters.setup import (
                create_memory_manager,
                resolve_memory_binding,
            )
            from app.services.agent.platform_config import require_platform_embedding_config

            embedding_cfg = await require_platform_embedding_config()

            return await create_memory_manager(
                resolve_memory_binding(
                    namespaces=None,
                    agent_id=None,
                    channel_id=None,
                    conversation_id=None,
                    task_id=None,
                ),
                embedding_cfg,
                approval_required=approval_required,
            )
        except Exception as e:
            logger.warning(f"MemoryManager creation failed: {e}")
            raise HTTPException(
                status_code=503, detail="Memory system unavailable"
            ) from e

    return _dep


get_memory_manager = _make_manager_dependency(approval_required=True)
"""Pending endpoints: injects PendingStore for list/approve/reject."""

get_crud_memory_manager = _make_manager_dependency(approval_required=False)
"""CRUD endpoints: writes go directly to permanent storage."""

async def get_optional_memory_manager(
    user_id: str = Depends(get_deploy_identity),
) -> MemoryManager | None:
    """Optional dependency that returns None instead of 503 if MemoryManager creation fails."""
    try:
        from app.core.memory.adapters.setup import (
            create_memory_manager,
            resolve_memory_binding,
        )
        from app.services.agent.platform_config import require_platform_embedding_config

        embedding_cfg = await require_platform_embedding_config()

        return await create_memory_manager(
            resolve_memory_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_cfg,
            approval_required=False,
        )
    except Exception as e:
        logger.debug(f"Optional MemoryManager creation failed (graceful): {e}")
        return None


def parse_memory_type(raw: str) -> MemoryType:
    """Parse and validate a memory type string, raising 400 on invalid input."""
    try:
        return MemoryType(raw)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid memory type: {raw}"
        ) from e


_PROJECTION_MAP: dict[str, tuple[str, str, str]] = {
    "profile": ("user_profile", "User Profile", "Helps AI understand who you are"),
    "semantic": ("knowledge", "Knowledge", "Helps AI leverage what you know"),
    "episodic": ("experience", "Experience", "Helps AI reference your past events"),
    "conversation": (
        "dialogue",
        "Dialogue Memory",
        "Helps AI recall previous conversations",
    ),
    "procedural": ("method", "Method", "Helps AI follow your preferred workflows"),
    "claim": (
        "verified_knowledge",
        "Verified Knowledge",
        "Helps AI use validated facts",
    ),
    "task_digest": (
        "task_summary",
        "Task Summary",
        "Helps AI learn from completed tasks",
    ),
}


def memory_to_item(
    memory: AnyMemory | ProfileEntry, memory_type: MemoryType
) -> MemoryItem:
    """Convert a framework memory model to an API response item."""
    base_id = getattr(memory, "id", "")
    content = getattr(memory, "content", "")
    meta: dict[str, object] = getattr(memory, "metadata", {}) or {}
    now = datetime.now()

    proj = _PROJECTION_MAP.get(memory_type.value, ("other", "Other", ""))
    status_val = getattr(memory, "status", MemoryStatus.ACTIVE)
    if isinstance(status_val, MemoryStatus):
        status_val = status_val.value

    base: dict[str, object] = dict(
        id=base_id,
        memory_type=memory_type.value,
        content=content,
        importance=getattr(memory, "importance", 0.5),
        confidence=getattr(memory, "confidence", 1.0),
        status=status_val,
        created_at=getattr(memory, "created_at", now),
        updated_at=getattr(memory, "updated_at", now),
        metadata=meta,
        projected_category=proj[0],
        projected_label=proj[1],
        influence_explanation=proj[2],
        access_count=getattr(memory, "access_count", 0),
        last_accessed_at=getattr(memory, "last_accessed_at", None),
    )

    if memory_type == MemoryType.PROFILE:
        if isinstance(memory, ProfileEntry):
            base["key"] = memory.key
            base["value"] = str(memory.value) if memory.value is not None else None
        else:
            base["key"] = str(meta.get("key", "")) or None
            base["value"] = str(meta["value"]) if "value" in meta else None
    elif memory_type == MemoryType.PROCEDURAL and isinstance(memory, ProceduralMemory):
        base["trigger"] = memory.trigger
        base["action"] = memory.action
        if getattr(memory, "reasoning", None):
            base["reasoning"] = memory.reasoning
        if getattr(memory, "application", None):
            base["application"] = memory.application
        if memory.tool_name:
            base["tool_name"] = memory.tool_name
        if memory.tool_rule_priority:
            base["tool_rule_priority"] = memory.tool_rule_priority.value
    elif memory_type == MemoryType.EPISODIC and isinstance(memory, EpisodicMemory):
        base["event_type"] = memory.event_type
        base["related_entities"] = memory.related_entities or []

    if isinstance(memory, SemanticMemory):
        if memory.correction_of:
            base["correction_of"] = memory.correction_of
        if memory.source_error:
            base["source_error"] = memory.source_error

    return MemoryItem(**base)
