"""Overlap detection between the timed events of a Google Calendar response.

[INPUT]
- Events as decoded from the `items` of a Google Calendar events.list response

[OUTPUT]
- find_conflicts: Pairs of busy timed events whose times overlap, earliest first, capped at MAX_CONFLICT_PAIRS

[POS]
Stdlib-only sibling of google_api.py, imported from the staged scripts directory. The script reports overlaps itself
because a model that compares event times in its head misses some and invents others.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

MAX_CONFLICT_PAIRS = 10

# Google Calendar shows an untitled event under this name; the model reads it instead of a null.
_NO_TITLE = "(No title)"


@dataclass(frozen=True)
class _BusySlot:
    start: datetime
    end: datetime
    event_id: object
    summary: str
    start_text: str
    end_text: str

    def describe(self) -> dict[str, object]:
        # The original strings keep the UTC offset Google returned, which is the one the user's calendar shows.
        return {"id": self.event_id, "summary": self.summary, "start": self.start_text, "end": self.end_text}


def find_conflicts(events: Iterable[object], *, limit: int = MAX_CONFLICT_PAIRS) -> list[dict[str, object]]:
    """Return up to `limit` overlapping pairs of busy timed events, ordered by start time.

    Intervals are half-open: an event that starts when another ends is not a conflict.
    """
    slots = sorted((slot for event in events if (slot := _busy_slot(event)) is not None), key=_sort_key)
    pairs: list[dict[str, object]] = []
    for index, first in enumerate(slots):
        for second in slots[index + 1 :]:
            if second.start >= first.end:
                break  # slots are sorted by start, so every later one starts after `first` ends too
            pairs.append({"first": first.describe(), "second": second.describe()})
            if len(pairs) == limit:
                return pairs
    return pairs


def _sort_key(slot: _BusySlot) -> tuple[datetime, datetime]:
    return slot.start, slot.end


def _busy_slot(event: object) -> _BusySlot | None:
    """The event as a busy time slot, or None when it cannot collide with another event.

    Cancelled, free (transparent), declined and all-day events do not block time, and an event whose start or end is
    missing, has no UTC offset or does not lie after its start has no interval that can be compared.
    """
    if not isinstance(event, dict):
        return None
    if event.get("status") == "cancelled" or event.get("transparency") == "transparent":
        return None
    if _declined_by_user(event):
        return None
    start = _timed_bound(event.get("start"))
    end = _timed_bound(event.get("end"))
    if start is None or end is None or end[1] <= start[1]:
        return None
    summary = event.get("summary")
    return _BusySlot(
        start=start[1],
        end=end[1],
        event_id=event.get("id"),
        summary=summary if isinstance(summary, str) and summary else _NO_TITLE,
        start_text=start[0],
        end_text=end[0],
    )


def _declined_by_user(event: dict[object, object]) -> bool:
    attendees = event.get("attendees")
    if not isinstance(attendees, list):
        return False
    return any(
        isinstance(attendee, dict) and attendee.get("self") is True and attendee.get("responseStatus") == "declined"
        for attendee in attendees
    )


def _timed_bound(bound: object) -> tuple[str, datetime] | None:
    """The `dateTime` of an event start or end as (text, moment); an all-day bound carries `date` and yields None."""
    text = bound.get("dateTime") if isinstance(bound, dict) else None
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return (text, moment) if moment.tzinfo is not None else None
