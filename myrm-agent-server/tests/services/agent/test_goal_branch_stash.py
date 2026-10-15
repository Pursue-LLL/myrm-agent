from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.storage import GoalStorage
from myrm_agent_harness.agent.goals.types import GoalStatus

from app.config.settings import settings
from app.services.agent.goals import goal_branch_stash
from app.services.agent.goals.goal_branch_stash import (
    check_and_handle_branch_stash,
    get_current_git_branch,
    start_branch_watcher,
    stop_branch_watcher,
)
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.event.app_event_bus import AppEventType

_BRANCH_GETTER = "app.services.agent.goals.goal_branch_stash.get_current_git_branch"
_STORAGE_GETTER = "app.platform_utils.get_storage_provider"


@pytest.fixture
def mock_storage():
    store = {}
    storage = AsyncMock()

    async def write(key, content, content_type=None):
        store[key] = content

    async def read(key):
        return store.get(key)

    async def delete(key):
        store.pop(key, None)

    storage.write.side_effect = write
    storage.read.side_effect = read
    storage.delete.side_effect = delete
    storage.store = store
    return storage


@pytest.mark.asyncio
async def test_branch_switch_stashes_and_restores_goals_per_branch(mock_storage) -> None:
    session_id = "test-branch-stash-session"

    with (
        patch(_BRANCH_GETTER, new_callable=AsyncMock) as mock_branch_getter,
        patch(_STORAGE_GETTER, return_value=mock_storage),
    ):
        GoalRegistry.unregister(session_id)
        provider = GoalRegistry.get_or_create_provider(session_id)

        # branch_b already has its own goal parked by the harness stash API.
        mock_branch_getter.return_value = "branch_a"
        await check_and_handle_branch_stash(session_id)
        goal_b = await provider.create_goal(session_id=session_id, objective="Fix the crash")
        assert await provider.stash_goal(session_id, "branch_b")
        goal_a = await provider.create_goal(session_id=session_id, objective="Build auth module")
        assert goal_a.status == GoalStatus.ACTIVE

        # Switching to branch_b: branch_a's goal is parked, branch_b's goal comes back.
        mock_branch_getter.return_value = "branch_b"
        await check_and_handle_branch_stash(session_id)

        assert (await provider.get_goal(goal_a.goal_id)).status == GoalStatus.PAUSED
        active_on_b = await provider.get_active_goal(session_id)
        assert active_on_b is not None
        assert active_on_b.goal_id == goal_b.goal_id

        # Switching back swaps them again.
        mock_branch_getter.return_value = "branch_a"
        await check_and_handle_branch_stash(session_id)

        active_on_a = await provider.get_active_goal(session_id)
        assert active_on_a is not None
        assert active_on_a.goal_id == goal_a.goal_id
        assert active_on_a.status == GoalStatus.ACTIVE
        assert (await provider.get_goal(goal_b.goal_id)).status == GoalStatus.PAUSED

        GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_branch_without_stash_adopts_the_active_goal(mock_storage) -> None:
    session_id = "test-branch-migrate-session"

    with (
        patch(_BRANCH_GETTER, new_callable=AsyncMock) as mock_branch_getter,
        patch(_STORAGE_GETTER, return_value=mock_storage),
        patch("app.services.event.app_event_bus.get_event_bus") as get_bus,
    ):
        GoalRegistry.unregister(session_id)
        provider = GoalRegistry.get_or_create_provider(session_id)

        mock_branch_getter.return_value = "branch_a"
        await check_and_handle_branch_stash(session_id)
        goal = await provider.create_goal(session_id=session_id, objective="Build auth module")

        mock_branch_getter.return_value = "branch_new"
        await check_and_handle_branch_stash(session_id)

        assert (await provider.get_goal(goal.goal_id)).status == GoalStatus.ACTIVE
        assert await GoalStorage(mock_storage).get_stash(session_id, "branch_a") is None
        assert get_bus.return_value.publish.call_args.args[0].data["migrated"] is True

        GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_unreadable_stash_counts_as_no_stash(mock_storage) -> None:
    """A stash the harness cannot parse could never be restored, so the goal must not be parked behind it."""
    session_id = "test-branch-corrupt-stash-session"

    with (
        patch(_BRANCH_GETTER, new_callable=AsyncMock) as mock_branch_getter,
        patch(_STORAGE_GETTER, return_value=mock_storage),
    ):
        GoalRegistry.unregister(session_id)
        provider = GoalRegistry.get_or_create_provider(session_id)

        mock_branch_getter.return_value = "branch_a"
        await check_and_handle_branch_stash(session_id)
        goal = await provider.create_goal(session_id=session_id, objective="Build auth module")
        await GoalStorage(mock_storage).save_stash("branch_b", session_id, "other-goal", None, None)
        (stash_key,) = [key for key in mock_storage.store if key.endswith("/branch_b")]
        mock_storage.store[stash_key] = b"not json"

        mock_branch_getter.return_value = "branch_b"
        await check_and_handle_branch_stash(session_id)

        assert (await provider.get_goal(goal.goal_id)).status == GoalStatus.ACTIVE

        GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_unchanged_branch_is_a_no_op(mock_storage) -> None:
    session_id = "test-branch-noop-session"

    with (
        patch(_BRANCH_GETTER, new_callable=AsyncMock, return_value="branch_a"),
        patch(_STORAGE_GETTER, return_value=mock_storage),
        patch("app.services.event.app_event_bus.get_event_bus") as get_bus,
    ):
        GoalRegistry.unregister(session_id)
        await check_and_handle_branch_stash(session_id)
        await check_and_handle_branch_stash(session_id)

        assert get_bus.return_value.publish.call_count == 1
        assert mock_storage.store[f"goals_last_branch/{session_id}"] == b"branch_a"

        GoalRegistry.unregister(session_id)


