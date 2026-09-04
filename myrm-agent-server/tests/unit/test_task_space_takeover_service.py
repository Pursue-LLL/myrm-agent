"""Unit tests for task_space_service takeover linkage to space and session."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.browser_spaces.task_space_service import TaskSpaceService


@pytest.mark.asyncio
async def test_set_takeover_triggers_space_pause_and_resume() -> None:
    mock_manager = MagicMock()
    mock_space = MagicMock()
    mock_space.space_id = "space_abc"
    mock_space.name = "Test Space"
    mock_space.is_active = True
    mock_space.created_at = 1000.0
    mock_space.last_accessed_at = 1000.0
    mock_space.context = None
    mock_space.metadata = {}
    mock_space.pause_for_takeover = AsyncMock()
    mock_space.resume_from_takeover = AsyncMock()

    mock_manager.get_space.return_value = mock_space

    service = TaskSpaceService(manager=mock_manager)

    # 1. Enable takeover
    info = await service.set_takeover("space_abc", True)
    assert info.takeover_active is True
    assert info.status == "takeover"
    mock_space.pause_for_takeover.assert_awaited_once()

    # 2. Disable takeover (resume)
    info_resumed = await service.set_takeover("space_abc", False)
    assert info_resumed.takeover_active is False
    assert info_resumed.status == "idle"
    mock_space.resume_from_takeover.assert_awaited_once()
