"""Trajectory aggregation engine for extracting verified execution logs.

Aggregates delegation tasks, delivery artifacts, and chat events within a time window.
"""

from __future__ import annotations

import time
from typing import Sequence

from app.channels.delegation.delegation_models import DelegationTask, DeliveryArtifact
from app.services.weekly_report.models import (
    TrajectoryItem,
    TrajectorySourceKind,
)


class TrajectoryAggregator:
    """Aggregates execution trajectories across sandboxes and IM channels."""

    @staticmethod
    def get_natural_week_window(reference_time_ms: int | None = None) -> tuple[int, int]:
        """Calculates start and end timestamps (ms) for the current natural week (Monday to Sunday)."""
        now_sec = (reference_time_ms / 1000.0) if reference_time_ms is not None else time.time()
        time_struct = time.localtime(now_sec)
        
        # Calculate start of Monday 00:00:00
        days_since_monday = time_struct.tm_wday
        start_day_struct = time.struct_time((
            time_struct.tm_year,
            time_struct.tm_mon,
            time_struct.tm_mday - days_since_monday,
            0, 0, 0, 0, 0, time_struct.tm_isdst
        ))
        start_sec = time.mktime(start_day_struct)
        end_sec = start_sec + (7 * 86400) - 0.001
        
        return int(start_sec * 1000), int(end_sec * 1000)

    def aggregate_from_delegation(
        self,
        tasks: Sequence[DelegationTask],
        artifacts: Sequence[DeliveryArtifact],
        start_time_ms: int,
        end_time_ms: int,
    ) -> list[TrajectoryItem]:
        """Filters and maps delegation tasks and artifacts within the specified time window."""
        items: list[TrajectoryItem] = []
        
        # Map artifacts by task_id for efficient lookup
        task_artifacts_map: dict[str, list[str]] = {}
        for art in artifacts:
            if start_time_ms <= art.created_at_ms <= end_time_ms:
                task_artifacts_map.setdefault(art.task_id, []).append(art.file_path)

        for task in tasks:
            if not (start_time_ms <= task.created_at_ms <= end_time_ms):
                continue
            
            task_art_paths = task_artifacts_map.get(task.task_id, [])
            all_art_paths = tuple(task_art_paths) if task_art_paths else tuple(task.artifact_paths)

            title = f"Task: {task.instruction[:40]}" if task.instruction else f"Task {task.task_id[:8]}"
            summary = task.execution_summary or f"Status: {task.status.value}"
            
            item = TrajectoryItem(
                source_id=task.task_id,
                source_kind=TrajectorySourceKind.DELEGATION_TASK,
                title=title,
                summary=summary,
                timestamp_ms=task.created_at_ms,
                artifact_paths=all_art_paths,
                tags=("sandbox", task.status.value),
                metadata={"channel_id": task.channel_id, "status": task.status.value},
            )
            items.append(item)
            
        # Sort trajectory chronologically
        items.sort(key=lambda x: x.timestamp_ms)
        return items
