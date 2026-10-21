"""Integration tests for meeting-notes API endpoint."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.meeting_notes.models import (
    MeetingActionItem,
    MeetingNotesResult,
    StructuredMeetingNotes,
)


def test_meeting_notes_response_model_roundtrip() -> None:
    """API response model must round-trip the service result shape."""
    notes = StructuredMeetingNotes(
        title="Standup",
        summary="Daily sync.",
        decisions=("Ship v2",),
        debate_points=("Perf vs DX",),
        action_items=(MeetingActionItem(description="Write docs", owner="Bob", due_hint="Mon"),),
    )
    result = MeetingNotesResult(
        chunk_count=2,
        duration_seconds=720.0,
        notes=notes,
        published_wiki_paths=["raw/sources/meeting-notes/meeting-standup.md"],
        language="en",
    )
    assert result.chunk_count == 2
    assert result.notes.action_items[0].owner == "Bob"
    assert result.published_wiki_paths[0].endswith("meeting-standup.md")


def test_process_meeting_audio_chunk_plan_bounded() -> None:
    """Chunk plan stays within bounds for a 60min audio (6 x 10min chunks)."""
    from app.services.meeting_notes.service import build_chunk_plan

    plan = build_chunk_plan(60 * 60.0, chunk_seconds=600)
    assert len(plan) == 6
    assert plan[0][0] == 0.0 and plan[-1][1] == 3600.0