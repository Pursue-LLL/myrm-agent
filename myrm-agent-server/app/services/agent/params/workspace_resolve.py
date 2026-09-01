"""[INPUT]
- app.config.settings::get_settings (POS: application settings SSOT)
- myrm_agent_harness.toolkits.code_execution::create_workspace_service (POS: sandbox workspace lifecycle)
- app.services.chat.chat_service::ChatService (POS: chat metadata persistence)

[OUTPUT]
- resolve_default_chat_workspace_dir(): JIT workspace path for a chat session

[POS]
Resolves or creates the harness workspace directory for a chat when project/workspace
metadata is missing from the database.
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
    import base64

    from app.services.agent.profile.profile_resolver import get_agent_profile_resolver
    from app.services.chat.chat_service import ChatService

    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat or not chat.agent_id:
            return

        profile = await get_agent_profile_resolver().resolve(chat.agent_id)
        if not profile or not profile.engine_params:
            return

        template_files = profile.engine_params.get("template_workspace_files")
        if not isinstance(template_files, dict) or not template_files:
            return

        ws_path = Path(workspace_dir).resolve()
        for rel_path, content in template_files.items():
            if not isinstance(rel_path, str) or not rel_path:
                continue
            # Path traversal defense
            target_path = (ws_path / rel_path).resolve()
            if not str(target_path).startswith(str(ws_path)):
                logger.warning("Blocked path traversal in template workspace file: %s", rel_path)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            if not target_path.exists():
                if isinstance(content, str):
                    if content.startswith("base64:"):
                        raw_bytes = base64.b64decode(content[len("base64:") :])
                        target_path.write_bytes(raw_bytes)
                    else:
                        target_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to materialize template files for chat %s: %s", chat_id, exc)
