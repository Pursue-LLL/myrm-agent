"""Apply post-migration workspace bind to chat before agent param conversion.

[INPUT]
- app.services.agent.params::AgentRequest (POS: migration_bound_project_id field)
- app.services.project.project_service::ProjectService (POS: chat.project_id SSOT)

[OUTPUT]
- apply_migration_bound_project: one-shot bind when chat has no project yet

[POS]
Mirrors migration_readiness_anchor timing: after user message persist, before convert.
Does not alter Harness prompts or tool registration.
"""

from __future__ import annotations

import logging

from app.services.agent.params import AgentRequest

logger = logging.getLogger(__name__)


async def apply_migration_bound_project(request: AgentRequest) -> None:
    """Attach migration-bound project to chat before workspace resolution."""
    if request.resume_value is not None:
        return

    bound_project_id = (request.migration_bound_project_id or "").strip()
    chat_id = (request.chat_id or "").strip()
    if not bound_project_id or not chat_id:
        return

    from app.services.chat.chat_service import ChatService
    from app.services.project.project_service import ProjectService

    chat = await ChatService.get_chat_metadata(chat_id)
    if chat is not None and chat.project_id:
        return

    moved = await ProjectService.move_chat_to_project(chat_id, bound_project_id)
    if not moved:
        logger.warning(
            "Migration bound project handoff failed: chat_id=%s project_id=%s",
            chat_id,
            bound_project_id,
        )
