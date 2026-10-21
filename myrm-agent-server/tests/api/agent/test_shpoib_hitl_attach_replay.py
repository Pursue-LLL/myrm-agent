"""SHPOIB HITL attach replay integration tests (no Chrome/LLM).

Guards the server-side path LIVE Chrome E2E depends on when UI multiplex/SSE
is flaky: pending tool_approval_request → collector replay → hitl-probe / attach.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.api.agents.general_agent.active_sessions import attach_to_chat
from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.streaming_support.stream_collector import ACTIVE_COLLECTORS, StreamContentCollector
from tests.support.minimal_app import build_minimal_app


def _approval_event() -> dict[str, object]:
    return {
        "type": "tool_approval_request",
        "messageId": "msg-shpoib-1",
        "data": {
            "actionRequests": [
                {
                    "action": "bash_code_execute_tool",
                    "args": {"command": "curl -sS http://127.0.0.1:9/ALLOWLIST_LIVE_PROBE"},
                    "description": "Run curl probe",
                }
            ],
            "reviewConfigs": [{}],
        },
    }


@pytest.fixture(autouse=True)
def _clear_active_collectors() -> None:
    ACTIVE_COLLECTORS.clear()
    yield
    ACTIVE_COLLECTORS.clear()


def test_attach_subscribe_replays_pending_tool_approval_request() -> None:
    """Unit-level guard for attach SSE replay without opening the infinite stream."""
    chat_id = "chat-shpoib-attach-replay"
    collector = StreamContentCollector(chat_id=chat_id)
    collector.feed_event(_approval_event())
    assert collector.has_pending_hitl_replay() is True

    _snapshot, queue = collector.subscribe()
    replay = queue.get_nowait()
    assert replay.get("type") == "tool_approval_request"
    assert replay.get("messageId") == "msg-shpoib-1"
    collector.cleanup()


def test_attach_multiplexed_returns_catchup_snapshot(client: TestClient) -> None:
    chat_id = "chat-shpoib-multiplexed"
    collector = StreamContentCollector(chat_id=chat_id)
    collector.feed_event({"type": "message", "data": "partial"})
    collector.feed_event(_approval_event())

    response = client.get(f"/api/v1/agents/chat/{chat_id}/attach?multiplexed=true")
    assert response.status_code == 200
    body = response.json()
    snapshot = body.get("data", {}).get("catchup_snapshot")
    assert isinstance(snapshot, dict)
    assert snapshot.get("content") == "partial"
    assert collector.has_pending_hitl_replay() is True
    collector.cleanup()


def test_attach_returns_404_when_collector_missing(client: TestClient) -> None:
    response = client.get("/api/v1/agents/chat/chat-missing-collector/attach")
    assert response.status_code == 404


def test_hitl_probe_exposes_pending_interrupt_events() -> None:
    chat_id = "chat-hitl-probe-pending"
    collector = StreamContentCollector(chat_id=chat_id)
    collector.feed_event(_approval_event())

    app = build_minimal_app(preset="security")
    with patch("app.api.security.test_fixtures.is_local_mode", return_value=True):
        with TestClient(app) as client:
            response = client.get(
                f"/api/v1/security/allowlist/test/hitl-probe?chat_id={chat_id}",
            )
    assert response.status_code == 200
    body = response.json()
    assert body.get("collector_active") is True
    assert body.get("pending_hitl_replay") is True
    pending = body.get("pending_interrupt_events")
    assert isinstance(pending, list) and len(pending) >= 1
    assert pending[0].get("type") == "tool_approval_request"
    collector.cleanup()


def test_sse_response_headers_enable_shpoib_cross_origin_reads() -> None:
    assert SSE_RESPONSE_HEADERS.get("Cross-Origin-Resource-Policy") == "cross-origin"


class _FakeRequest:
    """Minimal Request stand-in: never disconnected, no E2EE session bound."""

    def __init__(self) -> None:
        self.state: Any = type("State", (), {})()
        self.state.e2ee_session = None
        self.state.auth_source = None

    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_attach_stream_terminates_after_collector_cleanup() -> None:
    """After a turn finalizes (collector removed), the attach SSE stream must end.

    Regression guard for the frontend loading-hang: if the attach stream stays open
    after `collector.cleanup()`, `consumeStream` never sees EOF and the chat store's
    `loading` flag is never reset.
    """
    chat_id = "chat-attach-terminates-on-cleanup"
    collector = StreamContentCollector(chat_id=chat_id)
    try:
        collector.feed_event({"type": "message", "data": "partial"})

        response = await attach_to_chat(chat_id, _FakeRequest())  # type: ignore[arg-type]
        assert isinstance(response, StreamingResponse)
        body = response.body_iterator

        # 1. catchup_snapshot is yielded first
        first = await anext(body)
        assert "catchup_snapshot" in first

        # 2. Real-time event is streamed while collector is active
        collector.feed_event({"type": "message", "data": "live-chunk"})
        second = await anext(body)
        assert "live-chunk" in second

        # 3. Once the turn finalizes, the stream must terminate promptly
        collector.cleanup()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(body), timeout=5)
    finally:
        collector.cleanup()
