"""Tests for manual chat memory extract retry."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.database.dto import MessageDTO
from app.services.memory.extract_retry import retry_chat_memory_extract as retry_module
from app.services.memory.extract_retry.retry_chat_memory_extract import (
    _find_last_turn,
    run_retry_extract_for_chat,
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


def _chat_dto(*, chat_id: str = "chat-1", is_incognito: bool = False):
    from app.database.dto import ChatDTO

    now = datetime.now(UTC)
    return ChatDTO(
        id=chat_id,
        is_incognito=is_incognito,
        created_at=now,
        updated_at=now,
    )


async def _patch_chat_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    chat=None,
    messages: list[MessageDTO] | None = None,
) -> None:
    monkeypatch.setattr(
        "app.services.memory.extract_retry.retry_chat_memory_extract.ChatService.get_chat_metadata",
        AsyncMock(return_value=chat),
    )
    monkeypatch.setattr(
        "app.services.memory.extract_retry.retry_chat_memory_extract.ChatService.get_all_messages",
        AsyncMock(return_value=messages or []),
    )


@pytest.mark.asyncio
async def test_schedule_retry_enqueues_and_returns_scheduled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        _message(message_id="u1", role="user", content="question"),
        _message(message_id="a1", role="assistant", content="answer"),
    ]
    await _patch_chat_service(
        monkeypatch,
        chat=_chat_dto(),
        messages=messages,
    )
    enqueue_mock = AsyncMock(return_value="queued")
    monkeypatch.setattr(
        "app.services.memory.extract_retry.extract_retry_queue.enqueue", enqueue_mock
    )

    status = await schedule_retry_chat_memory_extract("chat-1")

    assert status == "scheduled"
    enqueue_mock.assert_awaited_once_with("chat-1", reset_failed=True)


@pytest.mark.asyncio
async def test_schedule_retry_maps_already_queued_to_in_flight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        _message(message_id="u1", role="user", content="question"),
        _message(message_id="a1", role="assistant", content="answer"),
    ]
    await _patch_chat_service(
        monkeypatch,
        chat=_chat_dto(),
        messages=messages,
    )
    enqueue_mock = AsyncMock(return_value="already_queued")
    monkeypatch.setattr(
        "app.services.memory.extract_retry.extract_retry_queue.enqueue", enqueue_mock
    )

    status = await schedule_retry_chat_memory_extract("chat-1")

    assert status == "already_in_flight"


@pytest.mark.asyncio
async def test_schedule_retry_rejects_missing_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _patch_chat_service(monkeypatch, chat=None)

    with pytest.raises(ValueError, match="Chat not found"):
        await schedule_retry_chat_memory_extract("chat-1")


@pytest.mark.asyncio
async def test_schedule_retry_rejects_incognito_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _patch_chat_service(
        monkeypatch,
        chat=_chat_dto(chat_id="chat-incognito", is_incognito=True),
    )

    with pytest.raises(ValueError, match="Incognito"):
        await schedule_retry_chat_memory_extract("chat-incognito")


@pytest.mark.asyncio
async def test_schedule_retry_rejects_chat_without_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _patch_chat_service(monkeypatch, chat=_chat_dto(), messages=[])

    with pytest.raises(ValueError, match="has no messages"):
        await schedule_retry_chat_memory_extract("chat-1")


@pytest.mark.asyncio
async def test_run_retry_extract_for_chat_returns_false_when_chat_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _patch_chat_service(monkeypatch, chat=None)
    run_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.memory.extract_retry.retry_chat_memory_extract._run_retry_extract",
        run_mock,
    )

    assert await run_retry_extract_for_chat("chat-1") is False
    run_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_retry_extract_for_chat_returns_false_when_no_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [_message(message_id="u1", role="user", content="solo")]
    await _patch_chat_service(
        monkeypatch,
        chat=_chat_dto(),
        messages=messages,
    )
    run_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.memory.extract_retry.retry_chat_memory_extract._run_retry_extract",
        run_mock,
    )

    assert await run_retry_extract_for_chat("chat-1") is False
    run_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_retry_extract_for_chat_runs_latest_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages = [
        _message(message_id="u1", role="user", content="question"),
        _message(message_id="a1", role="assistant", content="answer"),
    ]
    await _patch_chat_service(
        monkeypatch,
        chat=_chat_dto(),
        messages=messages,
    )
    run_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.memory.extract_retry.retry_chat_memory_extract._run_retry_extract",
        run_mock,
    )

    assert await run_retry_extract_for_chat("chat-1") is True
    run_mock.assert_awaited_once_with(
        "chat-1",
        "question",
        [],
        "answer",
        source="manual_retry_extract",
        workspace_path=None,
    )


@pytest.mark.asyncio
async def test_run_retry_extract_uses_chat_binding_and_compressed_track(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        "app.services.memory.extract_retry.resolve_chat_extraction_llm.resolve_chat_extraction_llm",
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
        "myrm_agent_harness.api.hooks.auto_extract_memories",
        auto_extract,
    )
    monkeypatch.setattr(
        "app.ai_agents.extensions.extraction_lifecycle.make_extraction_lifecycle_observer",
        lambda chat_id, **kwargs: f"observer-{chat_id}",
    )
    configs = MagicMock()
    configs.personal_settings_dict = {"privacyDeepScan": False}
    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=configs),
    )

    await retry_module._run_retry_extract(
        "chat-1",
        "question",
        [],
        "answer",
        source="manual_retry_extract",
        workspace_path="/tmp/ws",
    )

    resolve_binding.assert_awaited_once_with("chat-1")
    create_manager.assert_awaited_once()
    manager_kwargs = create_manager.call_args.kwargs
    assert manager_kwargs["dedup_llm"] is extraction_llm
    assert manager_kwargs["on_conflict"] == "conflict-agent-marketing"
    auto_extract.assert_awaited_once()
    call_kwargs = auto_extract.call_args.kwargs
    assert call_kwargs["enable_verbatim"] is False
    assert call_kwargs["lifecycle_observer"] == "observer-chat-1"
    assert call_kwargs["deep_scan"] is False
