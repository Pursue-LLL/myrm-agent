"""Data models for Weekly Report SOP and Trajectory Aggregation.

[INPUT]
- dataclasses (standard library)
- typing (standard library)
- enum (standard library)

[OUTPUT]
- TrajectoryEventSource: Enum for origin of events (SANDBOX, CHAT, ARTIFACT, APPROVAL)
- TrajectoryEvent: Strongly-typed atomic action/output record
- WeeklyReportSection: Structured block in a generated weekly report
- WeeklyReportDocument: Complete structured weekly report entity
- ChatKnowledgeExtractRequest: Input schema for chat-to-knowledge extraction
- ChatKnowledgeExtractResult: Output schema with extracted concepts and wiki mutation path

[POS]
Domain models for organizational trajectory aggregation, weekly report generation, and chat-to-knowledge extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class TrajectoryEventSource(str, Enum):
    """Source domain of a trajectory action or artifact."""

    SANDBOX_EXECUTION = "sandbox_execution"
    CHAT_DECISION = "chat_decision"
    DELIVERY_ARTIFACT = "delivery_artifact"
    REMOTE_APPROVAL = "remote_approval"


@dataclass(frozen=True)
class TrajectoryEvent:
    """Atomic record representing an action, artifact, or decision in the organization."""

    event_id: str
    source: TrajectoryEventSource
    title: str
    summary: str
    timestamp: float
    task_id: Optional[str] = None
    channel: Optional[str] = None
    artifact_path: Optional[str] = None
    artifact_hash: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class WeeklyReportSection:
    """A semantic section in a weekly report."""

    section_id: str
    title: str
    items: List[str]
    evidence_events: List[TrajectoryEvent] = field(default_factory=list)


@dataclass(frozen=True)
class WeeklyReportDocument:
    """Complete weekly report generated from organizational trajectories."""

    report_id: str
    title: str
    period_start: str
    period_end: str
    author: str
    sections: List[WeeklyReportSection]
    raw_markdown: str
    created_at: float
    total_events_aggregated: int


@dataclass(frozen=True)
class ChatKnowledgeExtractRequest:
    """Request to extract structured knowledge from chat messages."""

    chat_context: str
    channel: str
    session_id: str
    target_wiki_category: str = "engineering/decisions"
    author: str = "agent"


@dataclass(frozen=True)
class ChatKnowledgeExtractResult:
    """Result of structured knowledge extraction from chat."""

    concept_title: str
    summary: str
    markdown_content: str
    wiki_rel_path: str
    tags: List[str]
    success: bool
    error_message: Optional[str] = None
