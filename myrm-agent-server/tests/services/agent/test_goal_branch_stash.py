from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.services.agent.goal_registry import (
    GoalRegistry,
    check_and_handle_branch_stash,
)


@pytest.fixture
def mock_storage():
    store = {}
    storage = AsyncMock()

    async def write(key, content):
        store[key] = content

    async def read(key):
        return store.get(key)

    async def delete(key):
        store.pop(key, None)

    async def write_text(path, text):
        store[path] = text.encode("utf-8")

    async def read_text(path):
        if path not in store:
            raise FileNotFoundError(f"{path} not found")
        val = store[path]
        return val.decode("utf-8") if isinstance(val, bytes) else str(val)

    async def exists(path):
        return path in store

    storage.write.side_effect = write
    storage.read.side_effect = read
    storage.delete.side_effect = delete
    storage.write_text.side_effect = write_text
    storage.read_text.side_effect = read_text
    storage.exists.side_effect = exists
    return storage


@pytest.mark.asyncio
async def test_check_and_handle_branch_stash_integration(mock_storage) -> None:
    session_id = "test-branch-stash-session"

    with patch(
        "app.services.agent.goal_registry.get_current_git_branch", new_callable=AsyncMock
    ) as mock_branch_getter, patch(
        "app.platform_utils.get_storage_provider", return_value=mock_storage
    ):
        # Ensure GoalRegistry has a clean provider for this session
        GoalRegistry.unregister(session_id)
        provider = GoalRegistry.get_or_create_provider(session_id)

        # 1. Start on branch_a and create an active goal
        mock_branch_getter.return_value = "branch_a"
        await check_and_handle_branch_stash(session_id)
        goal = await provider.create_goal(
            session_id=session_id, objective="Build auth module"
        )

        # Verify goal is active on branch_a
        assert goal.status == GoalStatus.ACTIVE

        # 2. Switch to branch_b (which has a stash to force branch_a to pause)
        mock_branch_getter.return_value = "branch_b"
        from myrm_agent_harness.agent.goals.storage import _GOAL_NAMESPACE
        await mock_storage.write(f"{_GOAL_NAMESPACE}_stash/{session_id}/branch_b", b"dummy")
        
        # Trigger branch perception stash
        await check_and_handle_branch_stash(session_id)
        
        # Goal for branch_a should now be stashed & PAUSED
        goal_a = await provider.get_goal(goal.goal_id)
        assert goal_a.status == GoalStatus.PAUSED

        # Active goal on branch_b should be None (fresh start!)
        active_on_b = await provider.get_active_goal(session_id)
        assert active_on_b is None

        # 3. Switch back to branch_a
        mock_branch_getter.return_value = "branch_a"
        await check_and_handle_branch_stash(session_id)

        # Goal for branch_a should be automatically RESTORED and ACTIVE!
        active_on_a = await provider.get_active_goal(session_id)
        assert active_on_a is not None
        assert active_on_a.goal_id == goal.goal_id
        assert active_on_a.status == GoalStatus.ACTIVE

        # Clean up
        GoalRegistry.unregister(session_id)
