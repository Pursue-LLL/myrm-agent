"""run_agent_stream hands a reserved turn to the E1 launcher and always releases its reservation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.streaming.stream_buffer import GlobalStreamRegistry

from app.services.agent.stream_session import run_agent_stream

_ORCHESTRATOR = "app.services.agent.stream_session.orchestrator"


@pytest.fixture
def handoff(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Run every pre-reserve step as a no-op so run_agent_stream reaches the launcher."""
    request = MagicMock()
    request.action_mode = "general"
    request.resume_value = None
    request.chat_id = "chat-handoff"
    request.message_id = "msg-handoff"
    request.query = "hello"

    http_request = MagicMock()

    async def _stream():
        yield b""

    http_request.stream = _stream

    for step in ("try_stream_reconnect", "check_stream_risk", "prevalidate_archive_restore_actions"):
        monkeypatch.setattr(f"{_ORCHESTRATOR}.{step}", AsyncMock(return_value=None))
    monkeypatch.setattr(f"{_ORCHESTRATOR}._count_pending_approvals", AsyncMock(return_value=0))
    monkeypatch.setattr(
        "app.services.agent.context_guard_service.ContextGuardService.guard_inbound_prompt",
        AsyncMock(return_value=SimpleNamespace(spilled=False)),
    )

    reservation = MagicMock()
    reservation.try_reserve = MagicMock(return_value=None)
    monkeypatch.setattr(f"{_ORCHESTRATOR}.ChatSessionReservation", lambda: reservation)

    buffer = MagicMock()
    registry = MagicMock()
    registry.get_or_create = AsyncMock(return_value=buffer)
    monkeypatch.setattr(GlobalStreamRegistry, "get", staticmethod(lambda: registry))

    launcher = AsyncMock(return_value=JSONResponse(content={"status": "accepted"}))
    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator_turn_launch.launch_early_buffered_stream",
        launcher,
    )
    return SimpleNamespace(
        request=request,
        http_request=http_request,
        reservation=reservation,
        buffer=buffer,
        registry=registry,
        launcher=launcher,
    )


@pytest.mark.asyncio
async def test_reserved_turn_is_handed_to_the_launcher(handoff: SimpleNamespace) -> None:
    response = await run_agent_stream(handoff.request, handoff.http_request)

    assert response is handoff.launcher.return_value
    handoff.launcher.assert_awaited_once()
    kwargs = handoff.launcher.await_args.kwargs
    assert kwargs["request"] is handoff.request
    assert kwargs["buffer"] is handoff.buffer
    assert kwargs["registry"] is handoff.registry
    assert kwargs["session_reservation"] is handoff.reservation
    assert kwargs["text_content"] == "hello"
    handoff.reservation.release.assert_called_once_with()


@pytest.mark.asyncio
async def test_reservation_is_released_when_the_launcher_fails(handoff: SimpleNamespace) -> None:
    handoff.launcher.side_effect = RuntimeError("launch failed")

    with pytest.raises(RuntimeError, match="launch failed"):
        await run_agent_stream(handoff.request, handoff.http_request)

    handoff.reservation.release.assert_called_once_with()
