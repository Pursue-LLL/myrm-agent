"""Move a session's goal and todos along with the workspace git branch.

[INPUT]
- app.services.agent.goals.goal_registry::GoalRegistry (POS: session-scoped GoalProvider registry)
- myrm_agent_harness.agent.goals.storage::GoalStorage (POS: public stash reader)
- myrm_agent_harness.infra.git::resolve_git_branch (POS: zero-subprocess branch reader)
- myrm_agent_harness.agent.meta_tools.progress (POS: workspace todo store; one list per chat, so a switch moves only this session's)
- app.platform_utils::get_storage_provider (POS: framework storage singleton)

[OUTPUT]
- get_current_git_branch: current branch of the workspace
- check_and_handle_branch_stash: stash, migrate or restore one session's goal after a branch change
- start_branch_watcher / stop_branch_watcher: `.git/HEAD` polling loop over the live goal sessions

[POS]
Server-owned branch awareness for goals. The harness owns the goal and stash storage layout and is only
reached through its public API; the last-seen-branch marker is the one key this module owns.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.goals.storage import GoalStorage
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    delete_todos_sync_from_workspace,
    read_todos_sync_from_workspace,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.infra.git import resolve_git_branch

from app.services.agent.goals.goal_registry import GoalRegistry

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.toolkits.storage.base import StorageProvider

logger = logging.getLogger(__name__)

_LAST_BRANCH_PREFIX = "goals_last_branch"
_POLL_INTERVAL_SECONDS = 0.5
_DISABLED_RETRY_SECONDS = 10.0

_watcher_task: asyncio.Task[None] | None = None


async def get_current_git_branch(workspace_dir: str | None = None) -> str | None:
    """Return the workspace's current Git branch via the zero-subprocess filesystem reader."""
    return resolve_git_branch(workspace_dir)


async def _read_last_branch(storage: StorageProvider, key: str) -> str | None:
    try:
        raw = await storage.read(key)
    except FileNotFoundError:
        return None
    return raw.decode("utf-8") if raw else None


async def _stash_or_migrate(
    provider: GoalProvider,
    session_id: str,
    *,
    last_branch: str,
    branch: str,
    has_stash: bool,
    workspace_dir: str | None,
) -> bool:
    """Stash the active goal of the branch being left; return True when it migrates to ``branch`` instead.

    A branch without a stash has no goal of its own yet, so the active goal follows the user there.
    """
    if not await provider.get_active_goal(session_id):
        return False
    if not has_stash:
        logger.info("Intent-Aware Migration: Migrating active goal to new branch %s", branch)
        return True

    ws_root = workspace_dir or ""
    progress_state: dict[str, object] | None = None
    if ws_root:
        store = read_todos_sync_from_workspace(ws_root, session_id)
        if store is not None:
            progress_state = store.model_dump()

    stashed = await provider.stash_goal(
        session_id=session_id,
        branch_name=last_branch,
        progress_state=progress_state,
        chat_history=None,
    )
    if stashed:
        logger.info("Branch switch perceived: stashed active goal and todos for branch %s", last_branch)
        if ws_root:
            delete_todos_sync_from_workspace(ws_root, session_id)
    return False


async def _restore_branch_goal(
    provider: GoalProvider,
    session_id: str,
    branch: str,
    workspace_dir: str | None,
) -> bool:
    """Restore the goal stashed for ``branch`` and rewrite its todos into the workspace."""
    restored = await provider.restore_goal(session_id, branch)
    if not restored:
        return False

    progress_raw = restored.get("progress_state")
    if isinstance(progress_raw, dict) and workspace_dir:
        try:
            write_todos_sync_to_workspace(workspace_dir, TodoStore.model_validate(progress_raw), session_id)
            logger.info("Branch switch perceived: restored goal and todos for branch %s", branch)
        except Exception as e:
            logger.error("Failed to restore todos for branch %s: %s", branch, e)
    return True


