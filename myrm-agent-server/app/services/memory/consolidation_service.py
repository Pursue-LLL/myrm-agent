"""Consolidation and Working State application service.

[INPUT]
myrm_agent_harness.api::LocalWorkingMemoryBlock (POS: 本地工作记忆块)
myrm_agent_harness.api::SubtaskStatus (POS: 子任务执行状态枚举)
myrm_agent_harness.toolkits.memory.types::TaskDigestMemory (POS: 任务阶段沉淀记忆类型)
myrm_agent_harness.toolkits.memory.manager::MemoryManager (POS: 记忆系统核心管理器)

[OUTPUT]
ConsolidationService: 工作记忆与历史阶段任务摘要业务服务

[POS]
记忆工作台与巩固服务。连接执行端 LocalWorkingMemoryBlock 实时状态快照、子任务/避坑项变动与历史 TaskDigest 阶段摘要查询。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.api import (
    LocalWorkingMemoryBlock,
    SubtaskStatus,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType

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
    def resolve_trap(fingerprint: str) -> bool:
        """Resolve an active runtime error trap on the current coroutine workbench."""
        return LocalWorkingMemoryBlock.resolve_trap(fingerprint=fingerprint)

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
        def _parse_str_list(val: object) -> list[str]:
            if isinstance(val, list):
                return [str(x) for x in val]
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except Exception:
                    pass
            return []

        results: list[dict[str, object]] = []
        try:
            if hasattr(memory_manager, "list_memories"):
                memories = await memory_manager.list_memories(
                    memory_type=MemoryType.EPISODIC,
                    limit=limit,
                )
                for mem in memories:
                    meta = getattr(mem, "metadata", {}) or {}
                    if (
                        getattr(mem, "event_type", "") == "task_digest"
                        or meta.get("event_type") == "task_digest"
                        or meta.get("task_goal")
                    ):
                        created = getattr(mem, "created_at", getattr(mem, "timestamp", None))
                        created_str = created.isoformat() if hasattr(created, "isoformat") else str(created or "")
                        results.append(
                            {
                                "id": str(getattr(mem, "id", "")),
                                "task_goal": str(meta.get("task_goal", getattr(mem, "content", ""))),
                                "status": str(meta.get("status", "completed")),
                                "completed_steps": _parse_str_list(meta.get("completed_steps")),
                                "artifact_paths": _parse_str_list(meta.get("artifact_paths")),
                                "key_findings": _parse_str_list(meta.get("key_findings")),
                                "error_lessons": _parse_str_list(meta.get("error_lessons")),
                                "tool_call_count": int(meta.get("tool_call_count", 0)),
                                "source_session_id": getattr(mem, "source_chat_id", None),
                                "created_at": created_str,
                            }
                        )
        except Exception as err:
            logger.warning("Error querying task digests: %s", err)

        return results
