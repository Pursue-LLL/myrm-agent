"""E1 early buffered turn: response shape, user-message bootstrap and Stop reachability during setup."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse, StreamingResponse
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry

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


def _persist_request() -> SimpleNamespace:
    return SimpleNamespace(
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


@pytest.mark.asyncio
async def test_persist_user_message_defers_a_new_chat_until_the_first_assistant_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appended: list[object] = []

    async def fake_missing_chat(_chat_id: str) -> None:
        return None

    async def fake_append(**kwargs: object) -> object:
        appended.append(kwargs)
        return SimpleNamespace(id="never-persisted")

    monkeypatch.setattr(chat_history_bootstrap.ChatService, "get_chat_metadata", staticmethod(fake_missing_chat))
    monkeypatch.setattr(
        chat_history_bootstrap.ChatService,
        "ensure_chat_and_append_user_message",
        staticmethod(fake_append),
    )

    message_id = await chat_history_bootstrap.persist_user_message(_persist_request(), text_content="hello")

    assert appended == []
    assert isinstance(message_id, chat_history_bootstrap.BootstrappedMessageId)
    assert message_id == "msg-1"
    draft = message_id.pending_draft
    assert draft is not None
    assert (draft.chat_id, draft.message_id, draft.user_content) == ("chat-1", "msg-1", "hello")


@pytest.mark.asyncio
async def test_persist_user_message_is_separate_from_history_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _persist_request()
    persisted = SimpleNamespace(id="msg-1")
    calls: list[str] = []

    async def fake_existing_chat(_chat_id: str) -> object:
        return SimpleNamespace(id="chat-1")

    async def fake_append(**_kwargs: object) -> object:
        calls.append("persist")
        return persisted

    async def fake_history(*_args: object, **_kwargs: object) -> list[list[str]]:
        calls.append("history")
        return [["user", "hello"]]

    monkeypatch.setattr(chat_history_bootstrap.ChatService, "get_chat_metadata", staticmethod(fake_existing_chat))
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


async def _start_turn_blocked_in_setup(
    monkeypatch: pytest.MonkeyPatch,
    message_id: str,
) -> tuple[MagicMock, asyncio.Event, asyncio.Task[None]]:
    """Launch a real background turn and hold it at its first setup await (persisting the user message)."""
    request = MagicMock()
    request.message_id = message_id
    request.multiplexed = True
    request.chat_id = None
    request.agent_id = None
    buffer = MagicMock()
    buffer.append = AsyncMock()
    buffer.end_stream = AsyncMock()

    setup_entered = asyncio.Event()
    finish_setup = asyncio.Event()

    async def persist_blocked_until_released(*_args: object, **_kwargs: object) -> None:
        setup_entered.set()
        await finish_setup.wait()
        raise RuntimeError("setup failed")

    monkeypatch.setattr(chat_history_bootstrap, "persist_user_message", persist_blocked_until_released)
    monkeypatch.setattr(chat_history_bootstrap, "load_chat_history", AsyncMock())

    await launch_early_buffered_stream(
        request=request,
        http_request=MagicMock(),
        text_content="hello",
        stream_started_at_monotonic=0.0,
        registry=MagicMock(),
        buffer=buffer,
        session_reservation=MagicMock(),
        record_terminal_failure=AsyncMock(),
    )
    await asyncio.wait_for(setup_entered.wait(), timeout=5)
    turn = next(task for task in asyncio.all_tasks() if task.get_name() == f"agent_turn_{message_id}")
    return buffer, finish_setup, turn


@pytest.mark.asyncio
async def test_stop_during_turn_setup_reaches_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setup awaits the database before the agent session exists; a Stop landing then must still find the turn."""
    _, finish_setup, turn = await _start_turn_blocked_in_setup(monkeypatch, "msg-stop-in-setup")
    try:
        assert CancellationRegistry.cancel("msg-stop-in-setup") is True
    finally:
        finish_setup.set()
        await asyncio.wait_for(turn, timeout=5)


@pytest.mark.asyncio
async def test_failed_turn_setup_releases_its_cancel_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A turn that ends in setup never reaches stream finalize, so the failure path must unregister the token."""
    baseline = CancellationRegistry.get_active_count()
    buffer, finish_setup, turn = await _start_turn_blocked_in_setup(monkeypatch, "msg-setup-fails")
    try:
        assert CancellationRegistry.get_active_count() == baseline + 1
    finally:
        finish_setup.set()
        await asyncio.wait_for(turn, timeout=5)

    assert CancellationRegistry.get_active_count() == baseline
    buffer.end_stream.assert_awaited_once()
