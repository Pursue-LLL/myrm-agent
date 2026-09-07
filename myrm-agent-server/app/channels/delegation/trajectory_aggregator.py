"""Trajectory and organizational context aggregator for enterprise value-chain penetration.

Aggregates multi-source evidence:
1. Sandbox execution records (DelegationTask, execution states, error recovery).
2. Physical delivery artifacts (DeliveryArtifact, generated code/reports/configs).
3. Chat-stream technical/management decisions and milestones.

[INPUT]
- .delegation_models::DelegationTask, DeliveryArtifact, DelegationStatus
- typing primitives and dataclasses

[OUTPUT]
- WorkTrajectoryItem: Typed descriptor for a single unit of work output.
- GroupDecisionItem: Typed descriptor for an extracted chat decision.
- AggregatedTrajectory: Comprehensive weekly/daily activity context.
- TrajectoryAggregator: Core aggregator engine.

[POS]
Data ingestion and normalization layer for weekly reporting and wiki archiving in app/channels/delegation/.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Sequence

from .delegation_models import DelegationStatus, DelegationTask, DeliveryArtifact

logger = logging.getLogger("myrm.channels.delegation.trajectory_aggregator")


class TrajectoryCategory(str, enum.Enum):
    """Categorization of work output within the organizational value chain."""

    DEVELOPMENT = "development"
    BUGFIX = "bugfix"
    DEPLOYMENT = "deployment"
    RESEARCH = "research"
    MANAGEMENT_DECISION = "management_decision"
    GENERAL = "general"


@dataclass(frozen=True)
class WorkTrajectoryItem:
    """Normalized evidence item representing a completed unit of work."""

    task_id: str
    title: str
    category: TrajectoryCategory
    summary: str
    status: DelegationStatus
    duration_seconds: float
    artifacts: list[DeliveryArtifact] = field(default_factory=list)
    completed_at: float = field(default_factory=time.time)
    origin_channel: str = ""
    origin_user_id: str = ""


@dataclass(frozen=True)
class GroupDecisionItem:
    """Decision extracted from collaborative chat streams."""

    decision_id: str
    topic: str
    summary: str
    decision_maker: str
    channel_id: str
    timestamp: float = field(default_factory=time.time)
    related_task_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AggregatedTrajectory:
    """Aggregated multi-source trajectory context across a defined time window."""

    user_id: str
    start_time: float
    end_time: float
    completed_items: list[WorkTrajectoryItem] = field(default_factory=list)
    in_progress_items: list[WorkTrajectoryItem] = field(default_factory=list)
    failed_items: list[WorkTrajectoryItem] = field(default_factory=list)
    artifacts: list[DeliveryArtifact] = field(default_factory=list)
    decisions: list[GroupDecisionItem] = field(default_factory=list)

    @property
    def total_tasks_count(self) -> int:
        return len(self.completed_items) + len(self.in_progress_items) + len(self.failed_items)

    @property
    def completion_rate(self) -> float:
        total = self.total_tasks_count
        if total == 0:
            return 1.0
        return len(self.completed_items) / total


class TrajectoryAggregator:
    """Aggregates sandbox execution histories, delivery artifacts, and IM decisions."""

    def __init__(self) -> None:
        pass

    def classify_task_category(self, task: DelegationTask) -> TrajectoryCategory:
        """Heuristically classify task category based on prompt and summary."""
        text = f"{task.user_prompt or task.raw_prompt or task.normalized_prompt} {task.result_summary}".lower()
        if any(w in text for w in ("fix", "bug", "repair", "error", "issue", "修复", "排查", "报错")):
            return TrajectoryCategory.BUGFIX
        if any(w in text for w in ("deploy", "release", "docker", "k8s", "部署", "上线", "发布")):
            return TrajectoryCategory.DEPLOYMENT
        if any(w in text for w in ("research", "study", "investigate", "compare", "调研", "分析", "对比")):
            return TrajectoryCategory.RESEARCH
        if any(w in text for w in ("implement", "feature", "build", "create", "开发", "实现", "编写", "重构")):
            return TrajectoryCategory.DEVELOPMENT
        return TrajectoryCategory.GENERAL

    def aggregate_from_tasks(
        self,
        tasks: Sequence[DelegationTask],
        *,
        user_id: str,
        start_time: float = 0.0,
        end_time: float | None = None,
        decisions: Sequence[GroupDecisionItem] | None = None,
    ) -> AggregatedTrajectory:
        """Aggregate execution tasks and decisions into structured trajectory context.

        Args:
            tasks: Sequence of candidate tasks.
            user_id: Filter by target user ID (or empty string for all).
            start_time: Inclusive start epoch timestamp.
            end_time: Inclusive end epoch timestamp (defaults to current time).
            decisions: Optional sequence of extracted chat decisions.

        Returns:
            AggregatedTrajectory structured container.
        """
        now = time.time()
        effective_end_time = end_time if end_time is not None else now

        completed_items: list[WorkTrajectoryItem] = []
        in_progress_items: list[WorkTrajectoryItem] = []
        failed_items: list[WorkTrajectoryItem] = []
        all_artifacts: list[DeliveryArtifact] = []

        for task in tasks:
            if user_id and task.origin_user_id != user_id:
                continue

            # Time range check based on task creation or completion
            task_time = task.completed_at or task.started_at or task.created_at
            if task_time < start_time or task_time > effective_end_time:
                continue

            duration = 0.0
            if task.started_at and task.completed_at:
                duration = max(0.0, task.completed_at - task.started_at)

            category = self.classify_task_category(task)
            item = WorkTrajectoryItem(
                task_id=task.task_id,
                title=(task.user_prompt or task.raw_prompt or task.normalized_prompt or "Task")[:80].strip(),
                category=category,
                summary=task.result_summary or task.error_message or "Executed in background sandbox.",
                status=task.status,
                duration_seconds=duration,
                artifacts=list(task.artifacts),
                completed_at=task.completed_at or task_time,
                origin_channel=task.origin_channel,
                origin_user_id=task.origin_user_id,
            )

            all_artifacts.extend(task.artifacts)

            if task.status == DelegationStatus.COMPLETED:
                completed_items.append(item)
            elif task.status in (DelegationStatus.RUNNING, DelegationStatus.PENDING, DelegationStatus.SUSPENDED_FOR_APPROVAL):
                in_progress_items.append(item)
            elif task.status in (DelegationStatus.FAILED, DelegationStatus.CANCELLED):
                failed_items.append(item)

        filtered_decisions: list[GroupDecisionItem] = []
        if decisions:
            for d in decisions:
                if start_time <= d.timestamp <= effective_end_time:
                    if not user_id or d.decision_maker == user_id:
                        filtered_decisions.append(d)

        return AggregatedTrajectory(
            user_id=user_id,
            start_time=start_time,
            end_time=effective_end_time,
            completed_items=completed_items,
            in_progress_items=in_progress_items,
            failed_items=failed_items,
            artifacts=all_artifacts,
            decisions=filtered_decisions,
        )
