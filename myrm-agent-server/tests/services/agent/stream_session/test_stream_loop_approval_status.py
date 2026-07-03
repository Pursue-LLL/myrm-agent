"""Tests for awaiting_approval / generating status broadcast in stream_loop."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_loop import (
    ApprovalTimeoutHolder,
    iter_agent_stream_chunks,
)
from app.services.agent.streaming_support.multiplexer import WorkspaceMultiplexer


@pytest.fixture(autouse=True)
def _reset_multiplexer():
    WorkspaceMultiplexer._instance = None
    yield
    WorkspaceMultiplexer._instance = None


def _make_session(chat_id: str = "test-chat") -> MagicMock:
    session = MagicMock()
    session.request.chat_id = chat_id
    session.request.action_mode = "general"
    session.request.use_workflow = False
    session.request.blueprint_id = None
    session.request.mention_references = None
    session.request.resume_value = None
    session.request.ephemeral_subagents = None
    session.routing_tier = "complex"
    session.params.message_id = "msg-1"
    session.cancel_token.is_cancelled = False
    session.goal_provider = None
    session.collector = MagicMock()
    return session


def _tool_approval_request_chunk() -> str:
    event = {
        "type": "tool_approval_request",
        "data": {
            "tool_name": "shell",
            "extensions": {"timeout": {"seconds": 120, "behavior": "deny"}},
        },
    }
    return f"data: {json.dumps(event)}\n\n"


def _approval_intercepted_chunk(decision: str = "approve") -> str:
    event = {
        "type": "approval_intercepted",
        "data": {"decision": decision},
    }
    return f"data: {json.dumps(event)}\n\n"


class TestApprovalStatusBroadcast:
    @pytest.mark.asyncio
    async def test_tool_approval_request_publishes_awaiting(self) -> None:
        """When a tool_approval_request SSE event is detected, the multiplexer
        should broadcast awaiting_approval status for the chat."""
        session = _make_session()
        approval = ApprovalTimeoutHolder()

        chunks = [_tool_approval_request_chunk()]

        async def _fake_stream(*_args, **_kwargs):
            for c in chunks:
                yield c

        mux = WorkspaceMultiplexer.get()
        published: list[str] = []
        original = mux.publish_session_status

        def spy(chat_id: str, status: str, agent_type: str = "") -> None:
            published.append(status)
            original(chat_id, status, agent_type)

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch.object(mux, "publish_session_status", side_effect=spy),
        ):
            collected = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                collected.append(chunk)

        assert "awaiting_approval" in published

    @pytest.mark.asyncio
    async def test_approval_intercepted_publishes_generating(self) -> None:
        """When an approval_intercepted event is detected, the multiplexer
        should broadcast generating status to resume the indicator."""
        session = _make_session()
        approval = ApprovalTimeoutHolder()

        chunks = [
            _tool_approval_request_chunk(),
            _approval_intercepted_chunk("approve"),
        ]

        async def _fake_stream(*_args, **_kwargs):
            for c in chunks:
                yield c

        mux = WorkspaceMultiplexer.get()
        published: list[str] = []
        original = mux.publish_session_status

        def spy(chat_id: str, status: str, agent_type: str = "") -> None:
            published.append(status)
            original(chat_id, status, agent_type)

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch.object(mux, "publish_session_status", side_effect=spy),
        ):
            collected = []
            async for chunk in iter_agent_stream_chunks(session, approval):
                collected.append(chunk)

        assert published == ["awaiting_approval", "generating"]

    @pytest.mark.asyncio
    async def test_reject_decision_also_publishes_generating(self) -> None:
        """A reject decision should still restore generating status."""
        session = _make_session()
        approval = ApprovalTimeoutHolder()

        chunks = [
            _tool_approval_request_chunk(),
            _approval_intercepted_chunk("reject"),
        ]

        async def _fake_stream(*_args, **_kwargs):
            for c in chunks:
                yield c

        mux = WorkspaceMultiplexer.get()
        published: list[str] = []
        original = mux.publish_session_status

        def spy(chat_id: str, status: str, agent_type: str = "") -> None:
            published.append(status)
            original(chat_id, status, agent_type)

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch.object(mux, "publish_session_status", side_effect=spy),
        ):
            async for _ in iter_agent_stream_chunks(session, approval):
                pass

        assert published == ["awaiting_approval", "generating"]

    @pytest.mark.asyncio
    async def test_consecutive_approvals_cycle(self) -> None:
        """Multiple sequential approval cycles should produce alternating statuses."""
        session = _make_session()
        approval = ApprovalTimeoutHolder()

        chunks = [
            _tool_approval_request_chunk(),
            _approval_intercepted_chunk("approve"),
            _tool_approval_request_chunk(),
            _approval_intercepted_chunk("approve"),
        ]

        async def _fake_stream(*_args, **_kwargs):
            for c in chunks:
                yield c

        mux = WorkspaceMultiplexer.get()
        published: list[str] = []
        original = mux.publish_session_status

        def spy(chat_id: str, status: str, agent_type: str = "") -> None:
            published.append(status)
            original(chat_id, status, agent_type)

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch.object(mux, "publish_session_status", side_effect=spy),
        ):
            async for _ in iter_agent_stream_chunks(session, approval):
                pass

        assert published == [
            "awaiting_approval", "generating",
            "awaiting_approval", "generating",
        ]

    @pytest.mark.asyncio
    async def test_no_broadcast_without_chat_id(self) -> None:
        """If the session has no chat_id, no status should be broadcast
        for either approval_request or approval_intercepted."""
        session = _make_session(chat_id="")
        session.request.chat_id = ""
        approval = ApprovalTimeoutHolder()

        chunks = [
            _tool_approval_request_chunk(),
            _approval_intercepted_chunk("approve"),
        ]

        async def _fake_stream(*_args, **_kwargs):
            for c in chunks:
                yield c

        mux = WorkspaceMultiplexer.get()
        published: list[str] = []

        def spy(chat_id: str, status: str, agent_type: str = "") -> None:
            published.append(status)

        with (
            patch(
                "app.services.agent.stream_session.stream_loop.ai_agent_service_stream",
                side_effect=_fake_stream,
            ),
            patch.object(mux, "publish_session_status", side_effect=spy),
        ):
            async for _ in iter_agent_stream_chunks(session, approval):
                pass

        assert published == []
