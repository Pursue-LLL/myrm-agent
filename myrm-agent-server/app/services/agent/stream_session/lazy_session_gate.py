"""Lazy Session Persistence Gate for Agent Stream.

Defers database persistence and sandbox materialization for new sessions until
the model emits the first active generation event (text token, reasoning chain,
or tool call), preventing orphan empty sessions and zero-byte directory pollution.

[INPUT]
- stream chunks (str | dict): inspected by is_active_generation_chunk
- AgentStreamSession: committed once by commit_lazy_session_barrier

[OUTPUT]
- is_active_generation_chunk(): True when a chunk represents authentic model activity
- PendingSessionDraft: in-memory draft held until the commit barrier
- commit_lazy_session_barrier(): persists the draft session exactly once

[POS]
Stream-session persistence gate: no session row or sandbox directory exists
until the first active generation event; empty sessions never materialize.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.stream_session.stream_session_types import (
        AgentStreamSession,
    )

logger = logging.getLogger(__name__)

# Events that represent authentic model activity requiring session persistence.
_ACTIVE_GENERATION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "message",
        "reasoning",
        "tool_call",
        "action",
        "clarification_required",
        "approval_intercepted",
    }
)


def is_active_generation_chunk(chunk: str | dict[str, object]) -> bool:
    """Return True if chunk represents authentic model generation activity.

    Status, routing decisions, warnings, and pre-stream telemetry do not count
    as generation activity; they must not trigger early persistence.
    """
    if isinstance(chunk, str):
        return bool(chunk.strip())
    if not isinstance(chunk, dict):
        return False

    event_type = chunk.get("type")
    if not isinstance(event_type, str) or event_type not in _ACTIVE_GENERATION_EVENT_TYPES:
        return False

    # For message and reasoning events, ensure payload actually contains visible content
    if event_type in ("message", "reasoning"):
        data = chunk.get("data")
        if isinstance(data, str):
            return bool(data.strip())
        if isinstance(data, dict):
            content = data.get("content") or data.get("text")
            return bool(isinstance(content, str) and content.strip())
        return False

    return True


@dataclass
class PendingSessionDraft:
    """In-memory draft for a new session prior to first assistant output."""

    chat_id: str
    user_content: str
    sent_at: datetime
    sent_timezone: str
    message_id: str | None
    action_mode: str
    agent_id: str
    ephemeral_subagents: dict[str, object] | None = None
    extra_data: dict[str, object] | None = None
    is_incognito: bool = False
    active_moa_preset_id: str | None = None
    persist_moa_preset: bool = False
    committed: bool = field(default=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def commit_if_pending(self) -> None:
        """Atomically persist chat row and initial user message into the database."""
        if self.committed:
            return
        async with self._lock:
            if self.committed:
                return
            self.committed = True

            from app.services.chat.chat_service import ChatService

            logger.info(
                "Committing lazy session to DB: chat_id=%s message_id=%s",
                self.chat_id,
                self.message_id,
            )
            await ChatService.ensure_chat_and_append_user_message(
                chat_id=self.chat_id,
                content=self.user_content,
                sent_at=self.sent_at,
                sent_timezone=self.sent_timezone,
                message_id=self.message_id,
                action_mode=self.action_mode,
                agent_id=self.agent_id,
                ephemeral_subagents=self.ephemeral_subagents,
                extra_data=self.extra_data,
                is_incognito=self.is_incognito,
                active_moa_preset_id=self.active_moa_preset_id,
                persist_moa_preset=self.persist_moa_preset,
            )


async def commit_lazy_session_barrier(session: AgentStreamSession) -> None:
    """Commit pending draft and lazily materialize sandbox workspace if uncommitted."""
    draft = getattr(session, "pending_session_draft", None)
    if draft is None or getattr(draft, "committed", True):
        return

    await draft.commit_if_pending()

    # Lazily materialize sandbox workspace directory now that session is committed
    if session.request.chat_id:
        try:
            from app.services.agent.params.workspace_resolve import (
                materialize_default_chat_workspace_dir,
            )

            await materialize_default_chat_workspace_dir(session.request.chat_id)
        except Exception as exc:
            logger.warning(
                "Lazy workspace materialization skipped for %s: %s",
                session.request.chat_id,
                exc,
            )
