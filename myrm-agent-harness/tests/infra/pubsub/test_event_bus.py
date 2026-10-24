"""PubSubBus replay contract.

[INPUT]
- myrm_agent_harness.infra.pubsub.event_bus::PubSubBus

[OUTPUT]
- Regression coverage for replayable notifications vs non-replayable telemetry

[POS]
Framework-level event bus tests. Locks the rule that a superseded snapshot must not be
backfilled into every new SSE subscriber while live delivery and dedup stay intact.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.infra.pubsub.event_bus import PubSubBus


class _Event:
    def __init__(self, event_type: str, data: dict[str, object]) -> None:
        self.event_type = event_type
        self.data = data


@pytest.mark.asyncio
async def test_replay_default_backfills_new_subscribers() -> None:
    bus: PubSubBus[_Event] = PubSubBus()
    bus.publish(_Event("notice", {"n": 1}))

    queue = bus.subscribe()

    assert queue.get_nowait().data == {"n": 1}


@pytest.mark.asyncio
async def test_replay_false_keeps_live_delivery_but_skips_backlog() -> None:
    bus: PubSubBus[_Event] = PubSubBus()
    live = bus.subscribe()

    bus.publish(_Event("memory_history_updated", {"history": [1, 2, 3]}), replay=False)

    assert live.get_nowait().data == {"history": [1, 2, 3]}
    assert bus.subscribe().empty()


@pytest.mark.asyncio
async def test_replay_false_still_deduplicates_consecutive_events() -> None:
    bus: PubSubBus[_Event] = PubSubBus()
    live = bus.subscribe()
    event = _Event("memory_history_updated", {"history": [1]})

    bus.publish(event, replay=False)
    bus.publish(event, replay=False)

    assert live.qsize() == 1


@pytest.mark.asyncio
async def test_telemetry_does_not_evict_replayable_backlog() -> None:
    bus: PubSubBus[_Event] = PubSubBus(max_backlog=2)
    bus.publish(_Event("notice", {"n": 1}))

    for _ in range(10):
        bus.publish(_Event("memory_history_updated", {"history": [0] * 512}), replay=False)

    queue = bus.subscribe()
    assert queue.get_nowait().data == {"n": 1}
    assert queue.empty()


@pytest.mark.asyncio
async def test_subscriber_receives_live_events_after_backfill() -> None:
    bus: PubSubBus[_Event] = PubSubBus()
    bus.publish(_Event("notice", {"n": 1}))

    queue = bus.subscribe()
    bus.publish(_Event("notice", {"n": 2}))

    assert [queue.get_nowait().data, queue.get_nowait().data] == [{"n": 1}, {"n": 2}]
    assert queue.empty()
