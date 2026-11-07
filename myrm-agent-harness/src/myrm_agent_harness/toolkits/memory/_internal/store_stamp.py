"""The store stamp: when a memory reached the store, and which writes have not finished reaching it.

[INPUT]
- memory.types::BaseMemory (POS: memory data models)

[OUTPUT]
- STORED_TS_KEY: payload key of the stamp, in epoch seconds
- stored_ts_payload, stored_at_from_metadata: the stamp's payload form
- persisting: stamp memories on their way into the store and keep the write registered until it has finished
- settled_through: the latest instant by which every write stamped at or before it has finished

[POS]
Gives consolidation an arrival order that business time cannot. ``created_at`` is when a fact was proposed or
true, and a late approval, an import and a correction each carry their own, so a cursor over it loses whatever
arrives behind it. The stamp comes from a clock that never repeats within a process, so no two memories tie at
a window's cut. The registry covers the span between stamping and visibility: a cursor never moves past a write
that another task is still persisting. Stamps are per process; writers in other processes are not covered.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from itertools import count

from myrm_agent_harness.toolkits.memory.types import BaseMemory

STORED_TS_KEY = "stored_ts"

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# Plain lock: it guards a few integers and is never held across an await.
_lock = threading.Lock()
_last_stamp_us = 0
_write_ids = count()
# Write id -> the first stamp of a write that has not finished persisting.
_in_flight: dict[int, int] = {}


def _at(microseconds: int) -> datetime:
    return _EPOCH + timedelta(microseconds=microseconds)


def _claim(stamps: int) -> int:
    """First of ``stamps`` consecutive microsecond values, all later than any claimed before. Hold ``_lock``."""
    global _last_stamp_us
    first = max(time.time_ns() // 1000, _last_stamp_us + 1)
    _last_stamp_us = first + stamps - 1
    return first


@contextmanager
def persisting(memories: Sequence[BaseMemory]) -> Iterator[None]:
    """Stamp ``memories`` and keep their write registered until the block ends, however it ends.

    Each memory gets its own stamp, replacing any it carried. The block has to hold the whole write: the
    registration is what keeps ``settled_through`` below the stamps of memories that are not visible yet.
    """
    if not memories:
        yield
        return
    with _lock:
        first = _claim(len(memories))
        write_id = next(_write_ids)
        _in_flight[write_id] = first
    try:
        for offset, memory in enumerate(memories):
            memory.stored_at = _at(first + offset)
        yield
    finally:
        with _lock:
            del _in_flight[write_id]


def settled_through() -> datetime:
    """The latest instant by which every write stamped at or before it has finished.

    Reading it advances the clock past itself, so every write that starts afterwards is stamped later.
    """
    with _lock:
        now = _claim(1)
        earliest = min(_in_flight.values(), default=None)
        # An in-flight stamp was claimed before ``now``, so stepping back one microsecond stays below the write.
        return _at(now if earliest is None else earliest - 1)


def stored_ts_payload(stored_at: datetime | None) -> dict[str, float]:
    """Payload entry of the stamp in the epoch seconds the store filters and orders on; absent until stamped."""
    return {STORED_TS_KEY: stored_at.timestamp()} if stored_at is not None else {}


def stored_at_from_metadata(meta: Mapping[str, object]) -> datetime | None:
    """The stamp of a stored document, or ``None`` for one written before stamps existed."""
    raw = meta.get(STORED_TS_KEY)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(raw, UTC)
    except (OverflowError, OSError, ValueError):
        return None
