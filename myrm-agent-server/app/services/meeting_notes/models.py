"""Meeting notes pipeline data models.

[INPUT]
- None (pure data models)

[OUTPUT]
- TranscriptChunk: one audio slice with its transcription payload
- MeetingActionItem: one actionable task extracted from the meeting
- StructuredMeetingNotes: LLM-distilled meeting minutes payload
- MeetingNotesResult: end-to-end pipeline result

[POS]
Single source of truth for meeting-notes orchestration data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TranscriptChunk:
    """One audio slice and its transcription payload."""

    index: int
    start_seconds: float
    end_seconds: float
    text: str = ""


@dataclass(frozen=True)
class MeetingActionItem:
    """One actionable task extracted from the meeting."""

    description: str
    owner: str | None = None
    due_hint: str | None = None


@dataclass(frozen=True)
class StructuredMeetingNotes:
    """LLM-distilled meeting minutes payload."""

    title: str
    summary: str
    decisions: tuple[str, ...] = ()
    debate_points: tuple[str, ...] = ()
    action_items: tuple[MeetingActionItem, ...] = ()


@dataclass
class MeetingNotesResult:
    """End-to-end pipeline result for one meeting audio import."""

    chunk_count: int
    duration_seconds: float
    notes: StructuredMeetingNotes
    published_wiki_paths: list[str] = field(default_factory=list)
    language: str | None = None