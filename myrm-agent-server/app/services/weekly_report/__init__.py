"""Weekly report and organizational trajectory aggregation services.

[INPUT]
- .models (POS: Strongly-typed event and report schemas)
- .trajectory_aggregator::TrajectoryAggregator (POS: Multi-source event collector)
- .chat_to_knowledge::ChatToKnowledgeArchiver (POS: Chat-to-wiki extractor)
- .weekly_report_service::WeeklyReportService (POS: Weekly report SOP generator)

[OUTPUT]
- TrajectoryEvent
- TrajectoryEventSource
- WeeklyReportSection
- WeeklyReportDocument
- ChatKnowledgeExtractRequest
- ChatKnowledgeExtractResult
- TrajectoryAggregator
- ChatToKnowledgeArchiver
- WeeklyReportService

[POS]
Package entry point exposing trajectory aggregation, chat-to-knowledge extraction, and weekly report services.
"""

from __future__ import annotations

from app.services.weekly_report.chat_to_knowledge import ChatToKnowledgeArchiver
from app.services.weekly_report.models import (
    ChatKnowledgeExtractRequest,
    ChatKnowledgeExtractResult,
    TrajectoryEvent,
    TrajectoryEventSource,
    WeeklyReportDocument,
    WeeklyReportSection,
)
from app.services.weekly_report.trajectory_aggregator import TrajectoryAggregator
from app.services.weekly_report.weekly_report_service import WeeklyReportService

__all__ = [
    "TrajectoryEvent",
    "TrajectoryEventSource",
    "WeeklyReportSection",
    "WeeklyReportDocument",
    "ChatKnowledgeExtractRequest",
    "ChatKnowledgeExtractResult",
    "TrajectoryAggregator",
    "ChatToKnowledgeArchiver",
    "WeeklyReportService",
]
