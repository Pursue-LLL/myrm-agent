"""The store stamp: a clock that never repeats, a registry of writes in flight, and the payload form of the stamp.

The horizon (`settled_through`) is what lets a consolidation cursor move forward without passing a memory that
is stamped but not yet visible, so it is checked against writes that overlap, fail and are cancelled.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.memory._internal.store_stamp import (
    STORED_TS_KEY,
    persisting,
    settled_through,
    stored_at_from_metadata,
    stored_ts_payload,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory


def _memories(count: int) -> list[SemanticMemory]:
    return [SemanticMemory(content=f"fact {i}") for i in range(count)]


def _stamps(memories: list[SemanticMemory]) -> list[datetime]:
    stamps = [m.stored_at for m in memories]
    assert None not in stamps
    return [s for s in stamps if s is not None]


class TestPersisting:
    def test_each_memory_gets_its_own_later_stamp_replacing_the_one_it_carried(self) -> None:
        memories = _memories(5)
        memories[0].stored_at = datetime(2001, 1, 1, tzinfo=UTC)

        with persisting(memories):
            pass

        stamps = _stamps(memories)
        assert stamps == sorted(set(stamps))
        assert stamps[0] > datetime.now(UTC) - timedelta(minutes=5)

    def test_stamps_keep_rising_while_the_wall_clock_stands_still_or_steps_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        frozen = time.time_ns()
        batches = [_memories(3), _memories(3)]
        with persisting(batches[0]):
            pass
        monkeypatch.setattr(time, "time_ns", lambda: frozen - 10_000_000_000)
        with persisting(batches[1]):
            pass
        monkeypatch.setattr(time, "time_ns", lambda: frozen)
        horizon = settled_through()

        stamps = _stamps([*batches[0], *batches[1]])
        assert stamps == sorted(set(stamps))
        assert horizon > stamps[-1]

    def test_an_empty_batch_just_runs_the_block(self) -> None:
        ran: list[bool] = []

        with persisting([]):
            ran.append(True)

        assert ran == [True]


class TestSettledThrough:
    def test_it_is_later_than_every_stamp_given_before_it_and_earlier_than_every_one_after(self) -> None:
        before, after = _memories(2), _memories(2)
        with persisting(before):
            pass

        horizon = settled_through()
        with persisting(after):
            pass

        assert max(_stamps(before)) < horizon < min(_stamps(after))

    def test_it_stays_below_a_write_that_has_not_finished(self) -> None:
        writing = _memories(3)

        with persisting(writing):
            during = settled_through()
            first_stamp = min(_stamps(writing))
        after = settled_through()

        assert during == first_stamp - timedelta(microseconds=1)
        assert after > max(_stamps(writing))

    def test_it_stays_below_the_earliest_of_several_overlapping_writes(self) -> None:
        early, late = _memories(1), _memories(1)

        with persisting(early):
            with persisting(late):
                both = settled_through()
            only_early = settled_through()
        none = settled_through()

        assert both == only_early == _stamps(early)[0] - timedelta(microseconds=1)
        assert none > _stamps(late)[0]

    def test_it_moves_up_to_the_next_write_when_the_earliest_one_finishes(self) -> None:
        early, late = _memories(1), _memories(1)

        with ExitStack() as running:
            with persisting(early):
                running.enter_context(persisting(late))
            # The early write has finished; the late one is still registered.
            horizon = settled_through()

        assert _stamps(early)[0] < horizon == _stamps(late)[0] - timedelta(microseconds=1)

    def test_a_write_that_raises_does_not_hold_it(self) -> None:
        failing = _memories(2)

        with pytest.raises(RuntimeError, match="write failed"), persisting(failing):
            raise RuntimeError("write failed")

        assert settled_through() > max(_stamps(failing))

    @pytest.mark.asyncio
    async def test_a_cancelled_write_does_not_hold_it(self) -> None:
        cancelled = _memories(2)
        started = asyncio.Event()

        async def write() -> None:
            with persisting(cancelled):
                started.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(write())
        await started.wait()
        assert settled_through() < min(_stamps(cancelled))

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert settled_through() > max(_stamps(cancelled))


class TestPayloadForm:
    def test_a_microsecond_stamp_survives_the_payload_exactly(self) -> None:
        start = settled_through()
        # Neighbouring microseconds at today's epoch stay distinct doubles, so a cut at one of them is exact.
        stamps = [start + timedelta(microseconds=i) for i in range(2_000)]

        restored = [stored_at_from_metadata(stored_ts_payload(s)) for s in stamps]

        assert restored == stamps
        assert len({stored_ts_payload(s)[STORED_TS_KEY] for s in stamps}) == len(stamps)

    def test_an_unstamped_memory_has_no_payload_entry(self) -> None:
        assert stored_ts_payload(None) == {}

    @pytest.mark.parametrize(
        "meta",
        [
            {},
            {STORED_TS_KEY: None},
            {STORED_TS_KEY: "1700000000.5"},
            {STORED_TS_KEY: True},
            {STORED_TS_KEY: float("nan")},
            {STORED_TS_KEY: float("inf")},
            {STORED_TS_KEY: 1e30},
        ],
    )
    def test_a_document_without_a_usable_stamp_reads_as_unstamped(self, meta: dict[str, object]) -> None:
        assert stored_at_from_metadata(meta) is None

    def test_an_integer_stamp_is_read(self) -> None:
        assert stored_at_from_metadata({STORED_TS_KEY: 1_700_000_000}) == datetime.fromtimestamp(1_700_000_000, UTC)
