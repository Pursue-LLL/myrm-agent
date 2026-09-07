"""Data models and type definitions for weekly report SOP and trajectory aggregation.

Strictly follows code_quality_guidelines: 0 Any, immutable dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReportRoleMode(str, Enum):
    """Role-adaptive projection modes for weekly report rendering."""
    GENERAL = "general"
    ENGINEER = "engineer"
    PRODUCT = "product"
    EXECUTIVE = "executive"


class TrajectorySourceKind(str, Enum):
    """Source origin of trajectory items."""
    DELEGATION_TASK = "delegation_task"
    DELIVERY_ARTIFACT = "delivery_artifact"
    CHAT_DECISION = "chat_decision"
    MANUAL_ENTRY = "manual_entry"


@dataclass(frozen=True)
class TrajectoryItem:
    """A discrete unit of verified execution trajectory."""
    source_id: str
    source_kind: TrajectorySourceKind
    title: str
    summary: str
    timestamp_ms: int
    artifact_paths: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WeeklyReportSection:
    """A structured section within the generated weekly report."""
    heading: str
    items: tuple[str, ...]
    role_weight: float = 1.0


@dataclass(frozen=True)
class WeeklyReportPayload:
    """Full assembled weekly report model."""
    start_time_ms: int
    end_time_ms: int
    role_mode: ReportRoleMode
    title: str
    sections: tuple[WeeklyReportSection, ...]
    attached_artifacts: tuple[str, ...]
    markdown_content: str
    summary_for_im: str


@dataclass(frozen=True)
class WikiIngestPayload:
    """Payload for archiving high-value chat decisions to Wiki."""
    channel_id: str
    topic_title: str
    content_raw: str
    tags: tuple[str, ...]
    fingerprint_sha256: str
    created_at_ms: int


@dataclass(frozen=True)
class WikiIngestResult:
    """Result of wiki archive operation."""
    success: bool
    wiki_path: str
    is_duplicate: bool
    message: str
