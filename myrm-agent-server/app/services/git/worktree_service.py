"""Git worktree domain service for multi-worktree orchestration, checkout anchoring, and touched files inspection.

[INPUT]
- repo_path: str | None (defaults to repo root of current process)
- branch, worktree_path, base_ref
- session_id, checkout_ref, touched_files

[OUTPUT]
- GitWorktreeInfo: Pydantic model of a single git worktree
- SessionCheckoutAnchorInfo: Pydantic model of session-to-worktree anchoring metadata
- SessionTouchedFileInfo: Pydantic model of touched file items in session
- GitWorktreeService / get_worktree_service(): Singleton accessor

[POS]
app/services/git/worktree_service.py: 核心 Git 多工作区与会话检出锚定服务，
被 app/api/git/worktree_router.py 调用。
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from app.core.utils.git_worktree import (
    _GIT_ENV,
    _classify_git_error,
    _ensure_worktree_excluded,
    _remove_worktree,
    _worktree_is_dirty,
)

logger = logging.getLogger(__name__)


class SessionTouchedFileInfo(BaseModel):
    """File touched/mutated during a session."""

    file_path: str = Field(..., description="Relative path within the worktree")
    change_type: str = Field(default="modified", description="created | modified | deleted | read")
    touched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionCheckoutAnchorInfo(BaseModel):
    """Anchor metadata linking a session to its checkout state at inception."""

    session_id: str
    project_root: str
    worktree_path: str
    checkout_ref: str
    is_anchored: bool = Field(default=True, description="True if currently active worktree matches session anchor")
    active_worktree_path: str = Field(default="")
    touched_files: list[SessionTouchedFileInfo] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GitWorktreeInfo(BaseModel):
    """Detailed metadata for a git worktree."""

    path: str
    branch: str = Field(default="", description="Branch name or HEAD if detached")
    head_commit: str = Field(default="")
    is_current: bool = Field(default=False)
    is_bare: bool = Field(default=False)
    is_dirty: bool = Field(default=False)
    is_locked: bool = Field(default=False)
    lock_reason: str | None = None


class GitWorktreeService:
    """Domain service managing worktree lifecycle, active switcher, and session anchoring."""

    _instance: ClassVar[GitWorktreeService | None] = None
    _active_worktree_override: dict[str, str] = {}
    _session_anchors: dict[str, SessionCheckoutAnchorInfo] = {}

    @classmethod
    def get_instance(cls) -> GitWorktreeService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _resolve_repo_root(self, repo_path: str | None = None) -> str:
        """Resolve top-level git repository root."""
        base = repo_path or os.getcwd()
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=base,
                capture_output=True,
                text=True,
                timeout=5,
                env=_GIT_ENV,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception as exc:
            logger.debug("Failed to resolve git rev-parse top-level: %s", exc)
        return str(Path(base).resolve())

    async def list_worktrees(self, repo_path: str | None = None) -> list[GitWorktreeInfo]:
        """List all worktrees for repository using `git worktree list --porcelain`."""
        root = self._resolve_repo_root(repo_path)
        try:
            res = await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "list", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
                env=_GIT_ENV,
            )
            if res.returncode != 0:
                logger.warning("git worktree list failed: %s", res.stderr.strip())
                return [
                    GitWorktreeInfo(
                        path=root,
                        branch="main",
                        head_commit="HEAD",
                        is_current=True,
                    )
                ]

            worktrees: list[GitWorktreeInfo] = []
            current_block: dict[str, str] = {}

            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    if "worktree" in current_block:
                        wt = await self._parse_block(current_block, root)
                        worktrees.append(wt)
                    current_block = {}
                    continue

                parts = line.split(" ", 1)
                key = parts[0]
                val = parts[1] if len(parts) > 1 else ""
                current_block[key] = val

            if "worktree" in current_block:
                wt = await self._parse_block(current_block, root)
                worktrees.append(wt)

            active_override = self._active_worktree_override.get(root)
            if active_override:
                for w in worktrees:
                    w.is_current = os.path.abspath(w.path) == os.path.abspath(active_override)

            return worktrees
        except Exception as exc:
            logger.error("Failed to list worktrees: %s", exc)
            return [GitWorktreeInfo(path=root, branch="main", head_commit="HEAD", is_current=True)]

    async def _parse_block(self, block: dict[str, str], root: str) -> GitWorktreeInfo:
        path = block.get("worktree", root)
        head = block.get("HEAD", "")
        branch_ref = block.get("branch", "")
        branch_name = branch_ref.replace("refs/heads/", "") if branch_ref else ("detached" if "detached" in block else "HEAD")
        is_bare = "bare" in block
        is_locked = "locked" in block
        lock_reason = block.get("locked") if is_locked else None

        is_curr = False
        active_ov = self._active_worktree_override.get(root)
        if active_ov:
            is_curr = os.path.abspath(path) == os.path.abspath(active_ov)
        else:
            is_curr = os.path.abspath(path) == os.path.abspath(root)

        dirty = await _worktree_is_dirty(path) if not is_bare and os.path.isdir(path) else False

        return GitWorktreeInfo(
            path=path,
            branch=branch_name,
            head_commit=head[:8] if head else "",
            is_current=is_curr,
            is_bare=is_bare,
            is_dirty=dirty,
            is_locked=is_locked,
            lock_reason=lock_reason,
        )

    async def create_worktree(
        self,
        branch: str,
        repo_path: str | None = None,
        worktree_path: str | None = None,
        base_ref: str | None = "HEAD",
    ) -> GitWorktreeInfo:
        """Create a new worktree under .worktrees/<branch> or custom target."""
        root = self._resolve_repo_root(repo_path)
        safe_branch = branch.strip().replace(" ", "-")
        target_path = worktree_path or os.path.join(root, ".worktrees", safe_branch)

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        _ensure_worktree_excluded(root, ".worktrees")

        cmd = ["git", "worktree", "add", "-B", safe_branch, target_path, base_ref or "HEAD"]
        res = await asyncio.to_thread(
            subprocess.run,
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            env=_GIT_ENV,
        )

        if res.returncode != 0:
            err = res.stderr.strip()
            reason = _classify_git_error(err)
            raise ValueError(f"Failed to create worktree: {reason.value} - {err[:200]}")

        self._active_worktree_override[root] = target_path
        return GitWorktreeInfo(
            path=target_path,
            branch=safe_branch,
            head_commit="HEAD",
            is_current=True,
            is_bare=False,
            is_dirty=False,
        )

    async def switch_worktree(self, worktree_path: str, repo_path: str | None = None) -> GitWorktreeInfo:
        """Switch active worktree pointer."""
        root = self._resolve_repo_root(repo_path)
        target = os.path.abspath(worktree_path)
        if not os.path.exists(target):
            raise FileNotFoundError(f"Worktree path does not exist: {target}")

        self._active_worktree_override[root] = target
        worktrees = await self.list_worktrees(root)
        matched = next((w for w in worktrees if os.path.abspath(w.path) == target), None)
        if matched:
            return matched
        return GitWorktreeInfo(path=target, branch="active", is_current=True)

    async def remove_worktree(self, worktree_path: str, repo_path: str | None = None, force: bool = False) -> bool:
        """Safely remove a git worktree."""
        root = self._resolve_repo_root(repo_path)
        target = os.path.abspath(worktree_path)

        if not force and await _worktree_is_dirty(target):
            raise RuntimeError("Worktree has uncommitted modifications; cannot remove without force=True.")

        ok = await _remove_worktree(root, target, context="worktree-switcher")
        if root in self._active_worktree_override and self._active_worktree_override[root] == target:
            self._active_worktree_override.pop(root, None)
        return ok

    def get_session_checkout_anchor(self, session_id: str, repo_path: str | None = None) -> SessionCheckoutAnchorInfo:
        """Get anchor metadata for a session, checking if currently in sync."""
        root = self._resolve_repo_root(repo_path)
        active_path = self._active_worktree_override.get(root, root)

        anchor = self._session_anchors.get(session_id)
        if not anchor:
            anchor = SessionCheckoutAnchorInfo(
                session_id=session_id,
                project_root=root,
                worktree_path=active_path,
                checkout_ref="HEAD",
                is_anchored=True,
                active_worktree_path=active_path,
                touched_files=[],
            )
            self._session_anchors[session_id] = anchor
            return anchor

        is_same = os.path.abspath(anchor.worktree_path) == os.path.abspath(active_path)
        return SessionCheckoutAnchorInfo(
            session_id=anchor.session_id,
            project_root=anchor.project_root,
            worktree_path=anchor.worktree_path,
            checkout_ref=anchor.checkout_ref,
            is_anchored=is_same,
            active_worktree_path=active_path,
            touched_files=anchor.touched_files,
            created_at=anchor.created_at,
        )

    def bind_session_checkout_anchor(
        self,
        session_id: str,
        checkout_ref: str,
        worktree_path: str,
        repo_path: str | None = None,
        touched_files: list[SessionTouchedFileInfo] | None = None,
    ) -> SessionCheckoutAnchorInfo:
        """Register or update session checkout anchor."""
        root = self._resolve_repo_root(repo_path)
        active_path = self._active_worktree_override.get(root, root)
        norm_wt = os.path.abspath(worktree_path)

        info = SessionCheckoutAnchorInfo(
            session_id=session_id,
            project_root=root,
            worktree_path=norm_wt,
            checkout_ref=checkout_ref,
            is_anchored=norm_wt == os.path.abspath(active_path),
            active_worktree_path=active_path,
            touched_files=touched_files or [],
        )
        self._session_anchors[session_id] = info
        return info


def get_worktree_service() -> GitWorktreeService:
    return GitWorktreeService.get_instance()
