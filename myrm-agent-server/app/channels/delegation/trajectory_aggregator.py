"""Three Value Chains Organizational Context and Action Trajectory Aggregator.

Extracts, normalizes, and aggregates real execution trajectories across:
1. Production Pipeline: Sandbox execution tasks, code patches, tests, and DeliveryArtifacts.
2. Business Pipeline: Customer/Channel interaction logs, technical decisions, and agreements.
3. Management Pipeline: Action items, delivery milestones, and operational status.

Provides the SSOT data model for 1-Click Task-to-Weekly-Report SOP generation.

[INPUT]
- List of DelegationTasks, DeliveryArtifacts, and Channel conversation decisions.

[OUTPUT]
- Structured OrganizationalTrajectory containing categorized weekly milestones.

[POS]
Domain aggregation service in app/channels/delegation/ for Topic 13 Item 8.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Sequence

from .delegation_models import DelegationStatus, DelegationTask, DeliveryArtifact


class ValueChainType(str, enum.Enum):
    """The enterprise three value chains categorization."""

    PRODUCTION = "production"  # Code, sandbox, testing, artifacts
    BUSINESS = "business"  # Customer interaction, requirements, technical decisions
    MANAGEMENT = "management"  # Delivery milestones, risk tracking, action items


@dataclass(frozen=True)
class TrajectoryItem:
    """A single atomic record of real work done or agreed upon."""

    item_id: str
    chain_type: ValueChainType
    title: str
    summary: str
    evidence: str  # File path, artifact hash, task ID, or chat quotation
    timestamp: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)


@dataclass
class OrganizationalTrajectory:
    """Aggregated trajectory package for weekly/daily report synthesis."""

    user_id: str
    time_window_start: float
    time_window_end: float
    production_items: list[TrajectoryItem] = field(default_factory=list)
    business_items: list[TrajectoryItem] = field(default_factory=list)
    management_items: list[TrajectoryItem] = field(default_factory=list)
    total_artifacts_produced: int = 0
    total_tasks_executed: int = 0


class TrajectoryAggregator:
    """Aggregates multi-modal execution trails into structured organization trajectory."""

    @staticmethod
    def aggregate(
        *,
        user_id: str,
        tasks: Sequence[DelegationTask],
        channel_decisions: Sequence[dict[str, str]] | None = None,
        time_window_start: float | None = None,
        time_window_end: float | None = None,
    ) -> OrganizationalTrajectory:
        """Aggregate sandbox tasks, artifacts, and channel decisions within a timeframe."""
        now = time.time()
        start_ts = time_window_start if time_window_start is not None else (now - 7 * 86400)
        end_ts = time_window_end if time_window_end is not None else now

        trajectory = OrganizationalTrajectory(
            user_id=user_id,
            time_window_start=start_ts,
            time_window_end=end_ts,
        )

        # 1. Process Sandbox Production Tasks & Artifacts
        for task in tasks:
            task_time = task.completed_at or task.created_at
            if not (start_ts <= task_time <= end_ts):
                continue

            trajectory.total_tasks_executed += 1
            status_tag = f"status:{task.status.value}"

            if task.status == DelegationStatus.COMPLETED:
                title = f"任务完成: {task.normalized_prompt[:50]}"
                summary = task.result_summary or "沙箱执行完成并交付"
                evidence = f"task_id:{task.task_id}"

                item = TrajectoryItem(
                    item_id=f"prod_{task.task_id}",
                    chain_type=ValueChainType.PRODUCTION,
                    title=title,
                    summary=summary,
                    evidence=evidence,
                    timestamp=task_time,
                    tags=[status_tag, f"origin:{task.origin_channel}"],
                )
                trajectory.production_items.append(item)

                # Collect artifacts produced
                for artifact in task.artifacts:
                    trajectory.total_artifacts_produced += 1
                    art_item = TrajectoryItem(
                        item_id=f"art_{artifact.sha256_hash[:8] or artifact.file_name}",
                        chain_type=ValueChainType.PRODUCTION,
                        title=f"交付工件: {artifact.file_name}",
                        summary=f"产出文件 {artifact.file_name} ({artifact.file_size_bytes} 字节)",
                        evidence=f"hash:{artifact.sha256_hash or 'n/a'}, path:{artifact.file_path}",
                        timestamp=artifact.created_at,
                        tags=["artifact", f"mime:{artifact.mime_type}"],
                    )
                    trajectory.production_items.append(art_item)

            elif task.status == DelegationStatus.FAILED:
                # Failed tasks map to Management risk items
                item = TrajectoryItem(
                    item_id=f"risk_{task.task_id}",
                    chain_type=ValueChainType.MANAGEMENT,
                    title=f"阻碍与风险: {task.normalized_prompt[:50]}",
                    summary=f"任务执行异常: {task.error_message or '未知异常'}",
                    evidence=f"task_id:{task.task_id}",
                    timestamp=task_time,
                    tags=[status_tag, "risk:execution_failure"],
                )
                trajectory.management_items.append(item)

        # 2. Process Channel Discussions and Agreements (Business Pipeline)
        if channel_decisions:
            for idx, decision in enumerate(channel_decisions):
                topic = decision.get("topic", "技术/业务方案决议")
                detail = decision.get("detail", "")
                channel = decision.get("channel", "im")
                ts = float(decision.get("timestamp", now))

                if not (start_ts <= ts <= end_ts):
                    continue

                item = TrajectoryItem(
                    item_id=f"biz_{idx}_{int(ts)}",
                    chain_type=ValueChainType.BUSINESS,
                    title=f"方案决策: {topic}",
                    summary=detail,
                    evidence=f"channel:{channel}",
                    timestamp=ts,
                    tags=["decision", f"channel:{channel}"],
                )
                trajectory.business_items.append(item)

        return trajectory
