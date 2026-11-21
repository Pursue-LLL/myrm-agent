"""The recall index's timestamps read back as the instants they name.

The repository reads the index with raw SQL, and SQLite hands such a column over as the text it stored: UTC without an
offset when the database filled it in or a rebuild copied a message's time, with an offset when an append bound an aware
datetime. A row that cannot read that text carries no time at all, so the mapper turns every form into an aware UTC
instant, and a value that is no time into None rather than a guess. A time with an offset can name an instant just past
the last (or before the first) one UTC can write down; that reads as None too, never as an error. Every test runs with
the process clock at UTC+8, so a time without an offset that is read as the host's local time comes back eight hours
off, on a UTC host too.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.database.repositories.conversation_recall.types import (
    optional_datetime,
    recall_document_row,
    recall_row,
)
from tests.support.host_clock import pin_host_clock_to_utc_plus_8

_INSTANT = datetime(2026, 4, 17, 12, 30, 45, tzinfo=UTC)
_PLUS_EIGHT = timezone(timedelta(hours=8))


@pytest.fixture(autouse=True)
def _host_clock_at_utc_plus_8() -> Iterator[None]:
    """Run every test here with the process clock at UTC+8, so a time read as the host's local time is eight hours off."""
    with pin_host_clock_to_utc_plus_8():
        yield


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("2026-04-17 12:30:45", _INSTANT),
        ("2026-04-17 12:30:45.250000", _INSTANT.replace(microsecond=250_000)),
        ("2026-04-17 12:30:45+00:00", _INSTANT),
        ("2026-04-17 12:30:45.250000+00:00", _INSTANT.replace(microsecond=250_000)),
        ("2026-04-17 20:30:45+08:00", _INSTANT),
        ("2026-04-17T12:30:45Z", _INSTANT),
        (datetime(2026, 4, 17, 12, 30, 45), _INSTANT),
        (_INSTANT, _INSTANT),
        (datetime(2026, 4, 17, 20, 30, 45, tzinfo=_PLUS_EIGHT), _INSTANT),
    ],
    ids=[
        "database-default",
        "orm-microseconds",
        "bound-aware",
        "bound-aware-microseconds",
        "offset-converted",
        "zulu",
        "driver-naive-datetime",
        "driver-aware-datetime",
        "driver-offset-datetime",
    ],
)
def test_a_stored_timestamp_reads_back_as_the_utc_instant_it_names(stored: object, expected: datetime) -> None:
    value = optional_datetime({"at": stored}, "at")

    assert value == expected
    assert value is not None
    assert value.utcoffset() == timedelta(0)


@pytest.mark.parametrize("stored", [None, "", "yesterday", "2026-13-45 99:99:99", 1_776_000_000, 1.5, b"2026-04-17"])
def test_a_value_that_is_no_time_reads_as_none(stored: object) -> None:
    assert optional_datetime({"at": stored}, "at") is None


@pytest.mark.parametrize(
    "stored",
    [
        "9999-12-31 23:59:59-05:00",
        "0001-01-01 00:00:00+05:00",
        datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=-5))),
    ],
    ids=["text-past-the-last-instant", "text-before-the-first-instant", "datetime-past-the-last-instant"],
)
def test_an_instant_utc_cannot_write_down_reads_as_none(stored: object) -> None:
    assert optional_datetime({"at": stored}, "at") is None


def test_a_missing_column_reads_as_none() -> None:
    assert optional_datetime({}, "at") is None


def test_the_row_mappers_read_every_time_column_through_the_same_rule() -> None:
    mapping = {
        "chat_id": "chat-1",
        "source": "web",
        "snippet": "text",
        "rank": -1.0,
        "last_message_at": "2026-04-17 12:30:45.250000",
        "created_at": "2026-03-01 08:00:00",
        "is_excluded": 0,
    }

    hit = recall_row(mapping)
    document = recall_document_row(mapping)

    assert hit.last_message_at == _INSTANT.replace(microsecond=250_000)
    assert hit.created_at == datetime(2026, 3, 1, 8, 0, tzinfo=UTC)
    assert document.last_message_at == hit.last_message_at
