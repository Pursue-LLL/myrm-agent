"""A conversation hit's header ends with the time of what the hit stands for, so the model can tell when it happened.

The time is written in the requester's zone when the request carries one, in UTC otherwise. Every test runs with the
process clock at UTC+8, so a time without an offset that is read as the host's local time shows up as a header eight
hours off, on a UTC host too.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from myrm_agent_harness.toolkits.memory.conversation_search.format_output import format_conversation_hit
from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchHit
from tests.support.host_clock import pin_host_clock_to_utc_plus_8

_CREATED = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
_CONTENT = datetime(2026, 4, 2, 9, 30, 15, tzinfo=UTC)
_HEADER = "1. Planning (conversation_id: chat-1, score: 0.50, source: conversation_index"


@pytest.fixture(autouse=True)
def _host_clock_at_utc_plus_8() -> Iterator[None]:
    """Run every test here with the process clock at UTC+8, so a time read as the host's local time is eight hours off."""
    with pin_host_clock_to_utc_plus_8():
        yield


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


@pytest.mark.parametrize(
    ("instant", "zone", "written"),
    [
        # Half past five in the evening of the 2nd in UTC is the small hours of the 3rd in Shanghai.
        (datetime(2026, 4, 2, 17, 30, 15, 250_000, tzinfo=UTC), "Asia/Shanghai", "2026-04-03T01:30:15.250000+08:00"),
        # The offset is the zone's at that instant: New York is five hours behind UTC in winter and four in summer.
        (datetime(2026, 1, 15, 12, tzinfo=UTC), "America/New_York", "2026-01-15T07:00:00-05:00"),
        (datetime(2026, 7, 15, 12, tzinfo=UTC), "America/New_York", "2026-07-15T08:00:00-04:00"),
        # A time without an offset is the UTC the index stores.
        (datetime(2026, 4, 2, 17, 30, 15), "Asia/Shanghai", "2026-04-03T01:30:15+08:00"),
        (_CONTENT, "UTC", "2026-04-02T09:30:15+00:00"),
    ],
    ids=["next-day", "winter-offset", "summer-offset", "no-offset-reads-as-utc", "utc-zone"],
)
def test_the_header_time_is_written_in_the_requesters_zone(instant: datetime, zone: str, written: str) -> None:
    header = format_conversation_hit(1, _hit(updated_at=instant), zone=zone).splitlines()[0]

    assert header == f"{_HEADER}, {written})"


def test_the_creation_time_a_header_falls_back_to_is_written_in_the_zone_too() -> None:
    header = format_conversation_hit(1, _hit(created_at=_CREATED), zone="Asia/Shanghai").splitlines()[0]

    assert header == f"{_HEADER}, 2026-03-01T16:00:00+08:00)"


@pytest.mark.parametrize(
    ("instant", "zone"),
    [
        (datetime.max.replace(tzinfo=UTC), "Asia/Shanghai"),
        (datetime.min.replace(tzinfo=UTC), "America/New_York"),
    ],
    ids=["past-the-last-instant-in-the-zone", "before-the-first-instant-in-the-zone"],
)
def test_an_instant_the_zone_cannot_hold_is_written_in_utc(instant: datetime, zone: str) -> None:
    header = format_conversation_hit(1, _hit(updated_at=instant), zone=zone).splitlines()[0]

    assert header == f"{_HEADER}, {instant.isoformat()})"
