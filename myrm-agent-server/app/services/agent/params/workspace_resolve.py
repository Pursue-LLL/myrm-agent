"""[INPUT]
- app.config.settings::get_settings (POS: application settings SSOT)
- myrm_agent_harness.toolkits.code_execution::create_workspace_service (POS: sandbox workspace lifecycle)
- myrm_agent_harness.toolkits.code_execution.security::validate_path_component (POS: path-component whitelist)
- app.services.chat.chat_service::ChatService (POS: chat metadata persistence)
- app.services.agent.profile.profile_resolver::get_agent_profile_resolver (POS: agent profile SSOT resolver)

[OUTPUT]
- default_workspaces_root(): directory holding every JIT chat workspace (pure)
- default_chat_workspace_path(): where a chat's JIT workspace lives, without creating it (pure; rejects ids that cannot name a directory)
- resolve_default_chat_workspace_dir(): JIT workspace path for a chat session
- _materialize_agent_template_files(): safely materialize agent's template workspace files into the sandbox

[POS]
Resolves or creates the harness workspace directory for a chat session and safely materializes
any bundled template workspace files declared on the bound agent profile.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution import WorkspaceService

logger = logging.getLogger(__name__)


def _chat_workspace_service() -> WorkspaceService:
    """Workspace service rooted at the harness directory, shared by every JIT chat workspace."""
    from myrm_agent_harness.toolkits.code_execution import create_workspace_service

    from app.config.settings import get_settings

    return create_workspace_service(root_dir=Path(get_settings().database.harness_dir))


def _chat_session_id(chat_id: str) -> str:
    return f"chat_{chat_id}"


def default_workspaces_root() -> Path:
    """Directory that holds every JIT chat workspace."""
    return _chat_workspace_service().workspaces_root


def default_chat_workspace_path(chat_id: str) -> Path:
    """Where a chat's JIT workspace lives. Pure: nothing is created on disk.

    Equals the directory ``resolve_default_chat_workspace_dir`` creates, so a file written here
    before the chat's first turn is already inside the workspace the agent later runs in.

    Raises:
        ValueError: ``chat_id`` cannot name a workspace directory (path separators, ``..``, ...).
    """
    from myrm_agent_harness.toolkits.code_execution.security import validate_path_component

    session_id = _chat_session_id(chat_id)
    validation = validate_path_component(session_id, "chat workspace id")
    if not validation.is_safe:
        raise ValueError(validation.reason)
    return default_workspaces_root() / session_id


async def materialize_default_chat_workspace_dir(chat_id: str) -> str | None:
    """Ensure the physical sandbox directory and bundled templates exist on disk."""
    return await resolve_default_chat_workspace_dir(chat_id, persist_workspace=True)


async def resolve_default_chat_workspace_dir(
    chat_id: str,
    *,
    persist_workspace: bool,
) -> str | None:
    try:
        from app.services.chat.chat_service import ChatService

        workspace_svc = _chat_workspace_service()
        workspace = await workspace_svc.get_or_create(session_id=_chat_session_id(chat_id))
        chat_workspace_dir = workspace_svc.get_workspace_absolute_path(workspace)
        if persist_workspace:
            await ChatService.update_chat_fields(chat_id, {"workspace_dir": chat_workspace_dir})
        if chat_workspace_dir:
            await _materialize_agent_template_files(chat_id, chat_workspace_dir)
        return chat_workspace_dir
    except Exception as exc:
        logger.warning(
            "Failed to resolve default sandbox workspace for chat %s: %s",
            chat_id,
            exc,
        )
        return None


async def _materialize_agent_template_files(chat_id: str, workspace_dir: str) -> None:
    """Materialize agent's bundled template_workspace_files safely into the session workspace."""
    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver
    from app.services.chat.chat_service import ChatService
    from app.services.plugins.template_workspace import TEMPLATE_FILES_KEY, materialize_template_workspace_files

    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat or not chat.agent_id:
            return

        profile = await get_agent_profile_resolver().resolve(chat.agent_id)
        if not profile:
            return

        engine_params: dict[str, object] | None = None
        if hasattr(profile, "engine_params") and isinstance(profile.engine_params, dict):
            engine_params = profile.engine_params
        elif hasattr(profile, "metadata") and isinstance(profile.metadata, dict):
            raw_engine = profile.metadata.get("engine_params")
            if isinstance(raw_engine, dict):
                engine_params = raw_engine

        if not engine_params:
            return

        template_files = engine_params.get(TEMPLATE_FILES_KEY)
        if isinstance(template_files, dict):
            materialize_template_workspace_files(template_files, workspace_dir)
    except Exception as exc:
        logger.warning("Failed to materialize template files for chat %s: %s", chat_id, exc)
