"""A web turn stores what the person pasted, parked in the chat workspace, not the reference the run reads instead."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent.stream_session import chat_history_bootstrap, run_agent_stream
from app.services.agent.stream_session.orchestrator_turn_launch import launch_early_buffered_stream
from app.services.chat.chat_service import ChatService
from app.services.chat.context_bomb_guard import KEPT_DIR_NAME

_ORCHESTRATOR = "app.services.agent.stream_session.orchestrator"
_PASTE = "meeting-line: the decision was to keep watching and review next week\n" * 400


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture
def http_request() -> MagicMock:
    async def _stream() -> AsyncIterator[bytes]:
        yield b""

    http = MagicMock()
    http.stream = _stream
    return http


def _web_request(chat_id: str) -> MagicMock:
    request = MagicMock()
    request.action_mode = "general"
    request.resume_value = None
    request.chat_id = chat_id
    request.message_id = "msg-paste"
    request.query = _PASTE
    request.regenerate_instruction = None
    request.sibling_group_id = None
    request.timestamp = None
    request.timezone = "UTC"
    request.agent_id = "default"
    request.ephemeral_subagents = None
    request.incognito_mode = False
    request.active_moa_preset_id = None
    return request


@pytest.mark.asyncio
async def test_the_turn_stores_the_paste_in_a_file_that_outlives_the_runs_own_copy(
    db_session: AsyncSession,
    fake_home: Path,
    http_request: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_session, fake_home
    chat_id = (await ChatService.get_or_create_channel_chat("test:typed-paste", "test")).id
    request = _web_request(chat_id)
    monkeypatch.setattr(f"{_ORCHESTRATOR}.try_stream_reconnect", AsyncMock(return_value=None))
    monkeypatch.setattr(f"{_ORCHESTRATOR}.check_stream_risk", AsyncMock(return_value=None))
    monkeypatch.setattr(f"{_ORCHESTRATOR}._count_pending_approvals", AsyncMock(return_value=0))
    read_by_the_run: list[str] = []

    async def run_the_setup_the_turn_runs(**launch: object) -> JSONResponse:
        text_content, typed_text = launch["text_content"], launch["typed_text"]
        assert isinstance(text_content, str) and isinstance(typed_text, str)
        read_by_the_run.append(text_content)
        await chat_history_bootstrap.persist_user_message(request, text_content=text_content, typed_text=typed_text)
        return JSONResponse(status_code=202, content={})

    monkeypatch.setattr(
        "app.services.agent.stream_session.orchestrator_turn_launch.launch_early_buffered_stream",
        run_the_setup_the_turn_runs,
    )

    response = await run_agent_stream(request, http_request)

    assert response.status_code == 202
    (reference,) = read_by_the_run
    assert reference.startswith("<file_spillover") and ".myrm/spillover/" in reference
    (message,) = [m for m in await ChatService.get_all_messages(chat_id) if m.role == "user"]
    assert message.content.startswith("<file_spillover") and f"{KEPT_DIR_NAME}/" in message.content
    assert ".myrm/spillover/" not in message.content
    assert message.extra_data is not None
    spillover = message.extra_data["spillover"]
    assert isinstance(spillover, dict)
    assert Path(str(spillover["spillover_path"])).read_text(encoding="utf-8") == _PASTE


@pytest.mark.asyncio
async def test_the_launched_turn_hands_the_typed_text_to_the_persistence_call(monkeypatch: pytest.MonkeyPatch) -> None:
    request = MagicMock()
    request.message_id = "msg-typed"
    request.multiplexed = True
    request.chat_id = None
    request.agent_id = None
    buffer = MagicMock()
    buffer.append = AsyncMock()
    buffer.end_stream = AsyncMock()
    persisted: dict[str, object] = {}

    async def stop_after_recording(_request: object, **kwargs: object) -> None:
        persisted.update(kwargs)
        raise RuntimeError("setup stops here")

    monkeypatch.setattr(chat_history_bootstrap, "persist_user_message", stop_after_recording)

    await launch_early_buffered_stream(
        request=request,
        http_request=MagicMock(),
        text_content="reference the run reads",
        typed_text="what was typed",
        stream_started_at_monotonic=0.0,
        registry=MagicMock(),
        buffer=buffer,
        session_reservation=MagicMock(),
        record_terminal_failure=AsyncMock(),
    )
    turn = next(task for task in asyncio.all_tasks() if task.get_name() == "agent_turn_msg-typed")
    await asyncio.wait_for(turn, timeout=5)

    assert persisted == {"text_content": "reference the run reads", "typed_text": "what was typed"}
