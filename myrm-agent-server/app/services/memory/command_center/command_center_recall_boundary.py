"""Review-first recall boundary snapshot for the memory command center.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager, MemoryType (POS: Unified memory manager and memory domain types)
app.services.memory.command_center.command_center_memory_scan::ALL_MEMORY_TYPES (POS: 指挥中心记忆类型枚举)
app.services.memory.command_center.command_center_pending::build_candidate_records (POS: 审批队列在指挥中心的读取视图)
app.services.memory.command_center.command_center_projection_utils::preview_content (POS: 指挥中心预览裁剪)

[OUTPUT]
build_recall_boundary: per-task recall scopes, candidate/approved partition and prompt-budget snapshot.
BUDGET_CHARS_TOTAL: prompt budget in characters shared by the four partitions.

[POS]
个人大脑指挥中心的「召回边界」投影。展示任务级 read_scopes、待批候选池、四职责分区（Identity / Session Memory / Operating Instructions / Retrievable Evidence）与 6000 字符装载预算。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import (
    MemoryApprovedRecord,
    MemoryFourPartitionSummary,
    MemoryRecallBoundaryData,
    MemoryRecallScopeBoundary,
)
from app.services.memory.command_center.command_center_memory_scan import ALL_MEMORY_TYPES
from app.services.memory.command_center.command_center_pending import build_candidate_records
from app.services.memory.command_center.command_center_projection_utils import preview_content

logger = logging.getLogger(__name__)

BUDGET_CHARS_TOTAL = 6000
_BUDGET_APPROACHING_CHARS = 4500
_SAMPLE_PER_TYPE = 10
_APPROVED_SAMPLE_LIMIT = 15
_PREVIEW_CHARS = 100

_ALL_SCOPE_LEVELS = frozenset({"global", "agent", "channel", "conversation", "task", "shared"})

Partition = Literal["identity", "session_memory", "operating_instructions", "retrievable_evidence"]


@dataclass(slots=True)
class _PartitionTotals:
    count: int = 0
    chars: int = 0


def _partition_of(memory_type: MemoryType) -> Partition:
    if memory_type == MemoryType.PROFILE:
        return "identity"
    if memory_type in (MemoryType.TASK_DIGEST, MemoryType.CONVERSATION):
        return "session_memory"
    if memory_type == MemoryType.PROCEDURAL:
        return "operating_instructions"
    return "retrievable_evidence"


def _scope_boundaries(
    memory_manager: MemoryManager,
    *,
    agent_id: str | None,
    task_id: str | None,
) -> list[MemoryRecallScopeBoundary]:
    policy = memory_manager.memory_policy
    active_levels = {scope.value for scope in policy.read_scopes} if (policy and policy.read_scopes) else _ALL_SCOPE_LEVELS
    levels = [
        ("global", "Global Shared Knowledge", "global", "System-wide persistent facts and rules"),
        (
            "agent",
            f"Agent Dedicated ({agent_id or 'default'})",
            f"agent:{agent_id or 'default'}",
            "Private memory assigned to this agent identity",
        ),
        ("channel", "Channel/Integration Boundary", "channel:*", "Platform or channel-specific context"),
        ("conversation", "Session Conversation State", "conversation:*", "Current multi-turn dialog flow"),
        (
            "task",
            f"Task Boundary ({task_id or 'active'})",
            f"task:{task_id or 'active'}",
            "Ephemeral execution session memory",
        ),
        ("shared", "Team Shared Context", "shared:*", "Explicitly shared team vaults and resources"),
    ]
    return [
        MemoryRecallScopeBoundary(
            level=level,
            label=label,
            is_active=level in active_levels,
            namespace_pattern=pattern,
            description=description,
        )
        for level, label, pattern, description in levels
    ]


async def build_recall_boundary(
    db: AsyncSession,
    memory_manager: MemoryManager,
    *,
    agent_id: str | None = None,
    task_id: str | None = None,
) -> MemoryRecallBoundaryData:
    """Build the review-first recall boundary: scopes, candidate pool, partitions and prompt budget."""
    policy = memory_manager.memory_policy
    candidates = await build_candidate_records(db, memory_manager)

    totals: dict[Partition, _PartitionTotals] = {
        "identity": _PartitionTotals(),
        "session_memory": _PartitionTotals(),
        "operating_instructions": _PartitionTotals(),
        "retrievable_evidence": _PartitionTotals(),
    }
    total_chars = 0
    approved_records: list[MemoryApprovedRecord] = []

    for memory_type in ALL_MEMORY_TYPES:
        try:
            memories = await memory_manager.list_memories(memory_type, limit=_SAMPLE_PER_TYPE)
            for memory in memories:
                content = str(getattr(memory, "content", "") or "")
                char_len = len(content)
                total_chars += char_len

                partition = _partition_of(memory_type)
                totals[partition].count += 1
                totals[partition].chars += char_len

                if len(approved_records) < _APPROVED_SAMPLE_LIMIT:
                    approved_records.append(
                        MemoryApprovedRecord(
                            id=str(getattr(memory, "id", "") or f"mem-{len(approved_records)}"),
                            memory_type=memory_type.value,
                            content_preview=preview_content(content, limit=_PREVIEW_CHARS),
                            namespace=str(getattr(memory, "primary_namespace", "") or "global"),
                            partition=partition,
                            importance=float(getattr(memory, "importance", 0.7) or 0.7),
                            access_count=int(getattr(memory, "access_count", 1) or 1),
                            char_count=char_len,
                            is_pinned=bool(getattr(memory, "pinned", False)),
                        )
                    )
        except Exception as exc:
            logger.warning("Failed to list memories for %s partition summary: %s", memory_type.value, exc)

    risk: Literal["safe", "approaching_limit", "overflow"] = "safe"
    if total_chars > BUDGET_CHARS_TOTAL:
        risk = "overflow"
    elif total_chars > _BUDGET_APPROACHING_CHARS:
        risk = "approaching_limit"

    return MemoryRecallBoundaryData(
        agent_id=agent_id or (policy.agent_id if policy else None),
        task_id=task_id or (policy.task_id if policy else None),
        read_scopes=_scope_boundaries(memory_manager, agent_id=agent_id, task_id=task_id),
        write_policy=(policy.write_policy.value if (policy and hasattr(policy.write_policy, "value")) else "inherit"),
        partitions=MemoryFourPartitionSummary(
            identity_count=totals["identity"].count,
            session_memory_count=totals["session_memory"].count,
            operating_instructions_count=totals["operating_instructions"].count,
            retrievable_evidence_count=totals["retrievable_evidence"].count,
            identity_chars=totals["identity"].chars,
            session_memory_chars=totals["session_memory"].chars,
            operating_instructions_chars=totals["operating_instructions"].chars,
            retrievable_evidence_chars=totals["retrievable_evidence"].chars,
        ),
        candidate_records=candidates,
        approved_records=approved_records,
        budget_chars_used=total_chars,
        budget_chars_total=BUDGET_CHARS_TOTAL,
        budget_overflow_risk=risk,
        total_candidates=len(candidates),
        total_approved=sum(partition.count for partition in totals.values()),
    )
