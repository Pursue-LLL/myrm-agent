"""SHPOIB HITL attach replay integration tests (no Chrome/LLM).

Guards the server-side path LIVE Chrome E2E depends on when UI multiplex/SSE
is flaky: pending tool_approval_request → collector replay → hitl-probe / attach.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.api.agents.general_agent.active_sessions import attach_to_chat, get_chat_turn_state
from app.remote_access.e2ee.session import E2EE_CONTENT_TYPE, E2EESession
from app.schemas.streaming import SSE_RESPONSE_HEADERS
from app.services.agent.gateway import get_agent_gateway
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


def test_settled_tool_approval_is_no_longer_replayed_to_a_new_subscriber() -> None:
    """The card was answered: a page that attaches before the resumed run registers its own collector must not get it again."""
    collector = StreamContentCollector(chat_id="chat-settled-card")
    collector.feed_event({"type": "clarification_required", "messageId": "msg-c", "data": {}})
    collector.feed_event(_approval_event())

    collector.settle_tool_approvals()

    assert collector.has_pending_tool_approval() is False
    _snapshot, queue = collector.subscribe()
    assert [queue.get_nowait().get("type") for _ in range(queue.qsize())] == ["clarification_required"]
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


def _turn_state(client: TestClient, chat_id: str) -> dict[str, bool]:
    response = client.get(f"/api/v1/agents/chat/{chat_id}/turn-state")
    assert response.status_code == 200
    state: dict[str, bool] = response.json()["data"]
    assert set(state) == {"running", "awaitingApproval"}
    return state


def test_turn_state_reports_the_chat_parked_behind_a_tool_approval(client: TestClient) -> None:
    """A parked turn has released its gateway session: this state is how a reloaded page learns the card can be brought back."""
    chat_id = "chat-parked-behind-approval"
    collector = StreamContentCollector(chat_id=chat_id)
    collector.feed_event(_approval_event())

    assert _turn_state(client, chat_id) == {"running": False, "awaitingApproval": True}


def test_turn_state_reports_a_running_turn_without_an_approval_card(client: TestClient) -> None:
    chat_id = "chat-running-turn"
    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id)
    try:
        assert _turn_state(client, chat_id) == {"running": True, "awaitingApproval": False}
    finally:
        gateway.release_session(chat_id)


def test_turn_state_ignores_the_approval_card_of_another_chat(client: TestClient) -> None:
    StreamContentCollector(chat_id="chat-parked-elsewhere").feed_event(_approval_event())

    assert _turn_state(client, "chat-without-turn") == {"running": False, "awaitingApproval": False}


def test_turn_state_leaves_out_a_chat_without_a_tool_approval_to_hand_back(client: TestClient) -> None:
    """Only a tool-approval card needs the collector: a plain run, a clarification and an approval record are restored elsewhere."""
    parked_elsewhere: dict[str, dict[str, object]] = {
        "chat-plain-run": {"type": "message", "data": "partial"},
        "chat-clarification": {"type": "clarification_required", "messageId": "msg-c", "data": {}},
        "chat-approval-record": {"type": "approval_required", "messageId": "msg-a", "data": {}},
    }
    for chat_id, event in parked_elsewhere.items():
        StreamContentCollector(chat_id=chat_id).feed_event(event)

    for chat_id in parked_elsewhere:
        assert _turn_state(client, chat_id)["awaitingApproval"] is False


def test_turn_state_drops_the_chat_once_the_resumed_run_took_over(client: TestClient) -> None:
    """Approve starts a new collector for the chat, so the page that reloads afterwards is not offered the answered card."""
    chat_id = "chat-approved-and-resumed"
    parked = StreamContentCollector(chat_id=chat_id)
    parked.feed_event(_approval_event())
    assert _turn_state(client, chat_id)["awaitingApproval"] is True

    StreamContentCollector(chat_id=chat_id).feed_event({"type": "message", "data": "resumed"})

    assert _turn_state(client, chat_id)["awaitingApproval"] is False
    parked.cleanup()
    assert chat_id in ACTIVE_COLLECTORS


def test_sse_response_headers_enable_shpoib_cross_origin_reads() -> None:
    assert SSE_RESPONSE_HEADERS.get("Cross-Origin-Resource-Policy") == "cross-origin"


def test_sse_response_headers_keep_a_compressing_proxy_from_buffering_the_stream() -> None:
    """The Next.js server that relays ``/api/v1`` gzips what it may; a quiet attach stream would then deliver nothing."""
    directives = {part.strip() for part in SSE_RESPONSE_HEADERS["Cache-Control"].split(",")}
    assert {"no-cache", "no-transform"} <= directives


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
async def test_turn_state_stays_plain_json_for_a_request_with_an_e2ee_session() -> None:
    """The page reads it with ``apiRequest``, which never decrypts: an encrypted answer would read as no state at all."""
    request = _FakeRequest()
    request.state.e2ee_session = E2EESession(
        session_id="session-turn-state",
        client_public_key=bytes(32),
        secret_key=bytes(32),
        expires_at=time.time() + 60,
    )

    response = await get_chat_turn_state("chat-with-e2ee-session", request)  # type: ignore[arg-type]

    assert response.media_type != E2EE_CONTENT_TYPE
    assert json.loads(bytes(response.body))["data"] == {"running": False, "awaitingApproval": False}


@pytest.mark.asyncio
async def test_turn_state_endpoint_rejects_a_pair_bound_to_another_chat_by_itself() -> None:
    """The auth middleware already refuses a mismatching path; the endpoint must not rely on that alone."""
    request = _FakeRequest()
    request.state.auth_source = "pair_token"
    request.state.pair_bound_chat_id = "chat-bound"

    with pytest.raises(HTTPException) as refused:
        await get_chat_turn_state("chat-other", request)  # type: ignore[arg-type]
    assert refused.value.status_code == 401


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
