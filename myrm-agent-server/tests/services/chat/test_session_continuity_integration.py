"""Integration tests for DB → LangGraph checkpoint continuity sync."""

from __future__ import annotations

import uuid

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.services.chat.session_continuity_service import (
    ContinuitySyncError,
    sync_chat_checkpoint_from_db,
)
from tests.support.local_harness_continuity import patch_session_continuity_sync


@pytest.fixture(autouse=True)
def _local_harness_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_session_continuity_sync(monkeypatch)


@pytest.mark.asyncio
async def test_sync_chat_checkpoint_from_db_propagates_continuity_sync_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_history(_chat_id: str, **_kwargs: object) -> list[list[str]]:
        return [["human", "hello"], ["assistant", "world"]]

    async def _raise_sync(*_args: object, **_kwargs: object) -> int:
        raise ContinuitySyncError("Synced 0/2 checkpoint threads for chat test-chat")

    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.ChatService.load_web_chat_history",
        _fake_history,
    )
    monkeypatch.setattr(
        "app.services.chat.session_continuity_service.sync_checkpoint_messages",
        _raise_sync,
    )
    monkeypatch.setattr(
        "app.platform_utils.get_checkpointer",
        lambda: MemorySaver(),
    )

    with pytest.raises(ContinuitySyncError, match="Synced 0/2"):
        await sync_chat_checkpoint_from_db(f"continuity-{uuid.uuid4().hex[:8]}")
