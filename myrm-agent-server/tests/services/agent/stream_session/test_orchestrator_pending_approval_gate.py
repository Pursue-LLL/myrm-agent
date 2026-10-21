from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import StreamingResponse

from app.services.agent.gateway import AgentBusyError
from app.services.agent.stream_session import run_agent_stream


@pytest.fixture
def mock_request():
    req = MagicMock()
    req.action_mode = "general"
    req.resume_value = None
    req.chat_id = "test_chat"
    req.sibling_group_id = None
    req.timestamp = None
    req.timezone = "UTC"
    req.engine_params = None
    req.steering_id = None
    req.mention_references = None
    req.ephemeral_subagents = None
    req.blueprint_id = None
    req.message_id = "test_msg"
    req.agent_id = "default"
    req.source = "web"
    req.session_id = "test"
    req.subagent_ids = None
    req.context_warnings = []
    req.extra_context = {}
    req.query = "hello"
    return req


@pytest.fixture
def mock_http_request():
    http_req = MagicMock()

    async def _stream():
        yield b""

    http_req.stream = _stream
    return http_req


def _patch_gateway_prereqs(monkeypatch) -> None:
    """Patch the synchronous pre-reserve validations to a clean pass."""
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.try_stream_reconnect",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.check_stream_risk",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.prevalidate_archive_restore_actions",
        AsyncMock(return_value=None),
    )


@pytest.mark.asyncio
async def test_gate_rejects_new_run_when_approvals_pending(mock_request, mock_http_request, monkeypatch):
    """A new non-resume run is rejected with AgentBusy SSE while HITL approvals are pending.

    The pending-approval gate must fire before the session reservation is
    attempted, so no reservation is created for the rejected run.
    """
    _patch_gateway_prereqs(monkeypatch)
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator._count_pending_approvals",
        AsyncMock(return_value=2),
    )
    try_reserve_called = MagicMock(side_effect=AssertionError("try_reserve must not be called"))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(try_reserve=try_reserve_called),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    assert isinstance(response, StreamingResponse)
    body = "".join([chunk async for chunk in response.body_iterator])
    assert "AgentBusyError" in body


@pytest.mark.asyncio
async def test_gate_allows_new_run_when_no_pending_approvals(mock_request, mock_http_request, monkeypatch):
    """With zero pending approvals the gate passes through to session reservation.

    try_reserve returning AgentBusyError stands in for a later concurrency
    rejection so the test does not reach the heavy registry/turn-body imports.
    """
    _patch_gateway_prereqs(monkeypatch)
    pending_spy = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator._count_pending_approvals",
        pending_spy,
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(
            try_reserve=MagicMock(return_value=AgentBusyError("Session busy")),
            release=MagicMock(),
        ),
    )

    response = await run_agent_stream(mock_request, mock_http_request)

    pending_spy.assert_awaited_once()
    assert pending_spy.await_args.args == ("test_chat",)
    assert isinstance(response, StreamingResponse)


@pytest.mark.asyncio
async def test_gate_skips_pending_check_for_resume(mock_request, mock_http_request, monkeypatch):
    """Resume requests bypass the pending-approval gate so approvals can be handled."""
    _patch_gateway_prereqs(monkeypatch)
    mock_request.resume_value = {"action": "completed"}
    pending_spy = AsyncMock(return_value=99)
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator._count_pending_approvals",
        pending_spy,
    )

    await run_agent_stream(
        mock_request,
        mock_http_request,
    )

    pending_spy.assert_not_called()


@pytest.mark.asyncio
async def test_gate_allows_run_when_approval_store_unavailable(monkeypatch):
    """_count_pending_approvals fails open: an approval store error yields 0."""
    monkeypatch.setattr(
        "app.services.approvals.registry.ApprovalRegistry.count_pending_for_chat",
        AsyncMock(side_effect=RuntimeError("db down")),
    )

    from app.services.agent.stream_session.orchestrator import _count_pending_approvals

    assert await _count_pending_approvals("test_chat") == 0


@pytest.mark.asyncio
async def test_gate_skips_query_without_chat_id(mock_request, mock_http_request, monkeypatch):
    """New runs without a chat_id never hit the approval store."""
    _patch_gateway_prereqs(monkeypatch)
    mock_request.chat_id = None
    pending_spy = AsyncMock(return_value=5)
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator._count_pending_approvals",
        pending_spy,
    )
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator.ChatSessionReservation",
        lambda: MagicMock(
            try_reserve=MagicMock(return_value=AgentBusyError("Session busy")),
            release=MagicMock(),
        ),
    )

    await run_agent_stream(mock_request, mock_http_request)

    pending_spy.assert_not_called()
