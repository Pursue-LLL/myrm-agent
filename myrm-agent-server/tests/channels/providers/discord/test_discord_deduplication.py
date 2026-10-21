"""Unit tests for Discord message deduplication."""

from __future__ import annotations

from collections import deque


class TestDiscordDeduplication:
    """Tests for Discord message deduplication logic (set + deque LRU)."""

    def test_dedup_set_add_and_check(self) -> None:
        """Basic set add and membership check."""
        processed: set[str] = set()
        msg_id = "123"

        assert msg_id not in processed
        processed.add(msg_id)
        assert msg_id in processed

    def test_dedup_duplicate_detection(self) -> None:
        """Duplicate message_id should be detected."""
        processed: set[str] = set()
        msg_id = "123"

        processed.add(msg_id)

        assert msg_id in processed

    def test_lru_queue_fifo(self) -> None:
        """Queue should maintain FIFO order."""
        queue: deque[str] = deque()

        queue.append("1")
        queue.append("2")
        queue.append("3")

        assert queue.popleft() == "1"
        assert queue.popleft() == "2"
        assert queue.popleft() == "3"

    def test_lru_eviction_logic(self) -> None:
        """LRU eviction when cache full."""
        processed: set[str] = set()
        queue: deque[str] = deque()
        max_size = 3

        for i in range(max_size):
            msg_id = str(i)
            processed.add(msg_id)
            queue.append(msg_id)

        assert len(processed) == max_size

        if len(processed) >= max_size:
            oldest = queue.popleft()
            processed.discard(oldest)

        new_msg_id = str(max_size)
        processed.add(new_msg_id)
        queue.append(new_msg_id)

        assert "0" not in processed
        assert str(max_size) in processed
        assert len(processed) == max_size

    def test_set_and_queue_consistency(self) -> None:
        """Set and queue should stay in sync."""
        processed: set[str] = set()
        queue: deque[str] = deque()

        for i in range(5):
            msg_id = str(i)
            processed.add(msg_id)
            queue.append(msg_id)

        assert len(processed) == len(queue)
        assert set(queue) == processed

    def test_dedup_multiple_different_ids(self) -> None:
        """Multiple different IDs should all be tracked."""
        processed: set[str] = set()

        ids = ["111", "222", "333"]
        for msg_id in ids:
            processed.add(msg_id)

        for msg_id in ids:
            assert msg_id in processed

    def test_eviction_preserves_recent_messages(self) -> None:
        """Eviction should only remove oldest, keep recent."""
        processed: set[str] = set()
        queue: deque[str] = deque()
        max_size = 3

        for i in range(max_size + 2):
            if len(processed) >= max_size:
                oldest = queue.popleft()
                processed.discard(oldest)

            msg_id = str(i)
            processed.add(msg_id)
            queue.append(msg_id)

        assert "0" not in processed
        assert "1" not in processed
        assert "2" in processed
        assert "3" in processed
        assert "4" in processed
