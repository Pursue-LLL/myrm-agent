"""Consolidation and Working State application service.

[INPUT]
myrm_agent_harness.agent.context_management.working_memory::LocalWorkingMemoryBlock (POS: 本地工作记忆块)
myrm_agent_harness.agent.context_management.working_memory::SubtaskStatus (POS: 子任务执行状态枚举)
myrm_agent_harness.toolkits.memory.types::TaskDigestMemory (POS: 任务阶段沉淀记忆类型)
myrm_agent_harness.toolkits.memory.manager::MemoryManager (POS: 记忆系统核心管理器)

[OUTPUT]
ConsolidationService: 工作记忆与历史阶段任务摘要业务服务

[POS]
记忆工作台与巩固服务。连接执行端 LocalWorkingMemoryBlock 实时状态快照、子任务/避坑项变动与历史 TaskDigest 阶段摘要查询。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.context_management.working_memory import (
    LocalWorkingMemoryBlock,
    SubtaskStatus,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType, TaskDigestMemory

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class ConsolidationService:
    """Service providing query and mutation facilities for runtime working boards and task digests."""

    @staticmethod
    def get_live_working_state() -> dict[str, object]:
        """Return the current active execution workbench state as serialized dict."""
        return LocalWorkingMemoryBlock.to_dict()

    @staticmethod
    def record_trap(
        fingerprint: str,
        avoidance_rule: str,
        tool_name: str | None = None,
    ) -> None:
        """Register a runtime error trap to the active coroutine workbench."""
        LocalWorkingMemoryBlock.record_trap(
            fingerprint=fingerprint,
            avoidance_rule=avoidance_rule,
            tool_name=tool_name,
        )

    @staticmethod
    def add_subtask(title: str, subtask_id: str | None = None) -> dict[str, str] | None:
        """Add a subtask to the live working block."""
        item = LocalWorkingMemoryBlock.add_subtask(title=title, subtask_id=subtask_id)
        if item is None:
            return None
        return {
            "id": item.id,
            "title": item.title,
            "status": str(item.status),
            "notes": item.notes,
        }

    @staticmethod
    def update_subtask(subtask_id: str, status: str, notes: str = "") -> bool:
        """Update an existing subtask's progression status."""
        try:
            parsed_status = SubtaskStatus(status)
        except ValueError:
            logger.warning("Invalid subtask status: %s", status)
            return False

        return LocalWorkingMemoryBlock.update_subtask(
            subtask_id=subtask_id,
            status=parsed_status,
            notes=notes,
        )

    @staticmethod
    async def list_task_digests(
        memory_manager: MemoryManager,
        limit: int = 20,
    ) -> list[dict[str, object]]:
        """Retrieve historical TaskDigestMemories from persistent store."""
        rel_store = getattr(memory_manager, "_relational_store", None)
        if rel_store is None:
            return []

        results: list[dict[str, object]] = []
        try:
            # Query relational store for memories of type TASK_DIGEST
            if hasattr(rel_store, "list_memories"):
                memories = await rel_store.list_memories(
                    memory_type=MemoryType.TASK_DIGEST,
                    limit=limit,
                )
                for mem in memories:
                    if isinstance(mem, TaskDigestMemory):
                        results.append(
                            {
                                "id": mem.id,
                                "task_goal": mem.task_goal,
                                "status": mem.status,
                                "completed_steps": list(mem.completed_steps),
                                "artifact_paths": list(mem.artifact_paths),
                                "key_findings": list(mem.key_findings),
                                "error_lessons": list(mem.error_lessons),
                                "tool_call_count": mem.tool_call_count,
                                "source_session_id": mem.source_session_id,
                                "created_at": mem.created_at.isoformat(),
                            }
                        )
        except Exception as err:
            logger.warning("Error querying task digests: %s", err)

        return results
