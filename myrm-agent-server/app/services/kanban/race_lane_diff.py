"""Kanban race lane diff review: file changes and side-by-side file contents.

[INPUT]
- app.services.kanban.race_orchestrator (POS: RaceError, _get_race_parent)
- myrm_agent_harness.toolkits.kanban.types (POS: KanbanTask domain type)
- app.core.utils.git_worktree (POS: _GIT_ENV for safe git subprocess env)

[OUTPUT]
- LaneFileChange: dataclass — one file changed by a lane, with line counts
- get_lane_changes: lists files changed by a lane against the race target branch
- get_lane_file_contents: target vs lane file contents for side-by-side review

[POS]
Business-layer race diff review. Pure git-diff read-only inspection of what
each lane changed relative to the race target branch, served to the review
board UI. Deliberately adds no harness machinery: read-only `git diff`/`git
show` against the lane worktree base dir, with path-safety and size guards.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.core.utils.git_worktree import _GIT_ENV
from app.services.kanban.race_orchestrator import RaceError, _get_race_parent

if TYPE_CHECKING:
    from app.services.kanban.service import KanbanService

logger = logging.getLogger(__name__)

MAX_DIFF_FILES = 100
MAX_FILE_BYTES = 200_000


@dataclass(frozen=True)
class LaneFileChange:
    """One file changed by a lane, with line counts."""

    path: str
    additions: int
    deletions: int

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "additions": self.additions, "deletions": self.deletions}


def _is_safe_repo_path(path: str) -> bool:
    """Reject traversal/absolute paths; only in-repo relative files are served."""
    if not path or path.startswith("/") or ".." in path.split("/"):
        return False
    return True


async def _run_git(
    base_dir: str, args: list[str], timeout: int = 15
) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(
        subprocess.run,
        ["git", *args],
        cwd=base_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_GIT_ENV,
    )


async def _get_lane_context(
    svc: KanbanService, board_id: str, parent_task_id: str, lane_task_id: str
) -> tuple[KanbanTask, KanbanTask, str, str]:
    """Return (parent, lane, base_dir, lane_branch) or raise RaceError."""
    from app.services.kanban.task_runner.worktree.lifecycle import (
        _worktree_branch_name,
        resolve_base_dir,
    )

    parent = await _get_race_parent(svc, parent_task_id)
    if parent.board_id != board_id:
        raise RaceError("wrong_board", "Parent task is not on this board")
    lane = await svc.get_task(lane_task_id)
    if lane is None or lane.metadata.get("race_parent") != parent.task_id:
        raise RaceError("not_a_lane", "Not a lane of this race")
    if not lane.branch:
        raise RaceError("lane_has_no_branch", "Lane has no git branch")
    base_dir = await resolve_base_dir(svc.store, lane)
    if not base_dir:
        raise RaceError("no_workdir", "Board has no working directory")
    return parent, lane, base_dir, _worktree_branch_name(lane.branch, lane.task_id)


async def get_lane_changes(
    svc: KanbanService, board_id: str, parent_task_id: str, lane_task_id: str
) -> dict[str, Any]:
    """List files changed by a lane against the race target branch."""
    parent, lane, base_dir, lane_branch = await _get_lane_context(
        svc, board_id, parent_task_id, lane_task_id
    )
    target = parent.branch or lane.branch
    if not target:
        raise RaceError("race_requires_branch", "Race target branch is missing")
    result = await _run_git(
        base_dir, ["diff", "--numstat", f"{target}...{lane_branch}", "--"]
    )
    if result.returncode != 0:
        raise RaceError("diff_failed", "All file differences were not computed")
    changes: list[LaneFileChange] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not _is_safe_repo_path(parts[2]):
            continue
        try:
            additions = int(parts[0]) if parts[0] != "-" else 0
            deletions = int(parts[1]) if parts[1] != "-" else 0
        except ValueError:
            continue
        changes.append(
            LaneFileChange(path=parts[2], additions=additions, deletions=deletions)
        )
        if len(changes) >= MAX_DIFF_FILES:
            break
    return {
        "lane_task_id": lane.task_id,
        "target_branch": target,
        "lane_branch": lane_branch,
        "truncated": len(changes) >= MAX_DIFF_FILES,
        "files": [c.to_dict() for c in changes],
    }


async def get_lane_file_contents(
    svc: KanbanService,
    board_id: str,
    parent_task_id: str,
    lane_task_id: str,
    path: str,
) -> dict[str, Any]:
    """Return target vs lane file contents for side-by-side review."""
    if not _is_safe_repo_path(path):
        raise RaceError("unsafe_path", "Only in-repo relative file paths are allowed")
    parent, lane, base_dir, lane_branch = await _get_lane_context(
        svc, board_id, parent_task_id, lane_task_id
    )
    target = parent.branch or lane.branch
    if not target:
        raise RaceError("race_requires_branch", "Race target branch is missing")

    async def show(ref: str) -> tuple[str, bool]:
        result = await _run_git(base_dir, ["show", f"{ref}:{path}"])
        if result.returncode != 0:
            return "", False
        content = result.stdout
        if "\x00" in content:
            return "", True
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            return content[:MAX_FILE_BYTES], True
        return content, False

    target_content, target_binary = await show(target)
    lane_content, lane_binary = await show(lane_branch)
    return {
        "lane_task_id": lane.task_id,
        "path": path,
        "target_content": target_content,
        "lane_content": lane_content,
        "truncated": target_binary or lane_binary,
    }