"""Tests for manual chat memory extract retry."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.dto import MessageDTO
from app.services.memory import retry_chat_memory_extract as retry_module
from app.services.memory.retry_chat_memory_extract import (
    _find_last_turn,
    schedule_retry_chat_memory_extract,
)


def _message(
    *,
    message_id: str,
    role: str,
    content: str,
    active: bool = True,
) -> MessageDTO:
    now = datetime.now(UTC)
    return MessageDTO(
        id=message_id,
        chat_id="chat-1",
        role=role,
        content=content,
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
        is_active=active,
    )


def test_find_last_turn_builds_history_before_latest_user() -> None:
    messages = [
        _message(message_id="u1", role="user", content="first question"),
        _message(message_id="a1", role="assistant", content="first answer"),
        _message(message_id="u2", role="user", content="second question"),
        _message(message_id="a2", role="assistant", content="second answer"),
    ]

    last_user, last_assistant, history = _find_last_turn(messages)

    assert last_user.id == "u2"
    assert last_assistant.id == "a2"
    assert history == [["human", "first question"], ["assistant", "first answer"]]


def test_find_last_turn_raises_when_assistant_missing() -> None:
    messages = [_message(message_id="u1", role="user", content="solo question")]

    with pytest.raises(ValueError, match="No assistant reply"):
        _find_last_turn(messages)


@pytest.mark.asyncio
async def test_schedule_retry_skips_when_already_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retry_module._in_flight_retries.add("chat-1")
    mock_get_messages = AsyncMock()
    monkeypatch.setattr(
        "app.services.memory.retry_chat_memory_extract.ChatService.get_all_messages",
        mock_get_messages,
    )

    status = await schedule_retry_chat_memory_extract("chat-1")

    assert status == "already_in_flight"
    mock_get_messages.assert_not_awaited()
    retry_module._in_flight_retries.discard("chat-1")


def _chat_dto(*, chat_id: str = "chat-1", is_incognito: bool = False):
    from app.database.dto import ChatDTO

    now = datetime.now(UTC)
    return ChatDTO(
        id=chat_id,
        is_incognito=is_incognito,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_schedule_retry_rejects_incognito_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.memory.retry_chat_memory_extract.ChatService.get_chat_metadata",
        AsyncMock(return_value=_chat_dto(chat_id="chat-incognito", is_incognito=True)),
    )

    with pytest.raises(ValueError, match="Incognito"):
        await schedule_retry_chat_memory_extract("chat-incognito")


@pytest.mark.asyncio
async def test_run_retry_extract_uses_chat_binding_and_dedup_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.memory import retry_chat_memory_extract as retry_module

    binding = MagicMock()
    binding_context = MagicMock()
    binding_context.binding = binding
    binding_context.agent_id = "agent-marketing"
    binding_context.memory_decay_profile = None

    extraction_llm = object()
    main_llm = object()
    memory_manager = MagicMock()

    resolve_binding = AsyncMock(return_value=binding_context)
    resolve_llm = AsyncMock(return_value=(main_llm, extraction_llm))
    create_manager = AsyncMock(return_value=memory_manager)
    auto_extract = AsyncMock()

    monkeypatch.setattr(
        "app.services.context.context_assembly.ContextAssemblyService.resolve_binding_for_chat",
        resolve_binding,
    )
    monkeypatch.setattr(
        "app.services.memory.resolve_chat_extraction_llm.resolve_chat_extraction_llm",
        resolve_llm,
    )
    monkeypatch.setattr(
        "app.core.memory.adapters.setup.create_memory_manager",
        create_manager,
    )
    monkeypatch.setattr(
        "app.core.memory.adapters.setup.create_conflict_callback",
        lambda agent_id: f"conflict-{agent_id}",
    )
    monkeypatch.setattr(
        "app.services.agent.platform_config.require_platform_embedding_config",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent._internals.memory_extraction.auto_extract_memories",
        auto_extract,
    )
    monkeypatch.setattr(
        "app.ai_agents.extensions.extraction_lifecycle.make_extraction_lifecycle_observer",
        lambda chat_id, **kwargs: f"observer-{chat_id}",
    )

    await retry_module._run_retry_extract("chat-1", "question", [], "answer")

    resolve_binding.assert_awaited_once_with("chat-1")
    create_manager.assert_awaited_once()
    manager_kwargs = create_manager.call_args.kwargs
    assert manager_kwargs["dedup_llm"] is extraction_llm
    assert manager_kwargs["on_conflict"] == "conflict-agent-marketing"
    auto_extract.assert_awaited_once()
    assert auto_extract.call_args.kwargs["lifecycle_observer"] == "observer-chat-1"


@pytest.mark.asyncio
async def test_schedule_retry_runs_extract_in_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        _message(message_id="u1", role="user", content="question"),
        _message(message_id="a1", role="assistant", content="answer"),
    ]
    monkeypatch.setattr(
        "app.services.memory.retry_chat_memory_extract.ChatService.get_chat_metadata",
        AsyncMock(return_value=_chat_dto(chat_id="chat-1", is_incognito=False)),
    )
    monkeypatch.setattr(
        "app.services.memory.retry_chat_memory_extract.ChatService.get_all_messages",
        AsyncMock(return_value=messages),
    )

    run_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.memory.retry_chat_memory_extract._run_retry_extract",
        run_mock,
    )

    with patch(
        "app.services.memory.retry_chat_memory_extract.asyncio.create_task"
    ) as create_task:
        status = await schedule_retry_chat_memory_extract("chat-1")

    assert status == "scheduled"

    create_task.assert_called_once()
    guarded_runner = create_task.call_args.args[0]
    await guarded_runner

    run_mock.assert_awaited_once_with("chat-1", "question", [], "answer")
    assert "chat-1" not in retry_module._in_flight_retries
