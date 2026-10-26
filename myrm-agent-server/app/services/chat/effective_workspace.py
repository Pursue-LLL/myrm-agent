"""[INPUT]
- app.database.dto::ChatDTO (POS: chat metadata transfer object)
- app.services.project.project_service::ProjectService (POS: project CRUD)
- app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: JIT sandbox bind)
- app.services.agent.params.workspace_resolve::default_chat_workspace_path (POS: pure JIT sandbox path)
- app.platform_utils.workspace_root::get_workspace_root (POS: process workspace root)

[OUTPUT]
- resolve_effective_chat_workspace: SSOT workspace path for Agent + UI
- find_chat_workspace_root: workspace root of a chat, None when it has none (callers that must not fall back)
- resolve_chat_workspace_root: SSOT workspace root the runs of a chat wrote to (vault, artifacts, snapshots)

[POS]
Single resolution order for chat workspace directories: project bind path,
then chat.workspace_dir, then optional JIT chat_{id} sandbox.
"""

from __future__ import annotations

from pathlib import Path

from app.database.dto import ChatDTO


async def resolve_effective_chat_workspace(
    chat: ChatDTO,
    *,
    jit_fallback: bool = True,
    persist_jit: bool = False,
) -> str | None:
    """Resolve the workspace directory Agent and UI should use for a chat."""
    project_id = getattr(chat, "project_id", None)
    if project_id:
        from app.services.project.project_service import ProjectService

        project = await ProjectService.get_project(project_id)
        if project and project.workspace_path:
            return project.workspace_path

    if chat.workspace_dir:
        return chat.workspace_dir

    if not jit_fallback:
        return None

    from app.services.agent.params.workspace_resolve import (
        resolve_default_chat_workspace_dir,
    )

    return await resolve_default_chat_workspace_dir(
        chat.id,
        persist_workspace=persist_jit,
    )


async def find_chat_workspace_root(chat_id: str) -> Path | None:
    """Workspace root the runs of ``chat_id`` work in, or None when the chat has no workspace to speak of.

    Read-only: unlike ``resolve_effective_chat_workspace(jit_fallback=True)`` it never creates a
    sandbox directory. A chat without a bound workspace answers with the pure JIT path its first run
    would create, so what lives there stays reachable. None means the id cannot name a workspace
    directory at all (path separators, ``..``) and the chat has none bound.
    """
    from app.services.agent.params.workspace_resolve import default_chat_workspace_path
    from app.services.chat.chat_service import ChatService

    chat = await ChatService.get_chat_metadata(chat_id)
    if chat is not None and (bound := await resolve_effective_chat_workspace(chat, jit_fallback=False)):
        return Path(bound)
    try:
        return default_chat_workspace_path(chat_id)
    except ValueError:
        return None


async def resolve_chat_workspace_root(chat_id: str | None) -> Path:
    """Workspace root the runs of ``chat_id`` wrote their vault objects and artifacts to.

    Without a chat id (artifacts that belong to no chat) or when the chat has no workspace the answer
    is the run-bound or process workspace root.
    """
    from app.platform_utils.workspace_root import get_workspace_root

    if chat_id and chat_id.strip() and (found := await find_chat_workspace_root(chat_id.strip())) is not None:
        return found
    return get_workspace_root()
