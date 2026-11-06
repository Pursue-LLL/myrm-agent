"""A first-turn folder the path policy refuses ends the turn with an error event before any user row is written."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry

from app.services.agent.stream_session import chat_history_bootstrap, orchestrator_turn_body
from app.services.agent.stream_session.turn_workspace_bind import TurnWorkspaceRefused
from app.services.workspace.workspace_path_policy import WorkspacePathIssue


@pytest.mark.asyncio
async def test_a_refused_folder_ends_the_turn_before_the_user_row(monkeypatch: pytest.MonkeyPatch) -> None:
    persist = AsyncMock()
    monkeypatch.setattr(chat_history_bootstrap, "persist_user_message", persist)
    monkeypatch.setattr(
        orchestrator_turn_body,
        "bind_turn_workspace",
        AsyncMock(side_effect=TurnWorkspaceRefused(WorkspacePathIssue.NOT_A_DIRECTORY, "Folder is gone")),
    )
    buffer = SimpleNamespace(append=AsyncMock(), end_stream=AsyncMock())
    record_failure = AsyncMock()

    await orchestrator_turn_body.execute_agent_turn_after_reserve(
        request=SimpleNamespace(message_id="msg-refused", chat_id="chat-1"),
        http_request=SimpleNamespace(),
        text_content="hello",
        stream_started_at_monotonic=0.0,
        registry=SimpleNamespace(),
        buffer=buffer,
        record_terminal_failure=record_failure,
    )

    persist.assert_not_awaited()
    record_failure.assert_awaited_once_with("server_error")
    buffer.end_stream.assert_awaited_once()
    (chunk,) = buffer.append.await_args.args
    assert "Folder is gone" in chunk
    assert "msg-refused" in chunk
    assert CancellationRegistry.cancel("msg-refused") is False