@pytest.mark.asyncio
async def test_branch_switch_publishes_goal_branch_switched_event(mock_storage) -> None:
    session_id = "test-branch-event-session"
    bus = MagicMock()

    with (
        patch(_BRANCH_GETTER, new_callable=AsyncMock) as mock_branch_getter,
        patch(_STORAGE_GETTER, return_value=mock_storage),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=bus),
    ):
        GoalRegistry.unregister(session_id)
        mock_branch_getter.return_value = "branch_a"
        await check_and_handle_branch_stash(session_id)
        mock_branch_getter.return_value = "branch_b"
        await check_and_handle_branch_stash(session_id)
        GoalRegistry.unregister(session_id)

    events = [call.args[0] for call in bus.publish.call_args_list]
    assert [event.event_type for event in events] == [AppEventType.GOAL_BRANCH_SWITCHED] * 2
    assert events[-1].event_type == "goal:branch_switched"  # the wire name the frontend listens for
    assert events[-1].data["branch"] == "branch_b"
    assert events[-1].data["stashed_branch"] == "branch_a"


@pytest.mark.asyncio
async def test_get_current_git_branch_zero_subprocess(tmp_path) -> None:
    """Test get_current_git_branch accurately delegates to pure-file resolver."""
    repo = tmp_path / "zero_subproc_repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/feature/fast-branch\n", encoding="utf-8")

    branch = await get_current_git_branch(str(repo))
    assert branch == "feature/fast-branch"


@pytest.mark.asyncio
async def test_session_ids_lists_live_providers(mock_storage) -> None:
    with patch(_STORAGE_GETTER, return_value=mock_storage):
        GoalRegistry.unregister("session-ids-a")
        GoalRegistry.get_or_create_provider("session-ids-a")
        assert "session-ids-a" in GoalRegistry.session_ids()
        GoalRegistry.unregister("session-ids-a")
        assert "session-ids-a" not in GoalRegistry.session_ids()


@pytest.mark.asyncio
async def test_branch_watcher_reacts_to_head_changes_and_stops(tmp_path: Path, mock_storage) -> None:
    repo = tmp_path / "watched_repo"
    head = repo / ".git" / "HEAD"
    head.parent.mkdir(parents=True)
    head.write_text("ref: refs/heads/main\n", encoding="utf-8")
    checker = AsyncMock()

    async def wait_for_calls(expected: int) -> None:
        for _ in range(200):
            if checker.await_count >= expected:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"watcher ran {checker.await_count} checks, expected {expected}")

    with (
        patch(_STORAGE_GETTER, return_value=mock_storage),
        patch.object(settings, "project_dir", str(repo)),
        patch.object(goal_branch_stash, "_POLL_INTERVAL_SECONDS", 0.01),
        patch.object(goal_branch_stash, "check_and_handle_branch_stash", checker),
    ):
        GoalRegistry.unregister("watched-session")
        GoalRegistry.get_or_create_provider("watched-session")
        start_branch_watcher()
        first_task = goal_branch_stash._watcher_task
        start_branch_watcher()
        assert goal_branch_stash._watcher_task is first_task

        await wait_for_calls(1)
        assert checker.await_args.args == ("watched-session",)
        assert checker.await_args.kwargs == {"workspace_dir": str(repo.resolve())}

        # A checkout rewrites .git/HEAD; the watcher must notice the new mtime.
        stat = head.stat()
        os.utime(head, (stat.st_atime, stat.st_mtime + 5))
        await wait_for_calls(2)

        stop_branch_watcher()
        assert goal_branch_stash._watcher_task is None
        await asyncio.sleep(0.05)
        assert first_task.done()

        GoalRegistry.unregister("watched-session")
