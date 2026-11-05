"""[INPUT]
- app.services.agent.params.models::AgentRequest (POS: Agent API request DTO)
- app.services.chat.chat_service::ChatService (POS: chat metadata loader)
- app.services.chat.effective_workspace (POS: project/chat workspace resolution)
- app.services.agent.session_access_service (POS: session access root bootstrap)
- app.services.agent.params.workspace_resolve (POS: default chat workspace resolution)
- app.services.memory.shared_context.shared_context (POS: shared knowledge-base contexts)

[OUTPUT]
- ChatContext: workspace, session access roots, persisted subagents/skills, shared memory contexts
- resolve_chat_context(): load the chat row and resolve everything conversation-scoped

[POS]
Conversation scope stage of Agent request conversion. Isolates the DB reads that describe the
chat (workspace, access roots, shared memory) from the pure request/config assembly around it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..models import AgentRequest

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChatContext:
    """Everything resolved from the persisted chat row."""

    project_id: str | None = None
    chat_workspace_dir: str | None = None
    session_access_roots_raw: list[dict[str, object]] | None = None
    session_loaded_skill_names: list[str] | None = None
    jit_subagents: dict[str, object] | None = None
    memory_shared_context_ids: list[str] = field(default_factory=list)
    memory_shared_context_names: dict[str, str] = field(default_factory=dict)


async def resolve_chat_context(request: AgentRequest) -> ChatContext:
    """Load the chat row and resolve workspace, access roots and shared memory contexts."""

    context = ChatContext(jit_subagents=request.ephemeral_subagents)
    chat_loaded = False
    db_had_workspace = False

    if request.chat_id:
        try:
            from app.services.chat.chat_service import ChatService

            chat = await ChatService.get_chat_metadata(request.chat_id)
            if chat:
                chat_loaded = True
                context.project_id = chat.project_id
                if context.jit_subagents is None and chat.ephemeral_subagents:
                    context.jit_subagents = chat.ephemeral_subagents
                if chat.session_loaded_skill_names:
                    context.session_loaded_skill_names = [str(name) for name in chat.session_loaded_skill_names if name]
                if chat.session_access_roots:
                    context.session_access_roots_raw = [
                        dict(item) for item in chat.session_access_roots if isinstance(item, dict)
                    ]

                from app.services.chat.effective_workspace import (
                    resolve_effective_chat_workspace,
                )

                resolved_workspace = await resolve_effective_chat_workspace(
                    chat,
                    jit_fallback=False,
                )
                if resolved_workspace:
                    context.chat_workspace_dir = resolved_workspace
                    db_had_workspace = True
        except Exception as e:
            logger.warning(f"Failed to load chat metadata for {request.chat_id}: {e}")

    # A first turn may carry the folder the viewer picked before the chat existed; the project
    # workspace (resolved above) and an existing chat workspace both take precedence over it.
    if not context.chat_workspace_dir and request.workspace_dir:
        context.chat_workspace_dir = request.workspace_dir

    if not context.chat_workspace_dir and request.chat_id:
        from app.services.agent.params.workspace_resolve import resolve_default_chat_workspace_dir

        context.chat_workspace_dir = await resolve_default_chat_workspace_dir(
            request.chat_id,
            persist_workspace=chat_loaded and not db_had_workspace,
        )

    if request.chat_id:
        from app.services.agent.session_access_service import (
            bootstrap_session_access_roots,
        )

        bootstrap_session_access_roots(
            context.session_access_roots_raw,
            workspace_dir=context.chat_workspace_dir,
        )

    try:
        from app.services.memory.shared_context.shared_context import (
            SharedContextService,
            resolve_shared_context_ids,
        )

        context.memory_shared_context_ids = await resolve_shared_context_ids(
            agent_id=request.agent_id,
            channel_id="web_chat",
            conversation_id=request.chat_id,
            task_id=None,
            project_id=context.project_id,
        )
        if request.session_knowledge_base_ids:
            for kb_id in request.session_knowledge_base_ids:
                if kb_id and kb_id not in context.memory_shared_context_ids:
                    context.memory_shared_context_ids.append(kb_id)

        if context.memory_shared_context_ids:
            from app.database.connection import get_session

            async with get_session() as session:
                context.memory_shared_context_names = await SharedContextService(session).get_context_names(
                    context.memory_shared_context_ids
                )
    except Exception as e:
        logger.warning("Failed to resolve shared memory contexts for agent request: %s", e)

    return context
