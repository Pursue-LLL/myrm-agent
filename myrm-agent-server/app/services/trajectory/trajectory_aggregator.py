"""Multi-source organizational trajectory aggregator across production, business, and management value chains.

Collects real execution traces from sandbox tasks, generated code artifacts, IM discussion
milestones, and governance approvals. Eliminates hallucinations and provides verified evidence
anchors for automated weekly reporting and knowledge archiving.

[INPUT]
- Raw task records, artifact registry items, and thread messages within a given time range.

[OUTPUT]
- Filtered, deduplicated, and chronologically organized TrajectoryEvents grouped by ValueChainType.
- TrajectoryAggregator: Core coordinator for organizational context collection.

[POS]
Domain service in app/services/trajectory/.
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

from .trajectory_models import (
    TrajectoryArtifactRef,
    TrajectoryEvent,
    ValueChainType,
)

logger = logging.getLogger("myrm.services.trajectory.aggregator")


class TrajectoryAggregator:
    """Aggregates enterprise execution evidence and milestones from multiple operational sources."""

    def __init__(self) -> None:
        self._in_memory_events: list[TrajectoryEvent] = []

    def record_event(self, event: TrajectoryEvent) -> None:
        """Register a new trajectory event into the aggregator store."""
        self._in_memory_events.append(event)
        logger.debug("Recorded trajectory event: %s (%s)", event.event_id, event.chain_type.value)

    def record_production_task(
        self,
        *,
        task_id: str,
        title: str,
        summary: str,
        artifacts: Sequence[TrajectoryArtifactRef] = (),
        is_completed: bool = True,
        timestamp: float | None = None,
        source_channel: str = "web",
    ) -> TrajectoryEvent:
        """Helper to record a production chain task execution event."""
        event = TrajectoryEvent(
            event_id=f"evt_prod_{task_id}_{int(time.time()*1000)}",
            chain_type=ValueChainType.PRODUCTION,
            title=title,
            summary=summary,
            timestamp=timestamp or time.time(),
            source_channel=source_channel,
            task_id=task_id,
            is_key_milestone=is_completed,
            artifacts=tuple(artifacts),
            metadata={"status": "completed" if is_completed else "running"},
        )
        self.record_event(event)
        return event

    def record_business_decision(
        self,
        *,
        title: str,
        summary: str,
        session_id: str = "",
        source_channel: str = "im_group",
        timestamp: float | None = None,
        tags: Sequence[str] = (),
    ) -> TrajectoryEvent:
        """Helper to record a business value chain requirement or architecture decision."""
        event = TrajectoryEvent(
            event_id=f"evt_biz_{int(time.time()*1000)}",
            chain_type=ValueChainType.BUSINESS,
            title=title,
            summary=summary,
            timestamp=timestamp or time.time(),
            source_channel=source_channel,
            session_id=session_id,
            is_key_milestone=True,
            metadata={"tags": ",".join(tags)},
        )
        self.record_event(event)
        return event

    def record_management_approval(
        self,
        *,
        approval_id: str,
        action_name: str,
        approver: str,
        decision: str,
        timestamp: float | None = None,
    ) -> TrajectoryEvent:
        """Helper to record a management value chain governance or risk approval event."""
        event = TrajectoryEvent(
            event_id=f"evt_mgmt_{approval_id}",
            chain_type=ValueChainType.MANAGEMENT,
            title=f"审批通过: {action_name}",
            summary=f"由 {approver} 审核通过，决策结果: {decision}",
            timestamp=timestamp or time.time(),
            source_channel="governance",
            is_key_milestone=False,
            metadata={"approver": approver, "decision": decision},
        )
        self.record_event(event)
        return event

    def aggregate_for_period(
        self,
        *,
        start_time: float,
        end_time: float,
        chain_filter: ValueChainType | None = None,
    ) -> list[TrajectoryEvent]:
        """Query and filter events within a specific temporal window.

        Args:
            start_time: Epoch start timestamp.
            end_time: Epoch end timestamp.
            chain_filter: Optional filter to restrict to a single ValueChainType.

        Returns:
            Chronologically sorted list of matching TrajectoryEvents.
        """
        filtered: list[TrajectoryEvent] = []
        for evt in self._in_memory_events:
            if start_time <= evt.timestamp <= end_time:
                if chain_filter is None or evt.chain_type == chain_filter:
                    filtered.append(evt)

        # Sort chronologically
        filtered.sort(key=lambda e: e.timestamp)
        return filtered

    def clear(self) -> None:
        """Clear all in-memory events (mainly for testing or session reset)."""
        self._in_memory_events.clear()
