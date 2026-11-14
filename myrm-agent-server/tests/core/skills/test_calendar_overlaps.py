"""Tests for the overlap detection of the google-workspace prebuilt skill.

The daily briefing reports conflicts from the events themselves, because a fixed "no conflicts" line would ignore
the calendar and a model that compares event times itself misses overlaps. These tests pin what counts as a
conflict.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills" / "google-workspace" / "scripts"


@pytest.fixture
def find_conflicts(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[dict[str, object]]]:
    # google_api.py imports the module by its bare name from the staged scripts directory; so does this test.
    monkeypatch.syspath_prepend(str(SCRIPTS_DIR))
    return importlib.import_module("calendar_overlaps").find_conflicts


def _at(clock: str) -> str:
    return f"2026-06-25T{clock}:00+08:00"


def _timed(event_id: str, start: str, end: str, **extra: object) -> dict[str, object]:
    return {"id": event_id, "summary": event_id.title(), "start": {"dateTime": start}, "end": {"dateTime": end}, **extra}


def _ids(pairs: list[dict[str, object]]) -> list[tuple[object, object]]:
    return [(pair["first"]["id"], pair["second"]["id"]) for pair in pairs]


_MEETING = _timed("meeting", _at("09:00"), _at("10:00"))

# Events that would overlap the 09:00-10:00 meeting if they blocked time.
_NON_BLOCKING_EVENTS = [
    pytest.param(_timed("other", _at("09:30"), _at("10:30"), status="cancelled"), id="cancelled"),
    pytest.param(_timed("other", _at("09:30"), _at("10:30"), transparency="transparent"), id="free-time"),
    pytest.param(
        _timed(
            "other",
            _at("09:30"),
            _at("10:30"),
            attendees=[
                {"email": "alice@example.com", "responseStatus": "accepted"},
                {"email": "me@example.com", "self": True, "responseStatus": "declined"},
            ],
        ),
        id="declined-by-the-user",
    ),
    pytest.param(
        {"id": "other", "summary": "Holiday", "start": {"date": "2026-06-25"}, "end": {"date": "2026-06-26"}},
        id="all-day",
    ),
    pytest.param({"id": "other", "start": {"dateTime": _at("09:30")}}, id="missing-end"),
    pytest.param(_timed("other", "2026-06-25T09:30:00", "2026-06-25T10:30:00"), id="no-utc-offset"),
    pytest.param(_timed("other", _at("09:30"), _at("09:30")), id="zero-length"),
    pytest.param(_timed("other", _at("10:30"), _at("09:30")), id="end-before-start"),
    pytest.param(_timed("other", "not a time", _at("10:30")), id="unparseable-start"),
    pytest.param("not an event", id="not-an-object"),
    pytest.param(None, id="null"),
]

# Events that look close to the ones above but do block time.
_BLOCKING_EVENTS = [
    pytest.param(_timed("other", _at("09:30"), _at("10:30")), id="plain"),
    pytest.param(_timed("other", _at("09:30"), _at("10:30"), transparency="opaque"), id="marked-busy"),
    pytest.param(_timed("other", _at("09:30"), _at("10:30"), status="tentative"), id="tentative-event"),
    pytest.param(
        _timed(
            "other",
            _at("09:30"),
            _at("10:30"),
            attendees=[{"email": "me@example.com", "self": True, "responseStatus": "tentative"}],
        ),
        id="tentatively-accepted",
    ),
    pytest.param(
        _timed(
            "other",
            _at("09:30"),
            _at("10:30"),
            attendees=[{"email": "me@example.com", "self": True, "responseStatus": "needsAction"}],
        ),
        id="not-answered-yet",
    ),
    pytest.param(
        _timed(
            "other",
            _at("09:30"),
            _at("10:30"),
            attendees=[{"email": "alice@example.com", "responseStatus": "declined"}],
        ),
        id="declined-by-someone-else",
    ),
]


def test_overlapping_events_form_a_pair_that_carries_their_times(find_conflicts) -> None:
    review = _timed("review", _at("09:30"), _at("10:30"))

    assert find_conflicts([_MEETING, review]) == [
        {
            "first": {"id": "meeting", "summary": "Meeting", "start": _at("09:00"), "end": _at("10:00")},
            "second": {"id": "review", "summary": "Review", "start": _at("09:30"), "end": _at("10:30")},
        }
    ]


def test_no_events_have_no_conflicts(find_conflicts) -> None:
    assert find_conflicts([]) == []


def test_events_that_only_touch_do_not_conflict(find_conflicts) -> None:
    assert find_conflicts([_MEETING, _timed("next", _at("10:00"), _at("11:00"))]) == []


def test_an_event_inside_another_conflicts(find_conflicts) -> None:
    offsite = _timed("offsite", _at("08:00"), _at("12:00"))

    assert _ids(find_conflicts([offsite, _MEETING])) == [("offsite", "meeting")]


def test_events_are_compared_as_instants_not_as_clock_text(find_conflicts) -> None:
    same_moment_in_utc = _timed("utc-sync", "2026-06-25T01:30:00Z", "2026-06-25T02:30:00Z")  # 09:30-10:30 at +08:00
    same_clock_hours_later = _timed("late-call", "2026-06-25T09:30:00Z", "2026-06-25T10:30:00Z")  # 17:30-18:30 at +08:00

    assert _ids(find_conflicts([_MEETING, same_moment_in_utc, same_clock_hours_later])) == [("meeting", "utc-sync")]


@pytest.mark.parametrize("other", _NON_BLOCKING_EVENTS)
def test_an_event_that_cannot_block_time_never_conflicts(find_conflicts, other: object) -> None:
    assert find_conflicts([_MEETING, other]) == []


@pytest.mark.parametrize("other", _BLOCKING_EVENTS)
def test_an_event_that_blocks_time_conflicts(find_conflicts, other: object) -> None:
    assert _ids(find_conflicts([_MEETING, other])) == [("meeting", "other")]


def test_pairs_follow_start_order_whatever_the_input_order(find_conflicts) -> None:
    first = _timed("a", _at("09:00"), _at("11:00"))
    middle = _timed("b", _at("10:00"), _at("12:00"))
    last = _timed("c", _at("11:30"), _at("13:00"))  # shares a moment with "b" but never with "a"

    assert _ids(find_conflicts([last, first, middle])) == [("a", "b"), ("b", "c")]


def test_identical_slots_keep_their_input_order(find_conflicts) -> None:
    pairs = find_conflicts([_timed("x", _at("09:00"), _at("10:00")), _timed("y", _at("09:00"), _at("10:00"))])

    assert _ids(pairs) == [("x", "y")]


def test_pairs_are_capped_at_ten_and_start_with_the_earliest(find_conflicts) -> None:
    stacked = [_timed(f"e{n}", _at("09:00"), _at("10:00")) for n in range(6)]  # 15 overlapping pairs

    pairs = find_conflicts(stacked)

    assert len(pairs) == 10
    assert _ids(pairs)[:6] == [("e0", "e1"), ("e0", "e2"), ("e0", "e3"), ("e0", "e4"), ("e0", "e5"), ("e1", "e2")]
    assert len(find_conflicts(stacked, limit=3)) == 3


@pytest.mark.parametrize("summary", [{}, {"summary": ""}, {"summary": None}], ids=["missing", "empty", "null"])
def test_an_untitled_event_is_named_as_google_calendar_names_it(find_conflicts, summary: dict[str, object]) -> None:
    untitled = {"id": "untitled", "start": {"dateTime": _at("09:30")}, "end": {"dateTime": _at("10:30")}, **summary}

    [pair] = find_conflicts([_MEETING, untitled])

    assert pair["second"]["summary"] == "(No title)"
