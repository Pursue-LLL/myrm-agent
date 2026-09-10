"""Unit tests for meeting_notes orchestration service."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.meeting_notes.models import (
    MeetingActionItem,
    StructuredMeetingNotes,
)
from app.services.meeting_notes.service import (
    _render_minutes_markdown,
    build_chunk_plan,
)


def test_build_chunk_plan_covers_full_duration() -> None:
    plan = build_chunk_plan(125 * 60, chunk_seconds=600)
    assert plan[0] == (0.0, 600.0)
    assert plan[1] == (600.0, 1200.0)
    assert plan[-1][1] == 125 * 60.0
    assert all(e - s <= 600 for s, e in plan)


def test_build_chunk_plan_zero_duration() -> None:
    plan = build_chunk_plan(0.0, chunk_seconds=600)
    assert plan == [(0.0, 600.0)]


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
    body = _render_minutes_markdown(notes, "[00:00] transcript line", 600.0)
    assert "# Weekly Sync" in body
    assert "## Decisions" in body
    assert "- [ ] Draft spec (owner: Alice, due: Friday)" in body
    assert "## Transcript" in body
