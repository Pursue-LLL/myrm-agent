"""File revert & review API — undo AI file edits and review diffs."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import SnapshotStore
from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import FileChange, RevertService
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)


class RevertMessageRequest(BaseModel):
    session_id: str
    message_id: str


class RevertSessionRequest(BaseModel):
    session_id: str


class RevertResponse(BaseModel):
    success: bool
    reverted_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)


class FileChangeInfo(BaseModel):
    path: str
    operation: str
    has_original: bool
    timestamp: float
    revertible: bool = True
    skip_reason: str | None = None


def _to_change_info(c: FileChange) -> FileChangeInfo:
    return FileChangeInfo(
        path=c.path,
        operation=c.operation,
        has_original=c.has_original,
        timestamp=c.timestamp,
        revertible=c.revertible,
        skip_reason=c.skip_reason,
    )


MAX_DIFF_CONTENT_BYTES = 512 * 1024


class FileDiffItem(BaseModel):
    """Diff content for a single file: original vs current."""

    path: str
    operation: str
    original: str | None = None
    current: str | None = None
    is_binary: bool = False
    truncated: bool = False
    additions: int = 0
    deletions: int = 0


def _diff_stats(original: str | None, current: str | None) -> tuple[int, int]:
    import difflib

    if not original and not current:
        return 0, 0
    additions = 0
    deletions = 0
    for line in difflib.unified_diff(
        (original or "").splitlines(),
        (current or "").splitlines(),
        lineterm="",
    ):
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _is_oversized(original: str | None, current: str | None, file_path: Path | None = None) -> bool:
    total = len((original or "").encode("utf-8", errors="ignore"))
    total += len((current or "").encode("utf-8", errors="ignore"))
    if total > MAX_DIFF_CONTENT_BYTES:
        return True
    try:
        if file_path is not None and file_path.exists() and file_path.is_file():
            if file_path.stat().st_size > MAX_DIFF_CONTENT_BYTES:
                return True
    except OSError:
        pass
    return False


async def _hydrate_session(session_id: str) -> None:
    from app.services.files.revert_hydrate import ensure_session_snapshots_hydrated

    await ensure_session_snapshots_hydrated(session_id)


def _snapshot_local_path(snap_path: str) -> Path:
    """Resolve a container-abstract snapshot path (``/workspace/...``) to the
    real local file inside the chat workspace, falling back to the path as-is."""
    from myrm_agent_harness.api import get_workspace_root
    from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
        WorkspacePathResolver,
    )

    if not WorkspacePathResolver.is_container_path(snap_path):
        return Path(snap_path)
    workspace_root = get_workspace_root()
    local = WorkspacePathResolver.to_local_path(snap_path, workspace_root or None)
    if local is None:
        return Path(snap_path)
    return local


@router.get("/changes/{session_id}")
async def get_session_changes(session_id: str) -> dict[str, list[FileChangeInfo]]:
    """Get all file changes for a session, grouped by message_id."""
    await _hydrate_session(session_id)
    changes = await RevertService.get_session_changes(session_id)
    return {msg_id: [_to_change_info(c) for c in file_changes] for msg_id, file_changes in changes.items()}


@router.get("/changes/{session_id}/{message_id}")
async def get_message_changes(session_id: str, message_id: str) -> list[FileChangeInfo]:
    """Get file changes for a specific message."""
    await _hydrate_session(session_id)
    changes = await RevertService.get_message_changes(session_id, message_id)
    return [_to_change_info(c) for c in changes]


@router.get("/diff/{session_id}/{message_id}")
async def get_message_diff(session_id: str, message_id: str) -> list[FileDiffItem]:
    """Get diff content for all file changes in a message (for Review UI).

    Returns original content (from snapshot) and current content (from disk)
    for each modified file.
    """
    await _hydrate_session(session_id)
    store = SnapshotStore.get()
    snapshots = store.get_message_snapshots(session_id, message_id)

    diffs: list[FileDiffItem] = []
    for snap in snapshots:
        diffs.append(_build_diff_item(snap.path, snap.operation.value, snap.original_content))

    return diffs


def _read_current_safe(file_path: Path) -> tuple[str | None, bool]:
    try:
        if file_path.exists() and file_path.is_file():
            try:
                if file_path.stat().st_size > MAX_DIFF_CONTENT_BYTES:
                    return None, False
            except OSError:
                pass
            return file_path.read_text(encoding="utf-8"), False
    except UnicodeDecodeError:
        return None, True
    except OSError as e:
        logger.warning("Cannot read file for diff: %s", e)
    return None, False


def _build_diff_item(path: str, operation: str, original: str | None) -> FileDiffItem:
    file_path = _snapshot_local_path(path)
    current_content, is_binary = _read_current_safe(file_path) if file_path.exists() else (None, False)
    if is_binary:
        return FileDiffItem(path=path, operation=operation, original=None, current=None, is_binary=True)
    if _is_oversized(original, current_content, file_path):
        return FileDiffItem(
            path=path,
            operation=operation,
            original=None,
            current=None,
            is_binary=False,
            truncated=True,
            additions=0,
            deletions=0,
        )
    additions, deletions = _diff_stats(original, current_content)
    return FileDiffItem(
        path=path,
        operation=operation,
        original=original,
        current=current_content,
        is_binary=False,
        truncated=False,
        additions=additions,
        deletions=deletions,
    )


@router.get("/diff/{session_id}")
async def get_session_diff(session_id: str) -> dict[str, list[FileDiffItem]]:
    """Get diff content for all file changes in a session, grouped by message_id."""
    await _hydrate_session(session_id)
    store = SnapshotStore.get()
    session_snaps = store.get_session_snapshots(session_id)

    result: dict[str, list[FileDiffItem]] = {}
    for msg_id, snapshots in session_snaps.items():
        result[msg_id] = [
            _build_diff_item(snap.path, snap.operation.value, snap.original_content) for snap in snapshots
        ]

    return result


@router.post("/message")
async def revert_message(req: RevertMessageRequest) -> RevertResponse:
    """Revert all file changes from a specific message."""
    from app.services.files.revert_agent_notify import notify_agent_of_turn_revert
    from app.services.files.revert_hydrate import cleanup_persisted_snapshots

    await _hydrate_session(req.session_id)
    result = await RevertService.revert_message(req.session_id, req.message_id)
    if result.reverted_files:
        await cleanup_persisted_snapshots(req.session_id, req.message_id)
        notify_agent_of_turn_revert(
            session_id=req.session_id,
            message_id=req.message_id,
            reverted_files=result.reverted_files,
        )
    return RevertResponse(
        success=len(result.reverted_files) > 0,
        reverted_files=result.reverted_files,
        warnings=result.warnings,
        skipped_files=result.skipped_files,
    )


@router.post("/session")
async def revert_session(req: RevertSessionRequest) -> RevertResponse:
    """Revert all file changes in an entire session (all messages)."""
    from app.services.files.revert_agent_notify import notify_agent_of_turn_revert
    from app.services.files.revert_hydrate import cleanup_persisted_snapshots

    await _hydrate_session(req.session_id)
    result = await RevertService.revert_session(req.session_id)
    if result.reverted_files:
        await cleanup_persisted_snapshots(req.session_id)
        notify_agent_of_turn_revert(
            session_id=req.session_id,
            message_id=None,
            reverted_files=result.reverted_files,
        )
    return RevertResponse(
        success=len(result.reverted_files) > 0,
        reverted_files=result.reverted_files,
        warnings=result.warnings,
        skipped_files=result.skipped_files,
    )


@router.get("/stats")
async def get_snapshot_stats() -> dict[str, int]:
    """Get snapshot store statistics."""
    store = SnapshotStore.get()
    return {"total_bytes": store.total_bytes}
