"""E2E test: concurrent requests on the same chatId must yield AgentBusyError (409).

Relies on conftest.py autouse fixtures for DB, auth, and user config setup.
Uses ObservableSet to detect when gateway registers the first session.
"""

import asyncio
import json
import os
import uuid

import httpx
import pytest
from dotenv import load_dotenv

from tests.api.agent.utils import get_model_selection

load_dotenv(override=True)


class ObservableSet(set):
    """A set subclass that fires an asyncio.Event on the first add()."""

    def __init__(self, event: asyncio.Event):
        super().__init__()
        self._event = event

    def add(self, item):
        super().add(item)
        self._event.set()


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_concurrent_requests_return_409(app):
    """Two concurrent requests on the same chatId: second must get AgentBusyError."""
    from app.services.agent.gateway import get_agent_gateway

    gateway = get_agent_gateway()
    session_registered = asyncio.Event()

    original_sessions = gateway._active_sessions
    gateway._active_sessions = ObservableSet(session_registered)

    try:
        chat_id = str(uuid.uuid4())
        payload = {
            "messageId": str(uuid.uuid4()),
            "query": "Write a detailed story about space exploration.",
            "chatId": chat_id,
            "modelSelection": get_model_selection(),
            "actionMode": "agent",
        }

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:

            async def stream_request(req_payload: dict[str, object]) -> list[dict[str, object]]:
                events: list[dict[str, object]] = []
                async with client.stream("POST", "/api/v1/agents/agent-stream", json=req_payload) as resp:
                    if resp.status_code != 200:
                        raw = await resp.aread()
                        return [{"type": "http_error", "status": resp.status_code, "text": raw.decode(errors="replace")}]
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        try:
                            events.append(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            pass
                return events

            task1 = asyncio.create_task(stream_request(payload))

            try:
                await asyncio.wait_for(session_registered.wait(), timeout=60.0)
            except TimeoutError:
                task1_result = None
                if task1.done():
                    task1_result = task1.result()
                else:
                    task1.cancel()
                pytest.fail(f"Task1 did not register session within 60s. Task1 done={task1.done()}, result={task1_result}")

            payload2 = {
                "messageId": str(uuid.uuid4()),
                "query": "Another quick question.",
                "chatId": chat_id,
                "modelSelection": get_model_selection(),
                "actionMode": "agent",
            }
            events2 = await stream_request(payload2)

            assert len(events2) > 0, "Second request should return at least one event"
            error_event = next((e for e in events2 if e.get("type") == "error"), None)
            assert error_event is not None, f"Expected error event, got: {events2}"
            assert error_event.get("error_type") == "AgentBusyError"
            assert error_event.get("status_code") == 409
            assert "Agent is busy" in error_event.get("data", "")

            task1.cancel()
            try:
                await task1
            except asyncio.CancelledError:
                pass
    finally:
        gateway._active_sessions = original_sessions
