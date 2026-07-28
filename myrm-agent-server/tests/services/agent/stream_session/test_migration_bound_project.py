from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.database.dto import ChatDTO
from app.services.agent.params import AgentRequest
from app.services.agent.stream_session.migration_bound_project import apply_migration_bound_project


def _request(**overrides: object) -> AgentRequest:
    base: dict[str, object] = {
        "message_id": "msg-1",
        "chat_id": "chat-1",
        "query": "hello",
        "migration_bound_project_id": "project-42",
    }
    base.update(overrides)
    return AgentRequest(**base)


def _chat(**overrides: object) -> ChatDTO:
    now = datetime.now(tz=UTC)
    base: dict[str, object] = {
        "id": "chat-1",
        "project_id": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return ChatDTO(**base)


@pytest.mark.asyncio
async def test_apply_migration_bound_project_moves_unassigned_chat() -> None:
    chat = _chat()
    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new=AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.project.project_service.ProjectService.move_chat_to_project",
            new=AsyncMock(return_value=True),
        ) as move_mock,
    ):
        await apply_migration_bound_project(_request())

    move_mock.assert_awaited_once_with("chat-1", "project-42")


@pytest.mark.asyncio
async def test_apply_migration_bound_project_skips_when_chat_already_assigned() -> None:
    chat = _chat(project_id="existing-project")
    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new=AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.project.project_service.ProjectService.move_chat_to_project",
            new=AsyncMock(return_value=True),
        ) as move_mock,
    ):
        await apply_migration_bound_project(_request())

    move_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_migration_bound_project_skips_on_resume() -> None:
    with patch(
        "app.services.project.project_service.ProjectService.move_chat_to_project",
        new=AsyncMock(return_value=True),
    ) as move_mock:
        await apply_migration_bound_project(
            _request(resume_value={"decision": "approve", "action": "completed"}),
        )

    move_mock.assert_not_awaited()
