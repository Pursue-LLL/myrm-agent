"""DB integration tests for the functions that write, clear and replay an InterruptedTurnMarker.

Uses real SQLite via the `session_factory` fixture — no mocking DB layer. Validates:
1. `write_interrupted_turn_marker` creates the chat's marker, replaces an earlier one and records the id the user's
   message was stored under
2. `_clear_interrupted_turn_marker` removes the marker row it is given
3. The replay of an interrupted turn does not repeat the interrupted user's message as history
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from app.database.models.chat import InterruptedTurnMarker, Message


@pytest.mark.asyncio
async def test_write_marker_function_creates_and_replaces(session_factory, test_chat):
    """write_interrupted_turn_marker should create a new marker and replace existing one."""

    from app.services.agent.stream_session.orchestrator_turn_body import write_interrupted_turn_marker

    request = MagicMock()
    request.chat_id = test_chat
    request.message_id = "msg-write-001"
    request.action_mode = "fast"
    request.agent_id = "test-agent"

    params = MagicMock()
    params.model_dump.return_value = {"query": "test write", "model_cfg": {"provider": "test"}}

    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        await write_interrupted_turn_marker(request, params)

    async with session_factory() as db:
        result = await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))
        marker = result.scalar_one()

    assert marker.user_message_id == "msg-write-001"
    assert marker.action_mode == "fast"
    assert marker.serialized_params["query"] == "test write"

    request.message_id = "msg-write-002"
    params.model_dump.return_value = {"query": "second write", "model_cfg": {"provider": "test"}}

    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        await write_interrupted_turn_marker(request, params)

    async with session_factory() as db:
        result = await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))
        marker = result.scalar_one()

    assert marker.user_message_id == "msg-write-002", "Second write should replace first"
    assert marker.serialized_params["query"] == "second write"


@pytest.mark.asyncio
async def test_clear_marker_function(session_factory, test_chat):
    """_clear_interrupted_turn_marker should remove the marker row it is given."""
    from app.services.agent.stream_session.stream_finalize import _clear_interrupted_turn_marker

    marker_id = str(uuid.uuid4())
    async with session_factory() as db:
        db.add(
            InterruptedTurnMarker(
                id=marker_id,
                chat_id=test_chat,
                user_message_id="msg-clear",
                action_mode="fast",
            )
        )
        await db.commit()

    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        await _clear_interrupted_turn_marker(test_chat, marker_id=marker_id)

    async with session_factory() as db:
        result = await db.execute(
            select(func.count()).select_from(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat)
        )
        assert result.scalar() == 0


@pytest.mark.asyncio
async def test_marker_records_the_id_the_user_row_was_stored_under(session_factory, test_chat):
    """The stored row id can differ from the request id, and replay must exclude the stored one."""
    from app.services.agent.stream_session.orchestrator_turn_body import write_interrupted_turn_marker

    request = MagicMock()
    request.chat_id = test_chat
    request.message_id = "msg-requested"
    request.action_mode = "fast"
    request.agent_id = "test-agent"
    params = MagicMock()
    params.model_dump.return_value = {"query": "q", "model_cfg": {"provider": "test"}}

    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        await write_interrupted_turn_marker(request, params, user_message_id="msg-persisted")

    async with session_factory() as db:
        marker = (await db.execute(select(InterruptedTurnMarker).where(InterruptedTurnMarker.chat_id == test_chat))).scalar_one()
    assert marker.user_message_id == "msg-persisted"


@pytest.mark.asyncio
async def test_replay_history_does_not_repeat_the_interrupted_users_message(session_factory, test_chat):
    """The interrupted query is replayed through params, so its stored row must not also be history."""
    from app.lifecycle.auto_continue import _dispatch_auto_continue

    now = datetime.now(UTC).replace(tzinfo=None)
    async with session_factory() as db:
        for index, (message_id, role, content) in enumerate(
            (
                ("u-old", "user", "Earlier question"),
                ("a-old", "assistant", "Earlier answer"),
                ("u-interrupted", "user", "Interrupted question"),
            )
        ):
            at = now - timedelta(minutes=10 - index)
            db.add(
                Message(
                    id=message_id,
                    chat_id=test_chat,
                    role=role,
                    content=content,
                    sent_at=at,
                    sent_timezone="UTC",
                    created_at=at,
                )
            )
        marker = InterruptedTurnMarker(
            id=str(uuid.uuid4()),
            chat_id=test_chat,
            user_message_id="u-interrupted",
            action_mode="fast",
            serialized_params={"query": "Interrupted question", "model_cfg": {"provider": "test"}},
        )
        db.add(marker)
        await db.commit()

    seen_history: list[object] = []

    async def _fake_stream(*_args: object, **kwargs: MagicMock):
        seen_history.append(kwargs["params"].chat_history)
        yield {"type": "message", "data": "resumed"}

    with (
        patch("app.ai_agents.GeneralAgentParams") as params_cls,
        patch("app.services.agent.streaming.ai_agent_service_stream", side_effect=_fake_stream),
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", AsyncMock()),
        patch("app.services.infra.system_notification.SystemNotificationService.create_notification", AsyncMock()),
    ):
        params_cls.model_validate.return_value = MagicMock(model_cfg=MagicMock(), chat_id=test_chat, timezone="UTC")
        await _dispatch_auto_continue(marker, session_factory)

    assert len(seen_history) == 1
    replayed = str(seen_history[0])
    assert "Earlier question" in replayed
    assert "Earlier answer" in replayed
    assert "Interrupted question" not in replayed
