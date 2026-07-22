"""File revert & review API — undo AI file edits and review diffs."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import SnapshotStore
from myrm_agent_harness.agent.meta_tools.file_ops.revert_service import RevertService
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


class FileDiffItem(BaseModel):
    """Diff content for a single file: original vs current."""

    path: str
    operation: str
    original: str | None = None
    current: str | None = None
    is_binary: bool = False


async def _hydrate_session(session_id: str) -> None:
    from app.services.files.revert_hydrate import ensure_session_snapshots_hydrated

    await ensure_session_snapshots_hydrated(session_id)


@router.get("/changes/{session_id}")
async def get_session_changes(session_id: str) -> dict[str, list[FileChangeInfo]]:
    """Get all file changes for a session, grouped by message_id."""
    await _hydrate_session(session_id)
    changes = await RevertService.get_session_changes(session_id)
    return {
        msg_id: [
            FileChangeInfo(path=c.path, operation=c.operation, has_original=c.has_original, timestamp=c.timestamp)
            for c in file_changes
        ]
        for msg_id, file_changes in changes.items()
    }


@router.get("/changes/{session_id}/{message_id}")
async def get_message_changes(session_id: str, message_id: str) -> list[FileChangeInfo]:
    """Get file changes for a specific message."""
    await _hydrate_session(session_id)
    changes = await RevertService.get_message_changes(session_id, message_id)
    return [
        FileChangeInfo(path=c.path, operation=c.operation, has_original=c.has_original, timestamp=c.timestamp) for c in changes
    ]


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
        current_content: str | None = None
        is_binary = False

        file_path = Path(snap.path)
        if file_path.exists():
            try:
                current_content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                is_binary = True
            except OSError as e:
                logger.warning("Cannot read file %s for diff: %s", snap.path, e)

        diffs.append(
            FileDiffItem(
                path=snap.path,
                operation=snap.operation.value,
                original=snap.original_content,
                current=current_content,
                is_binary=is_binary,
            )
        )

    return diffs


@router.get("/diff/{session_id}")
async def get_session_diff(session_id: str) -> dict[str, list[FileDiffItem]]:
    """Get diff content for all file changes in a session, grouped by message_id."""
    await _hydrate_session(session_id)
    store = SnapshotStore.get()
    session_snaps = store.get_session_snapshots(session_id)

    result: dict[str, list[FileDiffItem]] = {}
    for msg_id, snapshots in session_snaps.items():
        diffs: list[FileDiffItem] = []
        for snap in snapshots:
            current_content: str | None = None
            is_binary = False

            file_path = Path(snap.path)
            if file_path.exists():
                try:
                    current_content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    is_binary = True
                except OSError:
                    pass

            diffs.append(
                FileDiffItem(
                    path=snap.path,
                    operation=snap.operation.value,
                    original=snap.original_content,
                    current=current_content,
                    is_binary=is_binary,
                )
            )
        result[msg_id] = diffs

    return result


@router.post("/message")
async def revert_message(req: RevertMessageRequest) -> RevertResponse:
    """Revert all file changes from a specific message."""
    from app.services.files.revert_hydrate import cleanup_persisted_snapshots

    await _hydrate_session(req.session_id)
    result = await RevertService.revert_message(req.session_id, req.message_id)
    if result.reverted_files:
        await cleanup_persisted_snapshots(req.session_id, req.message_id)
    return RevertResponse(
        success=len(result.reverted_files) > 0,
        reverted_files=result.reverted_files,
        warnings=result.warnings,
        skipped_files=result.skipped_files,
    )


@router.post("/session")
async def revert_session(req: RevertSessionRequest) -> RevertResponse:
    """Revert all file changes in an entire session (all messages)."""
    from app.services.files.revert_hydrate import cleanup_persisted_snapshots

    await _hydrate_session(req.session_id)
    result = await RevertService.revert_session(req.session_id)
    if result.reverted_files:
        await cleanup_persisted_snapshots(req.session_id)
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
