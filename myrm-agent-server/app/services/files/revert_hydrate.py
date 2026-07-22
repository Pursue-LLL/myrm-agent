"""Hydrate in-memory SnapshotStore from on-disk snapshots for revert flows.

[INPUT]
- myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer::SnapshotStore (POS: File snapshot observer)
- myrm_agent_harness.toolkits.code_execution.utils.workspace_path::WorkspacePathResolver (POS: Workspace path resolver with intelligent auto-detection.)
- app.services.chat.chat_service::ChatService (POS: chat metadata persistence)
- app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: JIT workspace path)

[OUTPUT]
- ensure_session_snapshots_hydrated: load disk snapshots into the current request context
- cleanup_persisted_snapshots: delete on-disk snapshot files after revert

[POS]
Server-side revert snapshot disk hydrate and cleanup. Shared by revert HTTP API and channel /undo.
Keeps harness RevertService free of business-layer imports.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    SnapshotStore,
)

logger = logging.getLogger(__name__)


async def _resolve_snapshot_search_roots(session_id: str) -> list[Path]:
    roots: list[Path] = []

    workspace_env = os.getenv("WORKSPACE_ROOT")
    if workspace_env:
        roots.append(Path(workspace_env))

    try:
        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
            WorkspacePathResolver,
        )

        roots.append(WorkspacePathResolver.resolve_workspace_root())
    except Exception:
        logger.debug(
            "Could not resolve harness workspace root for session=%s",
            session_id,
            exc_info=True,
        )

    try:
        from app.services.chat.chat_service import ChatService

        chat = await ChatService.get_chat_by_id(session_id)
        if chat and chat.workspace_dir:
            roots.append(Path(chat.workspace_dir))
    except Exception:
        pass

    try:
        from app.services.agent.params.workspace_resolve import (
            resolve_default_chat_workspace_dir,
        )

        workspace_dir = await resolve_default_chat_workspace_dir(
            session_id, persist_workspace=False
        )
        if workspace_dir:
            roots.append(Path(workspace_dir))
    except Exception:
        logger.debug(
            "Could not resolve default workspace for session=%s",
            session_id,
            exc_info=True,
        )

    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


async def ensure_session_snapshots_hydrated(session_id: str) -> None:
    """Load disk snapshots into the current context when memory is empty."""
    store = SnapshotStore.get()
    if store.get_session_snapshots(session_id):
        return

    for root in await _resolve_snapshot_search_roots(session_id):
        if await store.merge_session_from_disk(str(root), session_id):
            return


async def cleanup_persisted_snapshots(
    session_id: str, message_id: str | None = None
) -> None:
    """Remove on-disk snapshot files from all known workspace roots."""
    store = SnapshotStore.get()
    for root in await _resolve_snapshot_search_roots(session_id):
        if message_id:
            await store.remove_persisted_message(str(root), session_id, message_id)
        else:
            await store.clear_persisted_session(str(root), session_id)
