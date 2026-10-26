"""Bind chats to workspaces for API tests that read what a chat's runs wrote to disk.

The files API resolves a chat's workspace through ``ChatService``, which talks to the application database rather
than the in-memory session an API test seeds; this helper answers that lookup for the chats a test names.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.database.dto import ChatDTO


@contextmanager
def chats_bound_to_workspaces(bindings: dict[str, Path] | None = None, *, default: Path | None = None) -> Iterator[None]:
    """Make ``ChatService.get_chat_metadata`` report chats as bound to workspace directories.

    ``bindings`` maps chat ids to their workspace; ``default`` binds every other chat id, for tests that mint
    random chat ids and keep everything under one directory.
    """
    now = datetime.now(UTC)
    chats = {
        chat_id: ChatDTO(id=chat_id, workspace_dir=str(workspace), created_at=now, updated_at=now)
        for chat_id, workspace in (bindings or {}).items()
    }

    async def get_chat_metadata(chat_id: str) -> ChatDTO | None:
        if chat_id in chats or default is None:
            return chats.get(chat_id)
        return ChatDTO(id=chat_id, workspace_dir=str(default), created_at=now, updated_at=now)

    with patch(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        AsyncMock(side_effect=get_chat_metadata),
    ):
        yield
