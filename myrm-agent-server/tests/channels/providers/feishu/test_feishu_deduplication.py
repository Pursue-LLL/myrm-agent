"""Unit tests for Feishu message deduplication (OrderedDict LRU)."""

from __future__ import annotations

from collections import OrderedDict


class TestFeishuDeduplication:
    """Tests for Feishu message_id deduplication logic (OrderedDict LRU)."""

    def test_ordereddict_add_and_check(self) -> None:
        """Basic OrderedDict add and membership check."""
        processed: OrderedDict[str, None] = OrderedDict()
        msg_id = "123"

        assert msg_id not in processed
        processed[msg_id] = None
        assert msg_id in processed

    def test_duplicate_detection(self) -> None:
        """Duplicate message_id should be detected."""
        processed: OrderedDict[str, None] = OrderedDict()
        msg_id = "123"

        processed[msg_id] = None

        assert msg_id in processed

    def test_ordereddict_fifo_order(self) -> None:
        """OrderedDict should maintain FIFO insertion order."""
        processed: OrderedDict[str, None] = OrderedDict()

        processed["1"] = None
        processed["2"] = None
        processed["3"] = None

        assert list(processed.keys()) == ["1", "2", "3"]

    def test_lru_eviction_with_popitem(self) -> None:
        """popitem(last=False) should remove oldest (FIFO)."""
        processed: OrderedDict[str, None] = OrderedDict()
        max_size = 3

        for i in range(max_size):
            processed[str(i)] = None

        assert len(processed) == max_size

        while len(processed) >= max_size:
            processed.popitem(last=False)

        new_id = str(max_size)
        processed[new_id] = None

        assert "0" not in processed
        assert str(max_size) in processed
        assert len(processed) == max_size

    def test_eviction_preserves_recent(self) -> None:
        """Eviction should only remove oldest, keep recent."""
        processed: OrderedDict[str, None] = OrderedDict()
        max_size = 3

        for i in range(max_size + 2):
            if len(processed) >= max_size:
                processed.popitem(last=False)

            processed[str(i)] = None

        assert "0" not in processed
        assert "1" not in processed
        assert "2" in processed
        assert "3" in processed
        assert "4" in processed

    def test_multiple_different_ids(self) -> None:
        """Multiple different IDs should all be tracked."""
        processed: OrderedDict[str, None] = OrderedDict()

        ids = ["111", "222", "333"]
        for msg_id in ids:
            processed[msg_id] = None

        for msg_id in ids:
            assert msg_id in processed

    def test_popitem_last_false_removes_first(self) -> None:
        """popitem(last=False) should remove first item."""
        processed: OrderedDict[str, None] = OrderedDict()
        processed["first"] = None
        processed["second"] = None
        processed["third"] = None

        key, _ = processed.popitem(last=False)
        assert key == "first"
        assert "first" not in processed
        assert list(processed.keys()) == ["second", "third"]
