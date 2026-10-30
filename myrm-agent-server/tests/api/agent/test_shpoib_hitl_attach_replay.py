"""SHPOIB HITL attach replay integration tests (no Chrome/LLM).

Guards the server-side path LIVE Chrome E2E depends on when UI multiplex/SSE
is flaky: pending tool_approval_request → collector replay → hitl-probe / attach.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
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
def _clear_active_collectors() -> Iterator[None]:
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


def _awaiting_approval_chat_ids(client: TestClient) -> list[str]:
    response = client.get("/api/v1/agents/active-sessions")
    assert response.status_code == 200
    ids = response.json()["data"]["awaitingApprovalChatIds"]
    assert isinstance(ids, list)
    return ids


def test_active_sessions_lists_the_chat_parked_behind_a_tool_approval(client: TestClient) -> None:
    """A parked turn has released its gateway session: this list is how a reloaded page learns the card can be brought back."""
    chat_id = "chat-parked-behind-approval"
    collector = StreamContentCollector(chat_id=chat_id)
    collector.feed_event(_approval_event())

    assert _awaiting_approval_chat_ids(client) == [chat_id]
    assert chat_id not in [s["chatId"] for s in client.get("/api/v1/agents/active-sessions").json()["data"]["activeSessions"]]


def test_active_sessions_leaves_out_chats_without_a_tool_approval_to_hand_back(client: TestClient) -> None:
    """Only a tool-approval card needs the collector: a plain run, a clarification and an approval record are restored elsewhere."""
    parked_elsewhere: dict[str, dict[str, object]] = {
        "chat-plain-run": {"type": "message", "data": "partial"},
        "chat-clarification": {"type": "clarification_required", "messageId": "msg-c", "data": {}},
        "chat-approval-record": {"type": "approval_required", "messageId": "msg-a", "data": {}},
    }
    for chat_id, event in parked_elsewhere.items():
        StreamContentCollector(chat_id=chat_id).feed_event(event)

    assert _awaiting_approval_chat_ids(client) == []


def test_active_sessions_drops_the_chat_once_the_resumed_run_took_over(client: TestClient) -> None:
    """Approve starts a new collector for the chat, so the page that reloads afterwards is not offered the answered card."""
    chat_id = "chat-approved-and-resumed"
    parked = StreamContentCollector(chat_id=chat_id)
    parked.feed_event(_approval_event())
    assert _awaiting_approval_chat_ids(client) == [chat_id]

    StreamContentCollector(chat_id=chat_id).feed_event({"type": "message", "data": "resumed"})

    assert _awaiting_approval_chat_ids(client) == []
    parked.cleanup()
    assert chat_id in ACTIVE_COLLECTORS


def test_sse_response_headers_enable_shpoib_cross_origin_reads() -> None:
    assert SSE_RESPONSE_HEADERS.get("Cross-Origin-Resource-Policy") == "cross-origin"


async def _next_chunk(body: AsyncIterator[str | bytes | memoryview]) -> str:
    chunk = await anext(body)
    return chunk if isinstance(chunk, str) else bytes(chunk).decode()


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
        body = aiter(response.body_iterator)

        # 1. catchup_snapshot is yielded first
        first = await _next_chunk(body)
        assert "catchup_snapshot" in first

        # 2. Real-time event is streamed while collector is active
        collector.feed_event({"type": "message", "data": "live-chunk"})
        second = await _next_chunk(body)
        assert "live-chunk" in second

        # 3. Once the turn finalizes, the stream must terminate promptly
        collector.cleanup()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(_next_chunk(body), timeout=5)
    finally:
        collector.cleanup()
