import asyncio

import pytest
from myrm_agent_harness.runtime.events.system_events import LocatorSelfHealedEvent

from app.lifecycle.harness_bridge import _handle_locator_healed_event
from app.services.event.app_event_bus import get_event_bus as get_server_bus


@pytest.mark.asyncio
async def test_locator_healed_event_bridged_to_sse_direct():
    """
    Test that the event handler correctly publishes the LocatorHealed event to the server bus,
    which is then pushed to the frontend via SSE.
    """
    bus = get_server_bus()
    queue = bus.subscribe()

    event = LocatorSelfHealedEvent(
        ref="f0_e1",
        old_name="Submit",
        new_name="Confirm",
        url="https://example.com",
        role="button",
        distance=15.5,
    )

    await _handle_locator_healed_event(event)

    received_event = await asyncio.wait_for(queue.get(), timeout=1.0)

    assert received_event.event_type == "locator_healed"
    assert received_event.data["ref"] == "f0_e1"
    assert received_event.data["old_name"] == "Submit"
    assert received_event.data["new_name"] == "Confirm"
    assert received_event.data["url"] == "https://example.com"
    assert received_event.data["role"] == "button"
    assert received_event.data["distance"] == 15.5

    bus.unsubscribe(queue)
