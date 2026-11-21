"""Unit tests for meeting_notes orchestration service."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.meeting_notes.models import (
    MeetingActionItem,
    StructuredMeetingNotes,
)
from app.services.meeting_notes.service import _render_minutes_markdown


def test_render_minutes_markdown_sections() -> None:
    notes = StructuredMeetingNotes(
        title="Weekly Sync",
        summary="Aligned on roadmap.",
        decisions=("Adopt plan A",),
        debate_points=("Timeline risk",),
        action_items=(
            MeetingActionItem(
                description="Draft spec", owner="Alice", due_hint="Friday"
            ),
        ),
    )
    body = _render_minutes_markdown(notes, "[00:00] transcript line")
    assert "# Weekly Sync" in body
    assert "## Decisions" in body
    assert "- [ ] Draft spec (owner: Alice, due: Friday)" in body
    assert "## Transcript" in body
