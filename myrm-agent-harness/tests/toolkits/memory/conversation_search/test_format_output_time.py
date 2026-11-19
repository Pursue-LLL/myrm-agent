"""A conversation hit's header ends with the time of what the hit stands for, so the model can tell when it happened."""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory.conversation_search.format_output import format_conversation_hit
from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchHit

_CREATED = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
_CONTENT = datetime(2026, 4, 2, 9, 30, 15, tzinfo=UTC)
_HEADER = "1. Planning (conversation_id: chat-1, score: 0.50, source: conversation_index"


def _hit(*, created_at: datetime | None = None, updated_at: datetime | None = None) -> ConversationSearchHit:
    return ConversationSearchHit(
        conversation_id="chat-1",
        title="Planning",
        snippet="Redis.",
        score=0.5,
        created_at=created_at,
        updated_at=updated_at,
    )


def test_the_header_ends_with_the_time_of_the_content_the_hit_stands_for() -> None:
    header = format_conversation_hit(1, _hit(created_at=_CREATED, updated_at=_CONTENT)).splitlines()[0]

    assert header == f"{_HEADER}, 2026-04-02T09:30:15+00:00)"


def test_the_header_names_the_creation_time_when_the_hit_has_no_content_time() -> None:
    header = format_conversation_hit(1, _hit(created_at=_CREATED)).splitlines()[0]

    assert header == f"{_HEADER}, 2026-03-01T08:00:00+00:00)"


def test_the_header_names_no_time_when_the_hit_has_none() -> None:
    header = format_conversation_hit(1, _hit()).splitlines()[0]

    assert header == f"{_HEADER})"
