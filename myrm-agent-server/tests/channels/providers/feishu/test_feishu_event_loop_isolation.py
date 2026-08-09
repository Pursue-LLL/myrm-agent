"""Test Feishu event loop isolation for concurrent instances.

This test verifies whether the current implementation correctly isolates
event loops when multiple FeishuChannel instances are running concurrently.

If this test PASSES: Current implementation is safe, no fix needed.
If this test FAILS: Race condition exists, need to implement the fix.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest


def _check_sdk_available() -> bool:
    """Check if lark-oapi SDK is installed."""
    try:
        import importlib.util

        return importlib.util.find_spec("lark_oapi") is not None
    except Exception:
        return False


@pytest.mark.skipif(
    not _check_sdk_available(),
    reason="lark-oapi SDK not installed",
)
@pytest.mark.asyncio
async def test_concurrent_feishu_instances_event_isolation():
    """Test that concurrent Feishu WebSocket transports don't interfere with each other."""
    from app.channels.providers.feishu.ws_transport import (
        FeishuWSTransport,
    )

    # Track which transport received which event
    events_received = {"transport_1": [], "transport_2": []}

    async def on_event_1(event_dict):
        events_received["transport_1"].append(event_dict)
        return None

    async def on_event_2(event_dict):
        events_received["transport_2"].append(event_dict)
        return None

    # Create two transport instances
    transport_1 = FeishuWSTransport(
        app_id="test_app_1",
        app_secret="test_secret_1",
        encrypt_key="test_key_1",
        verification_token="test_token_1",
    )

    transport_2 = FeishuWSTransport(
        app_id="test_app_2",
        app_secret="test_secret_2",
        encrypt_key="test_key_2",
        verification_token="test_token_2",
    )

    # Mock the SDK client to simulate event delivery
    with patch("lark_oapi.ws.Client") as mock_client_class:
        mock_client_1 = MagicMock()
        mock_client_2 = MagicMock()

        # Track which client is created for which transport
        clients = []

        def create_client(*args, **kwargs):
            if len(clients) == 0:
                clients.append(("client_1", mock_client_1))
                return mock_client_1
            else:
                clients.append(("client_2", mock_client_2))
                return mock_client_2

        mock_client_class.side_effect = create_client

        # Start both transports concurrently
        start_tasks = [
            transport_1.start(on_event_1),
            transport_2.start(on_event_2),
        ]

        # Wait for both to start
        await asyncio.gather(*start_tasks)

        # Simulate events for each transport
        # If there's a race condition, events might be delivered to the wrong transport

        # Simulate event for transport_1
        event_1 = {"message_id": "msg_1", "content": "Hello from transport 1"}
        await transport_1._on_event(event_1)

        # Simulate event for transport_2
        event_2 = {"message_id": "msg_2", "content": "Hello from transport 2"}
        await transport_2._on_event(event_2)

        # Wait for event processing
        await asyncio.sleep(0.1)

        # Verify events are correctly isolated
        assert len(events_received["transport_1"]) == 1, "Transport 1 should receive exactly 1 event"
        assert len(events_received["transport_2"]) == 1, "Transport 2 should receive exactly 1 event"

        assert events_received["transport_1"][0]["message_id"] == "msg_1", "Transport 1 should receive its own event"
        assert events_received["transport_2"][0]["message_id"] == "msg_2", "Transport 2 should receive its own event"

        # Stop both transports
        await transport_1.stop()
        await transport_2.stop()
