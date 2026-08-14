"""E1 early buffered stream response shape tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.agent.stream_session import chat_history_bootstrap
from app.services.agent.stream_session.orchestrator_turn_body import (
    launch_early_buffered_stream,
)


@pytest.mark.asyncio
async def test_launch_early_buffered_stream_returns_sse_for_normal_web() -> None:
    request = MagicMock()
    request.message_id = "msg-1"
    request.multiplexed = False

    buffer = MagicMock()
    buffer.subscribe = MagicMock(return_value=iter(()))

    with patch(
        "app.services.agent.stream_session.orchestrator_turn_body.asyncio.create_task",
    ) as mock_create_task:
        mock_create_task.return_value = MagicMock(add_done_callback=MagicMock())
        response = await launch_early_buffered_stream(
            request=request,
            http_request=MagicMock(),
            text_content="hello",
            stream_started_at_monotonic=0.0,
            registry=MagicMock(),
            buffer=buffer,
            session_reservation=MagicMock(),
            record_terminal_failure=AsyncMock(),
        )

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"


@pytest.mark.asyncio
async def test_launch_early_buffered_stream_returns_json_when_multiplexed() -> None:
    request = MagicMock()
    request.message_id = "msg-mux-1"
    request.multiplexed = True

    buffer = MagicMock()

    with patch(
        "app.services.agent.stream_session.orchestrator_turn_body.asyncio.create_task",
    ) as mock_create_task:
        mock_create_task.return_value = MagicMock(add_done_callback=MagicMock())
        response = await launch_early_buffered_stream(
            request=request,
            http_request=MagicMock(),
            text_content="hello",
            stream_started_at_monotonic=0.0,
            registry=MagicMock(),
            buffer=buffer,
            session_reservation=MagicMock(),
            record_terminal_failure=AsyncMock(),
        )

    assert isinstance(response, JSONResponse)
    assert response.body is not None
    payload = response.body.decode()
    assert '"status":"accepted"' in payload.replace(" ", "")
    assert "msg-mux-1" in payload


@pytest.mark.asyncio
async def test_persist_user_message_is_separate_from_history_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = SimpleNamespace(
        chat_id="chat-1",
        sibling_group_id=None,
        resume_value=None,
        timestamp=None,
        timezone="UTC",
        query="hello",
        message_id="msg-1",
        action_mode="agent",
        agent_id="default",
        ephemeral_subagents=None,
        incognito_mode=False,
        active_moa_preset_id=None,
    )
    persisted = SimpleNamespace(id="msg-1")
    calls: list[str] = []

    async def fake_append(**_kwargs: object) -> object:
        calls.append("persist")
        return persisted

    async def fake_history(*_args: object, **_kwargs: object) -> list[list[str]]:
        calls.append("history")
        return [["user", "hello"]]

    monkeypatch.setattr(
        chat_history_bootstrap.ChatService,
        "ensure_chat_and_append_user_message",
        staticmethod(fake_append),
    )
    monkeypatch.setattr(
        chat_history_bootstrap.ChatService,
        "load_web_chat_history",
        staticmethod(fake_history),
    )

    message_id = await chat_history_bootstrap.persist_user_message(
        request,
        text_content="hello",
    )
    assert message_id == "msg-1"
    assert calls == ["persist"]

    history = await chat_history_bootstrap.load_chat_history(
        request,
        exclude_message_id=message_id,
    )
    assert history == [["user", "hello"]]
    assert calls == ["persist", "history"]


@pytest.mark.asyncio
async def test_background_turn_binds_harness_chat_id_for_snapshot_session() -> None:
    """The background turn must bind harness session_lock chat_id so SnapshotObserver
    persists snapshots under the real chat_id (not the "default" fallback), otherwise
    the revert API querying by chat_id returns empty."""
    from myrm_agent_harness.agent.context_management.infra.session_lock import (
        get_current_chat_id,
    )

    request = MagicMock()
    request.message_id = "msg-bind-1"
    request.multiplexed = False
    request.chat_id = "chat-bind-1"
    buffer = MagicMock()
    buffer.subscribe = MagicMock(return_value=iter(()))
    buffer.end_stream = AsyncMock()

    captured_coros: list[object] = []

    def fake_create_task(coro: object, name: str | None = None) -> MagicMock:
        captured_coros.append(coro)
        task = MagicMock()
        task.add_done_callback = MagicMock()
        return task

    bound_during_turn: list[str | None] = []

    async def fake_execute(*_args: object, **_kwargs: object) -> None:
        bound_during_turn.append(get_current_chat_id())
        return None

    with (
        patch(
            "app.services.agent.stream_session.orchestrator_turn_body.asyncio.create_task",
            side_effect=fake_create_task,
        ),
        patch(
            "app.services.agent.stream_session.orchestrator_turn_body.execute_agent_turn_after_reserve",
            new=fake_execute,
        ),
        patch(
            "app.services.agent.gateway.get_agent_gateway",
        ),
    ):
        response = await launch_early_buffered_stream(
            request=request,
            http_request=MagicMock(),
            text_content="hello",
            stream_started_at_monotonic=0.0,
            registry=MagicMock(),
            buffer=buffer,
            session_reservation=MagicMock(),
            record_terminal_failure=AsyncMock(),
        )
        assert len(captured_coros) == 1
        assert bound_during_turn == [], "chat_id must be bound before turn execution"
        await captured_coros[0]  # type: ignore[misc]

    assert response.media_type == "text/event-stream"
    assert bound_during_turn == ["chat-bind-1"], (
        f"harness session_lock chat_id must be bound to request chat_id, got {bound_during_turn}"
    )
