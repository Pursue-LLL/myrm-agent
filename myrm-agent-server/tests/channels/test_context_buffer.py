"""Unit tests for GroupContextBuffer."""

from __future__ import annotations

import time

from app.channels.routing.context_buffer import GroupContextBuffer
from app.channels.types import ContextEntry


def _entry(sender: str = "user1", content: str = "hello") -> ContextEntry:
    return ContextEntry(sender_id=sender, content=content, timestamp=time.monotonic())


class TestAppendAndDrain:
    def test_drain_returns_appended_entries(self) -> None:
        buf = GroupContextBuffer()
        e1 = _entry("a", "msg1")
        e2 = _entry("b", "msg2")
        buf.append("group1", e1)
        buf.append("group1", e2)

        result = buf.drain("group1")
        assert result == (e1, e2)

    def test_drain_clears_buffer(self) -> None:
        buf = GroupContextBuffer()
        buf.append("g", _entry())
        buf.drain("g")
        assert buf.drain("g") == ()

    def test_drain_empty_returns_empty_tuple(self) -> None:
        buf = GroupContextBuffer()
        assert buf.drain("nonexistent") == ()


class TestMaxEntries:
    def test_oldest_evicted_when_full(self) -> None:
        buf = GroupContextBuffer(max_per_group=3)
        entries = [_entry("u", f"msg{i}") for i in range(5)]
        for e in entries:
            buf.append("g", e)

        result = buf.drain("g")
        assert len(result) == 3
        assert result == (entries[2], entries[3], entries[4])


class TestTimeExpiry:
    def test_expired_entries_filtered_on_drain(self) -> None:
        buf = GroupContextBuffer(max_age_seconds=0.05)
        old = ContextEntry(sender_id="u", content="old", timestamp=time.monotonic() - 1.0)
        fresh = _entry("u", "fresh")
        buf.append("g", old)
        buf.append("g", fresh)

        result = buf.drain("g")
        assert len(result) == 1
        assert result[0].content == "fresh"


class TestGroupIsolation:
    def test_different_groups_independent(self) -> None:
        buf = GroupContextBuffer()
        e1 = _entry("u", "group1_msg")
        e2 = _entry("u", "group2_msg")
        buf.append("g1", e1)
        buf.append("g2", e2)

        assert buf.drain("g1") == (e1,)
        assert buf.drain("g2") == (e2,)

    def test_clear_only_affects_target(self) -> None:
        buf = GroupContextBuffer()
        buf.append("g1", _entry())
        buf.append("g2", _entry())
        buf.clear("g1")

        assert buf.drain("g1") == ()
        assert len(buf.drain("g2")) == 1


class TestClearAll:
    def test_clear_all_empties_everything(self) -> None:
        buf = GroupContextBuffer()
        buf.append("g1", _entry())
        buf.append("g2", _entry())
        buf.clear_all()

        assert buf.drain("g1") == ()
        assert buf.drain("g2") == ()
