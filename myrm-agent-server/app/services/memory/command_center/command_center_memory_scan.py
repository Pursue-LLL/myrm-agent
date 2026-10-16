"""Read-only MemoryManager scans backing the memory command center.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager, MemoryStatus, MemoryType (POS: Unified memory manager and memory domain types)
app.services.memory.command_center.command_center_projection_utils::preview_content (POS: 指挥中心预览裁剪)

[OUTPUT]
ALL_MEMORY_TYPES: every memory type the command center and statistics views enumerate.
count_memories_by_type: per-type memory counts (failures degrade to 0).
list_archived_memory_ids / list_pinned_memory_ids / list_active_memory_previews: id and preview collections for economics and exemption logic.

[POS]
指挥中心对 MemoryManager 的只读扫描层。把「枚举类型、统计、归档/置顶/预览收集」从聚合服务中拆出，单个类型扫描失败只记日志并跳过，不影响整体快照。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryStatus, MemoryType

from app.services.memory.command_center.command_center_projection_utils import preview_content

logger = logging.getLogger(__name__)

ALL_MEMORY_TYPES: tuple[MemoryType, ...] = (
    MemoryType.PROFILE,
    MemoryType.SEMANTIC,
    MemoryType.EPISODIC,
    MemoryType.PROCEDURAL,
    MemoryType.CONVERSATION,
    MemoryType.CLAIM,
    MemoryType.TASK_DIGEST,
)

_ARCHIVE_SCAN_TYPES: tuple[MemoryType, ...] = (MemoryType.SEMANTIC, MemoryType.EPISODIC)
_ACTIVE_SCAN_TYPES: tuple[MemoryType, ...] = (MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROCEDURAL)
_ID_SCAN_LIMIT = 5000
_PREVIEW_SCAN_LIMIT = 500
_PREVIEW_CHARS = 100
_MISSING = object()


async def count_memories_by_type(memory_manager: MemoryManager) -> dict[str, int]:
    counts: dict[str, int] = {}
    for memory_type in ALL_MEMORY_TYPES:
        try:
            counts[memory_type.value] = await memory_manager.count_memories(memory_type)
        except Exception as exc:
            logger.warning("Memory count failed for %s: %s", memory_type.value, exc)
            counts[memory_type.value] = 0
    return counts


async def list_archived_memory_ids(memory_manager: MemoryManager) -> set[str]:
    """Fetch archived (soft-deleted / forgotten) memory ids to prevent ghost recommendations."""
    if not memory_manager:
        return set()
    archived_ids: set[str] = set()
    for memory_type in _ARCHIVE_SCAN_TYPES:
        try:
            memories = await memory_manager.list_memories(memory_type, limit=_ID_SCAN_LIMIT, include_archived=True)
            for memory in memories:
                if getattr(memory, "status", None) == MemoryStatus.ARCHIVED:
                    memory_id = str(getattr(memory, "id", "") or "")
                    if memory_id:
                        archived_ids.add(memory_id)
        except Exception as exc:
            logger.debug("Failed listing archived %s memories: %s", memory_type, exc)
    return archived_ids


async def list_pinned_memory_ids(memory_manager: MemoryManager) -> set[str]:
    """Collect memory ids pinned by the user or the system so they stay exempt from archival."""
    if not memory_manager:
        return set()
    pinned_ids: set[str] = set()
    for memory_type in _ACTIVE_SCAN_TYPES:
        try:
            memories = await memory_manager.list_memories(memory_type, limit=_ID_SCAN_LIMIT, include_archived=False)
            for memory in memories:
                if getattr(memory, "pinned", False) or getattr(memory, "is_pinned", False):
                    memory_id = str(getattr(memory, "id", "") or "")
                    if memory_id:
                        pinned_ids.add(memory_id)
        except Exception as exc:
            logger.debug("Failed listing pinned %s memories: %s", memory_type, exc)
    return pinned_ids


async def list_active_memory_previews(memory_manager: MemoryManager) -> dict[str, tuple[str, str]]:
    """Map active memory id to ``(preview, memory type)``; procedural memories render as ``trigger -> action``."""
    if not memory_manager:
        return {}
    previews: dict[str, tuple[str, str]] = {}
    for memory_type in _ACTIVE_SCAN_TYPES:
        try:
            memories = await memory_manager.list_memories(memory_type, limit=_PREVIEW_SCAN_LIMIT, include_archived=False)
            for memory in memories:
                if getattr(memory, "status", None) == MemoryStatus.ARCHIVED:
                    continue
                memory_id = str(getattr(memory, "id", "") or "")
                content = getattr(memory, "content", "") or ""
                trigger = getattr(memory, "trigger", _MISSING)
                action = getattr(memory, "action", _MISSING)
                if not content and trigger is not _MISSING and action is not _MISSING:
                    content = f"{trigger} -> {action}"
                if memory_id and content:
                    previews[memory_id] = (preview_content(str(content), limit=_PREVIEW_CHARS), memory_type.value)
        except Exception as exc:
            logger.debug("Failed listing active %s memories for previews: %s", memory_type, exc)
    return previews
