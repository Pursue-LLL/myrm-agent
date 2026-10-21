"""Integration tests for persisted-history → LangGraph checkpoint continuity alignment."""

from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver, empty_checkpoint
from langgraph.checkpoint.memory import MemorySaver

from app.services.chat.session_continuity_service import (
    CheckpointClearError,
    invalidate_chat_checkpoint,
)
from tests.support.local_harness_continuity import patch_session_continuity_sync


@pytest.fixture(autouse=True)
def _local_harness_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_session_continuity_sync(monkeypatch)


async def _seed_thread(saver: BaseCheckpointSaver[str], thread_id: str) -> None:
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": [HumanMessage("question")]}
    await saver.aput(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        checkpoint,
        {"source": "test", "step": 0, "parents": {}},
        {},
    )


@pytest.mark.asyncio
async def test_invalidate_chat_checkpoint_propagates_checkpoint_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_clear(*_args: object, **_kwargs: object) -> int:
        raise CheckpointClearError("Deleted 0/2 checkpoint threads for chat test-chat")

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.clear_checkpoint_threads",
        _raise_clear,
    )
    monkeypatch.setattr(
        "app.platform_utils.get_checkpointer",
        lambda: MemorySaver(),
    )

    with pytest.raises(CheckpointClearError, match="Deleted 0/2"):
        await invalidate_chat_checkpoint(f"continuity-{uuid.uuid4().hex[:8]}")


@pytest.mark.asyncio
async def test_invalidate_chat_checkpoint_clears_every_thread_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saver = MemorySaver()
    chat_id = f"continuity-{uuid.uuid4().hex[:8]}"
    for thread_id in (chat_id, f"chat_{chat_id}"):
        await _seed_thread(saver, thread_id)
    monkeypatch.setattr("app.platform_utils.get_checkpointer", lambda: saver)

    cleared = await invalidate_chat_checkpoint(chat_id)

    assert cleared == 2
    for thread_id in (chat_id, f"chat_{chat_id}"):
        assert await saver.aget_tuple({"configurable": {"thread_id": thread_id}}) is None