async def _update_kanban_branch(branch: str, last_branch: str | None, *, migrated: bool) -> None:
    try:
        from app.services.kanban.service import KanbanService

        await KanbanService.get_instance().update_active_tasks_branch_metadata(
            new_branch=branch,
            old_branch=last_branch,
            migrated=migrated,
        )
    except Exception as e:
        logger.warning("Kanban branch metadata update skipped: %s", e)


def _publish_branch_switched(
    session_id: str,
    branch: str,
    last_branch: str | None,
    *,
    restored: bool,
    migrated: bool,
) -> None:
    try:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.GOAL_BRANCH_SWITCHED,
                data={
                    "chat_id": session_id,
                    "branch": branch,
                    "stashed_branch": last_branch,
                    "restored": restored,
                    "migrated": migrated,
                },
            )
        )
    except Exception as e:
        logger.error("Failed to publish goal:branch_switched event: %s", e)


async def check_and_handle_branch_stash(session_id: str, workspace_dir: str | None = None) -> None:
    """Perceive a git branch change, then stash, migrate or restore the session's goal and todos."""
    branch = await get_current_git_branch(workspace_dir)
    if not branch:
        return

    from app.platform_utils import get_storage_provider

    provider = GoalRegistry.get_or_create_provider(session_id)
    storage = get_storage_provider()
    last_branch_key = f"{_LAST_BRANCH_PREFIX}/{session_id}"
    last_branch = await _read_last_branch(storage, last_branch_key)
    if last_branch == branch:
        return

    has_stash = await GoalStorage(storage).get_stash(session_id, branch) is not None
    migrated = False
    if last_branch:
        migrated = await _stash_or_migrate(
            provider,
            session_id,
            last_branch=last_branch,
            branch=branch,
            has_stash=has_stash,
            workspace_dir=workspace_dir,
        )

    await storage.write(key=last_branch_key, content=branch.encode("utf-8"))
    await _update_kanban_branch(branch, last_branch, migrated=migrated)

    restored = False if migrated else await _restore_branch_goal(provider, session_id, branch, workspace_dir)
    _publish_branch_switched(session_id, branch, last_branch, restored=restored, migrated=migrated)


async def _watch_branch_changes() -> None:
    """Stat `.git/HEAD` (no subprocess) and re-check every live session whenever its mtime moves."""
    last_mtime = 0.0
    git_head_path: str | None = None
    disabled = False

    while True:
        try:
            if disabled:
                await asyncio.sleep(_DISABLED_RETRY_SECONDS)
                git_head_path = None
                disabled = False
            else:
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)

            session_ids = GoalRegistry.session_ids()
            if not session_ids:
                continue

            # A sandbox serves one workspace, so the configured project dir is every session's workspace.
            from app.config.settings import settings

            workspace_dir = str(Path(settings.project_dir).expanduser().resolve())
            if not git_head_path:
                git_head_path = os.path.join(workspace_dir, ".git", "HEAD")
                if not os.path.exists(git_head_path):
                    logger.debug("Branch watcher: .git/HEAD not found at %s. Pausing watcher.", git_head_path)
                    git_head_path = None
                    disabled = True
                    continue

            try:
                current_mtime = os.stat(git_head_path).st_mtime
            except (FileNotFoundError, PermissionError):
                continue

            if current_mtime != last_mtime:
                last_mtime = current_mtime
                for sid in session_ids:
                    try:
                        await check_and_handle_branch_stash(sid, workspace_dir=workspace_dir)
                    except Exception as e:
                        logger.error("Branch watcher error for session %s: %s", sid, e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Branch watcher loop error: %s", e)


def start_branch_watcher() -> None:
    """Start the background loop that follows `.git/HEAD` for live goal sessions."""
    global _watcher_task
    if _watcher_task is not None and not _watcher_task.done():
        return
    _watcher_task = asyncio.create_task(_watch_branch_changes(), name="goal-branch-watcher")


def stop_branch_watcher() -> None:
    global _watcher_task
    task, _watcher_task = _watcher_task, None
    if task is not None:
        task.cancel()
