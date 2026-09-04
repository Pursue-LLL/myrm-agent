"""[INPUT]
- app.config.settings::get_settings (POS: application settings SSOT)
- myrm_agent_harness.toolkits.code_execution::create_workspace_service (POS: sandbox workspace lifecycle)
- app.services.chat.chat_service::ChatService (POS: chat metadata persistence)
- app.services.agent.profile.profile_resolver::get_agent_profile_resolver (POS: agent profile SSOT resolver)

[OUTPUT]
- resolve_default_chat_workspace_dir(): JIT workspace path for a chat session
- _materialize_agent_template_files(): safely materialize agent's template workspace files into the sandbox

[POS]
Resolves or creates the harness workspace directory for a chat session and safely materializes
any bundled template workspace files declared on the bound agent profile.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def resolve_default_chat_workspace_dir(
    chat_id: str,
    *,
    persist_workspace: bool,
) -> str | None:
    try:
        from myrm_agent_harness.toolkits.code_execution import (
            create_workspace_service,
        )

        from app.config.settings import get_settings
        from app.services.chat.chat_service import ChatService

        session_id = f"chat_{chat_id}"
        workspace_svc = create_workspace_service(
            root_dir=Path(get_settings().database.harness_dir),
        )
        workspace = await workspace_svc.get_or_create(session_id=session_id)
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
    from app.services.plugins._agent_persist import materialize_template_workspace_files

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
        elif isinstance(profile.metadata, dict) and isinstance(profile.metadata.get("engine_params"), dict):
            engine_params = profile.metadata["engine_params"]

        if not engine_params:
            return

        template_files = engine_params.get("template_workspace_files")
        if isinstance(template_files, dict):
            materialize_template_workspace_files(template_files, workspace_dir)
    except Exception as exc:
        logger.warning("Failed to materialize template files for chat %s: %s", chat_id, exc)
