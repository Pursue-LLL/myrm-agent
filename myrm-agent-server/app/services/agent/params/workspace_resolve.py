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
        return chat_workspace_dir
    except Exception as exc:
        logger.warning(
            "Failed to resolve default sandbox workspace for chat %s: %s",
            chat_id,
            exc,
        )
        return None
