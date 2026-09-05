"""Salient Tool Output Archive Service.

[INPUT]
- myrm_agent_harness.api::extract_salient_tool_evidences, SalientToolEvidence
- app.services.chat.conversation_recall_index_service::ConversationRecallIndexService
- sqlalchemy.ext.asyncio::AsyncSession

[OUTPUT]
- SalientToolArchiveService: Coordinates verbatim tool error & execution evidence archival into recall index

[POS]
Server business service for pre-compaction tool output preservation. Extracts high-value tool outputs
(failures, pytest reports, exit codes) and persists them into conversation recall segments before
context compaction erases them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Sequence

from myrm_agent_harness.api import (
    SalientToolEvidence,
    SalientToolFilterConfig,
    extract_salient_tool_evidences,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat.conversation_recall_index_service import (
    ConversationRecallIndexService,
)

logger = logging.getLogger(__name__)


class SalientToolArchiveService:
    """Extracts and archives salient verbatim tool outputs into the conversation recall index."""

    def __init__(self, config: SalientToolFilterConfig | None = None) -> None:
        self._config = config or SalientToolFilterConfig()

    async def archive_salient_tools(
        self,
        db: AsyncSession,
        *,
        chat_id: str,
        messages: Sequence[object],
    ) -> list[SalientToolEvidence]:
        """Extract salient tool outputs from message sequence and persist verbatim segments.

        Args:
            db: Async database session
            chat_id: Conversation session identifier
            messages: List of messages (Message ORM, MessageDTO, or LangChain messages)

        Returns:
            List of archived SalientToolEvidence records
        """
        evidences = extract_salient_tool_evidences(messages, config=self._config)
        if not evidences:
            return []

        archived: list[SalientToolEvidence] = []
        now = datetime.now(timezone.utc)

        for ev in evidences:
            # Map tool call id or generate bounded fallback message key
            msg_id = ev.tool_call_id
            if not msg_id:
                # Resolve underlying message id if available on the object
                msg_id = getattr(ev, "id", None) or f"tool_{abs(hash(ev.snippet[:50]))}"

            try:
                await ConversationRecallIndexService.append_salient_tool_evidence(
                    db,
                    chat_id=chat_id,
                    message_id=str(msg_id),
                    tool_name=ev.tool_name,
                    command=ev.command,
                    exit_code=ev.exit_code,
                    snippet=ev.snippet,
                    sent_at=now,
                )
                archived.append(ev)
            except Exception as exc:
                logger.warning(
                    "Failed to archive salient tool segment (non-blocking): chat_id=%s tool=%s err=%s",
                    chat_id,
                    ev.tool_name,
                    exc,
                )

        if archived:
            logger.info(
                "Archived %d verbatim salient tool execution segments for chat %s",
                len(archived),
                chat_id,
            )

        return archived
