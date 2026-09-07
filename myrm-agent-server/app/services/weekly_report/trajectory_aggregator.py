"""Multi-source organizational trajectory aggregator.

[INPUT]
- .models::TrajectoryEvent, TrajectoryEventSource
- app.channels.delegation.delegation_models::DelegationTask, DeliveryArtifact (POS: Sandbox tasks and artifacts)
- typing (standard library)

[OUTPUT]
- TrajectoryAggregator: Core class for collecting, deduplicating, and indexing events across sandbox, chat, and approvals.

[POS]
Aggregates heterogeneous action records from sandboxes, IM channels, and artifacts into chronological, evidence-backed streams.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from app.services.weekly_report.models import TrajectoryEvent, TrajectoryEventSource


class TrajectoryAggregator:
    """Collects and organizes events across sandbox execution, artifacts, and decisions."""

    def __init__(self) -> None:
        self._events: Dict[str, TrajectoryEvent] = {}

    def record_event(self, event: TrajectoryEvent) -> None:
        """Register a new trajectory event."""
        self._events[event.event_id] = event

    def record_sandbox_task(
        self,
        task_id: str,
        title: str,
        summary: str,
        channel: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> TrajectoryEvent:
        """Convenience method to record a completed sandbox task."""
        event_id = f"sandbox_{task_id}_{int(time.time() * 1000)}"
        event = TrajectoryEvent(
            event_id=event_id,
            source=TrajectoryEventSource.SANDBOX_EXECUTION,
            title=title,
            summary=summary,
            timestamp=time.time(),
            task_id=task_id,
            channel=channel,
            tags=tags or ["sandbox", "execution"],
        )
        self.record_event(event)
        return event

    def record_artifact(
        self,
        task_id: str,
        artifact_path: str,
        artifact_hash: str,
        title: str,
        summary: str,
        channel: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> TrajectoryEvent:
        """Convenience method to record a generated deliverable artifact."""
        event_id = f"artifact_{task_id}_{artifact_hash[:8]}"
        event = TrajectoryEvent(
            event_id=event_id,
            source=TrajectoryEventSource.DELIVERY_ARTIFACT,
            title=title,
            summary=summary,
            timestamp=time.time(),
            task_id=task_id,
            channel=channel,
            artifact_path=artifact_path,
            artifact_hash=artifact_hash,
            tags=tags or ["artifact", "deliverable"],
        )
        self.record_event(event)
        return event

    def record_chat_decision(
        self,
        session_id: str,
        title: str,
        decision_summary: str,
        channel: str,
        tags: Optional[List[str]] = None,
    ) -> TrajectoryEvent:
        """Record an explicit consensus or key technical decision made in chat."""
        event_id = f"chat_{session_id}_{int(time.time() * 1000)}"
        event = TrajectoryEvent(
            event_id=event_id,
            source=TrajectoryEventSource.CHAT_DECISION,
            title=title,
            summary=decision_summary,
            timestamp=time.time(),
            channel=channel,
            tags=tags or ["chat", "decision"],
        )
        self.record_event(event)
        return event

    def get_events(
        self,
        source: Optional[TrajectoryEventSource] = None,
        tag: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[TrajectoryEvent]:
        """Query collected events with optional filters, sorted chronologically."""
        results: List[TrajectoryEvent] = []
        for event in self._events.values():
            if source and event.source != source:
                continue
            if tag and tag not in event.tags:
                continue
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            results.append(event)

        return sorted(results, key=lambda e: e.timestamp)

    def clear(self) -> None:
        """Clear all stored events."""
        self._events.clear()
