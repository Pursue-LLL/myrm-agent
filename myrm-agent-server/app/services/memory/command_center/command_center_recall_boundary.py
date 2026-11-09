"""Review-first recall boundary snapshot for the memory command center.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager, MemoryType, types.AnyMemory (POS: Unified memory manager and memory domain types)
app.services.memory.command_center.command_center_memory_scan::{ALL_MEMORY_TYPES, count_memories_by_type} (POS: 指挥中心记忆类型枚举与按类型计数)
app.services.memory.command_center.command_center_pending::build_candidate_records (POS: 审批队列在指挥中心的读取视图)
app.services.memory.command_center.command_center_projection_utils::preview_content (POS: 指挥中心预览裁剪)

[OUTPUT]
build_recall_boundary: per-task recall scopes, candidate pool, per-partition memory counts and an approved-memory sample.

[POS]
个人大脑指挥中心的「召回边界」投影。展示任务级 read_scopes、待批候选池、四职责分区（Identity / Session Memory / Operating Instructions / Retrievable Evidence）的真实记忆数量与已生效记忆样本。单轮装载预算由 harness 在运行时按模型窗口决定，不是已存记忆的属性，所以这里不给预算数字。
"""

from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from myrm_agent_harness.toolkits.memory.types import AnyMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import (
    MemoryApprovedRecord,
    MemoryFourPartitionSummary,
    MemoryRecallBoundaryData,
    MemoryRecallScopeBoundary,
)
from app.services.memory.command_center.command_center_memory_scan import ALL_MEMORY_TYPES, count_memories_by_type
from app.services.memory.command_center.command_center_pending import build_candidate_records
from app.services.memory.command_center.command_center_projection_utils import preview_content

logger = logging.getLogger(__name__)

_APPROVED_SAMPLE_LIMIT = 15
_PREVIEW_CHARS = 100

_ALL_SCOPE_LEVELS = frozenset({"global", "agent", "channel", "conversation", "task", "shared"})

Partition = Literal["identity", "session_memory", "operating_instructions", "retrievable_evidence"]


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


async def _partition_totals(memory_manager: MemoryManager) -> dict[Partition, int]:
    """Stored memories per partition, each counted once."""
    counts = await count_memories_by_type(memory_manager)
    # Task digests are episodic memories tagged by event type, so the episodic count already contains them;
    # they belong to the session partition only.
    digests = counts[MemoryType.TASK_DIGEST.value]
    counts[MemoryType.EPISODIC.value] = max(0, counts[MemoryType.EPISODIC.value] - digests)
    totals: dict[Partition, int] = {
        "identity": 0,
        "session_memory": 0,
        "operating_instructions": 0,
        "retrievable_evidence": 0,
    }
    for memory_type in ALL_MEMORY_TYPES:
        totals[_partition_of(memory_type)] += counts[memory_type.value]
    return totals


def _approved_record(memory: AnyMemory, memory_type: MemoryType) -> MemoryApprovedRecord:
    # A procedural rule has no importance score.
    importance: float | None = getattr(memory, "importance", None)
    return MemoryApprovedRecord(
        id=memory.id,
        memory_type=memory_type.value,
        content_preview=preview_content(memory.content, limit=_PREVIEW_CHARS),
        namespace=memory.scope.primary_namespace or "global",
        partition=_partition_of(memory_type),
        importance=importance,
        access_count=memory.access_count,
        is_pinned=memory.pinned,
    )


async def _approved_sample(memory_manager: MemoryManager) -> list[MemoryApprovedRecord]:
    """The first approved memories in type order; a type that fails to list is skipped."""
    records: list[MemoryApprovedRecord] = []
    for memory_type in ALL_MEMORY_TYPES:
        if len(records) >= _APPROVED_SAMPLE_LIMIT:
            break
        try:
            memories = await memory_manager.list_memories(memory_type, limit=_APPROVED_SAMPLE_LIMIT - len(records))
        except Exception as exc:
            logger.warning("Failed to list %s memories for the recall boundary sample: %s", memory_type.value, exc)
            continue
        for memory in memories:
            # The episodic listing also returns task digests, which the TASK_DIGEST pass shows in their own partition.
            if memory_type == MemoryType.EPISODIC and getattr(memory, "event_type", None) == MemoryType.TASK_DIGEST.value:
                continue
            records.append(_approved_record(memory, memory_type))
    return records


async def build_recall_boundary(
    db: AsyncSession,
    memory_manager: MemoryManager,
    *,
    agent_id: str | None = None,
    task_id: str | None = None,
) -> MemoryRecallBoundaryData:
    """Build the review-first recall boundary: scopes, candidate pool, partition counts and an approved sample."""
    policy = memory_manager.memory_policy
    candidates = await build_candidate_records(db, memory_manager)
    totals = await _partition_totals(memory_manager)

    return MemoryRecallBoundaryData(
        agent_id=agent_id or (policy.agent_id if policy else None),
        task_id=task_id or (policy.task_id if policy else None),
        read_scopes=_scope_boundaries(memory_manager, agent_id=agent_id, task_id=task_id),
        write_policy=(policy.write_policy.value if (policy and hasattr(policy.write_policy, "value")) else "inherit"),
        partitions=MemoryFourPartitionSummary(
            identity_count=totals["identity"],
            session_memory_count=totals["session_memory"],
            operating_instructions_count=totals["operating_instructions"],
            retrievable_evidence_count=totals["retrievable_evidence"],
        ),
        candidate_records=candidates,
        approved_records=await _approved_sample(memory_manager),
        total_candidates=len(candidates),
        total_approved=sum(totals.values()),
    )
