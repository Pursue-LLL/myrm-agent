"""Meeting notes data models.

[INPUT]
- None (pure data models)

[OUTPUT]
- MeetingActionItem: one actionable task extracted from the meeting
- StructuredMeetingNotes: LLM-distilled meeting minutes payload

[POS]
Single source of truth for meeting-notes orchestration data structures.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    risks: tuple[str, ...] = ()
    action_items: tuple[MeetingActionItem, ...] = ()
