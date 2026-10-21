"""[INPUT]
- app.database.dto::ChatDTO (POS: chat metadata transfer object)
- app.services.project.project_service::ProjectService (POS: project CRUD)
- app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: JIT sandbox bind)

[OUTPUT]
- resolve_effective_chat_workspace: SSOT workspace path for Agent + UI

[POS]
Single resolution order for chat workspace directories: project bind path,
then chat.workspace_dir, then optional JIT chat_{id} sandbox.
"""

from __future__ import annotations

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
