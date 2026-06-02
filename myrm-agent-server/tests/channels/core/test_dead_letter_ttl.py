import time
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.infra.delivery.dead_letter import DeadLetterQueue
from myrm_agent_harness.infra.delivery.storage import QueuedDelivery, move_to_failed


@pytest.fixture
def enqueue_mock():
    return AsyncMock()


@pytest.mark.asyncio
async def test_dlq_ttl_cleanup(tmp_path, enqueue_mock):
    dlq_dir = tmp_path / "dlq"
    dlq_dir.mkdir()

    dlq = DeadLetterQueue(
        enqueue_fn=enqueue_mock,
        base_dir=dlq_dir,
        ttl_days=1,  # 1 day TTL
        retry_intervals_ms=[0],  # immediate retry
    )

    # Create a message that is 2 days old (should be cleaned up)
    old_delivery = QueuedDelivery(
        id="old_msg",
        channel="dummy",
        recipient="user1",
        content={"content": "old"},
        enqueued_at=time.time() - (2 * 24 * 3600),
        priority=2,
        retry_count=0,
        failed_at=time.time() - (2 * 24 * 3600),
    )
    await move_to_failed(old_delivery, base_dir=dlq_dir)

    # Create a message that is fresh (should be kept and retried)
    fresh_delivery = QueuedDelivery(
        id="fresh_msg",
        channel="dummy",
        recipient="user1",
        content={"content": "fresh"},
        enqueued_at=time.time() - 100,  # 100 seconds ago
        priority=2,
        retry_count=0,
        failed_at=time.time() - 100,
    )
    await move_to_failed(fresh_delivery, base_dir=dlq_dir)

    # Verify both are in DLQ
    assert await dlq.get_failed_count() == 2

    # Process failed messages
    await dlq._process_failed_messages()

    # Verify old message is deleted, fresh message is retried (or kept)
    remaining = await dlq.get_failed_deliveries()
    # The fresh message should have been retried and deleted from DLQ
    # The old message should have been deleted due to TTL
    assert len(remaining) == 0

    # Verify enqueue_mock was called ONLY for the fresh message
    enqueue_mock.assert_called_once()
    call_args = enqueue_mock.call_args[0]
    assert call_args[0] == "dummy"
    assert call_args[2]["content"] == "fresh"
