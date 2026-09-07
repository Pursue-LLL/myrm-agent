"""Weekly report generation service.

[INPUT]
- .models::TrajectoryEvent, TrajectoryEventSource, WeeklyReportDocument, WeeklyReportSection
- .trajectory_aggregator::TrajectoryAggregator
- time, datetime (standard library)
- typing (standard library)

[OUTPUT]
- WeeklyReportService: Assembles multi-source trajectory events into structured, evidence-backed weekly reports.

[POS]
Generates professional, auditable Markdown/HTML weekly reports from sandbox actions, artifacts, and chat decisions.
"""

from __future__ import annotations

import datetime
import time
from typing import List, Optional

from app.services.weekly_report.models import (
    TrajectoryEvent,
    TrajectoryEventSource,
    WeeklyReportDocument,
    WeeklyReportSection,
)
from app.services.weekly_report.trajectory_aggregator import TrajectoryAggregator


class WeeklyReportService:
    """Orchestrates trajectory collection and formats standard weekly report documents."""

    def __init__(self, aggregator: Optional[TrajectoryAggregator] = None) -> None:
        self.aggregator = aggregator or TrajectoryAggregator()

    def generate_report(
        self,
        title: str = "Weekly Engineering & Operations Report",
        author: str = "Myrm Autonomous Agent",
        period_days: int = 7,
        end_time: Optional[float] = None,
    ) -> WeeklyReportDocument:
        """Generate a structured weekly report from events within the time window."""
        now = end_time if end_time is not None else time.time()
        start = now - (period_days * 86400)

        dt_start = datetime.datetime.fromtimestamp(
            start, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%d")
        dt_end = datetime.datetime.fromtimestamp(
            now, tz=datetime.timezone.utc
        ).strftime("%Y-%m-%d")

        events = self.aggregator.get_events(start_time=start, end_time=now)

        # Categorize events into standard sections
        sandbox_events: List[TrajectoryEvent] = []
        artifact_events: List[TrajectoryEvent] = []
        decision_events: List[TrajectoryEvent] = []
        approval_events: List[TrajectoryEvent] = []

        for e in events:
            if e.source == TrajectoryEventSource.SANDBOX_EXECUTION:
                sandbox_events.append(e)
            elif e.source == TrajectoryEventSource.DELIVERY_ARTIFACT:
                artifact_events.append(e)
            elif e.source == TrajectoryEventSource.CHAT_DECISION:
                decision_events.append(e)
            elif e.source == TrajectoryEventSource.REMOTE_APPROVAL:
                approval_events.append(e)

        sections: List[WeeklyReportSection] = []

        # Section 1: Completed Tasks & Sandbox Runs
        task_items = [f"**{e.title}**: {e.summary}" for e in sandbox_events] or [
            "No sandbox tasks recorded in this period."
        ]
        sections.append(
            WeeklyReportSection(
                section_id="tasks_completed",
                title="1. Key Executions & Sandbox Deliverables",
                items=task_items,
                evidence_events=sandbox_events,
            )
        )

        # Section 2: Code & Deliverable Artifacts
        artifact_items = [
            f"**{e.title}** (`{e.artifact_path or 'artifact'}`) - SHA256: `{e.artifact_hash or 'n/a'}`: {e.summary}"
            for e in artifact_events
        ] or ["No new artifacts generated in this period."]
        sections.append(
            WeeklyReportSection(
                section_id="artifacts_produced",
                title="2. Tangible Artifacts & Code Deliverables",
                items=artifact_items,
                evidence_events=artifact_events,
            )
        )

        # Section 3: Technical Consensus & Architecture Decisions
        decision_items = [f"**{e.title}**: {e.summary}" for e in decision_events] or [
            "No architecture decisions recorded."
        ]
        sections.append(
            WeeklyReportSection(
                section_id="decisions_made",
                title="3. Architectural & Team Decisions",
                items=decision_items,
                evidence_events=decision_events,
            )
        )

        # Section 4: Operational Approvals & Governance
        approval_items = [f"**{e.title}**: {e.summary}" for e in approval_events] or [
            "No pending or executed remote approvals."
        ]
        sections.append(
            WeeklyReportSection(
                section_id="approvals_and_risks",
                title="4. Governance & Safety Approvals",
                items=approval_items,
                evidence_events=approval_events,
            )
        )

        raw_markdown = self._render_markdown(
            title=title,
            author=author,
            period_start=dt_start,
            period_end=dt_end,
            sections=sections,
            total_events=len(events),
        )

        report_id = f"weekly_report_{dt_end.replace('-', '')}_{int(now)}"

        return WeeklyReportDocument(
            report_id=report_id,
            title=title,
            period_start=dt_start,
            period_end=dt_end,
            author=author,
            sections=sections,
            raw_markdown=raw_markdown,
            created_at=now,
            total_events_aggregated=len(events),
        )

    @staticmethod
    def _render_markdown(
        title: str,
        author: str,
        period_start: str,
        period_end: str,
        sections: List[WeeklyReportSection],
        total_events: int,
    ) -> str:
        """Render markdown document with summary headers and evidence links."""
        lines = [
            f"# {title}",
            f"> **Period**: {period_start} to {period_end}  ",
            f"> **Author**: {author}  ",
            f"> **Total Trajectory Events Aggregated**: {total_events}",
            "",
            "---",
            "",
        ]

        for sec in sections:
            lines.append(f"## {sec.title}")
            for item in sec.items:
                lines.append(f"- {item}")
            lines.append("")

        lines.extend(
            [
                "---",
                "*(Generated automatically by Myrm Trajectory Aggregation & Weekly Report SOP Engine)*",
            ]
        )
        return "\n".join(lines)
