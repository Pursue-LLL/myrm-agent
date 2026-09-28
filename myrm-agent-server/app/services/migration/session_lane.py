"""Session migration lane service.

[INPUT]
- app.database.models::Chat, Message (POS: 聊天会话与消息核心实体)
- myrm_agent_harness.runtime.context.transcripts::(
    CanonicalTranscriptTurn,
    CanonicalTurnRole,
    CanonicalToolCall,
    TranscriptParseResult,
) (POS: 框架层无状态转录本标准化数据结构)

[OUTPUT]
- SessionMigrationPreviewItem: DTO for wizard/dry-run review display
- SessionImportResult: Result containing created chat IDs and statistics
- SessionMigrationService: Orchestrates session conversion and DB persistence

[POS]
app/services/migration/session_lane.py
Transforms external assistant transcripts (Claude Code, Codex, etc.) into native
Chat and Message entities, preserving sandbox paths and prompt cache affinity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from myrm_agent_harness.runtime.context.transcripts import (
    CanonicalTranscriptTurn,
    CanonicalTurnRole,
    TranscriptParseResult,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionMigrationPreviewItem:
    """Preview metadata for an external session awaiting migration."""

    session_id: str
    title: str
    turn_count: int
    tool_call_count: int
    source_platform: str
    workspace_hint: str | None
    created_at_iso: str

    def to_dict(self) -> dict[str, object]:
        """Convert DTO to dictionary representation."""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "turn_count": self.turn_count,
            "tool_call_count": self.tool_call_count,
            "source_platform": self.source_platform,
            "workspace_hint": self.workspace_hint,
            "created_at_iso": self.created_at_iso,
        }


@dataclass(frozen=True)
class SessionImportResult:
    """Outcome of persisting external sessions into database."""

    imported_count: int
    created_chat_ids: list[str] = field(default_factory=list)
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


class SessionMigrationService:
    """Service for migrating external conversation sessions into native chats."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def build_preview(parsed_sessions: list[TranscriptParseResult]) -> list[SessionMigrationPreviewItem]:
        """Convert parsed transcript results into content-safe preview DTOs."""
        items: list[SessionMigrationPreviewItem] = []
        for s in parsed_sessions:
            created_iso = ""
            if s.created_at > 0:
                try:
                    created_iso = datetime.fromtimestamp(s.created_at, tz=UTC).isoformat()
                except Exception:
                    created_iso = ""
            items.append(
                SessionMigrationPreviewItem(
                    session_id=s.session_id,
                    title=s.title,
                    turn_count=len(s.turns),
                    tool_call_count=s.total_tool_calls,
                    source_platform=s.source_platform,
                    workspace_hint=s.detected_workspace_hint,
                    created_at_iso=created_iso,
                )
            )
        return items

    async def confirm_sessions(
        self,
        sessions: list[TranscriptParseResult | dict[str, object]],
        target_workspace_override: str | None = None,
        target_agent_id: str | None = None,
    ) -> SessionImportResult:
        """Persist parsed session transcripts into chats and messages tables.

        Strict Prompt Cache Affinity:
        - Never injects dynamic timestamps or random nonces into historical messages.
        - Preserves turn text purity so resumption turns achieve 100% prompt cache hits.
        """
        created_ids: list[str] = []
        errors: list[str] = []

        for raw_item in sessions:
            try:
                item = self._coerce_parse_result(raw_item)
                if not item.turns:
                    continue

                chat_id = f"chat_{item.source_platform}_{item.session_id}"
                if len(chat_id) > 200:
                    chat_id = f"chat_{uuid4().hex}"

                workspace_dir = target_workspace_override or item.detected_workspace_hint or "/workspace"

                first_msg_text: str | None = None
                last_msg_text: str | None = None
                for t in item.turns:
                    if t.role == CanonicalTurnRole.USER and first_msg_text is None:
                        first_msg_text = t.content
                    last_msg_text = t.content

                now_utc = datetime.now(tz=UTC)
                if item.created_at > 0:
                    raw_created = datetime.fromtimestamp(item.created_at, tz=UTC)
                    created_dt = min(raw_created, now_utc)
                else:
                    created_dt = now_utc

                if item.updated_at > 0:
                    raw_updated = datetime.fromtimestamp(item.updated_at, tz=UTC)
                    updated_dt = min(raw_updated, now_utc)
                else:
                    updated_dt = created_dt

                db_chat = Chat(
                    id=chat_id,
                    agent_id=target_agent_id,
                    title=item.title,
                    first_message=first_msg_text,
                    last_message=last_msg_text,
                    action_mode="fast",
                    source=item.source_platform,
                    workspace_dir=workspace_dir,
                    total_calls=item.total_tool_calls,
                    created_at=created_dt,
                    updated_at=updated_dt,
                )
                self._db.add(db_chat)

                for turn_idx, turn in enumerate(item.turns):
                    msg_id = f"msg_{chat_id[:32]}_{turn_idx}_{uuid4().hex[:8]}"
                    if turn.timestamp > 0:
                        raw_sent = datetime.fromtimestamp(turn.timestamp, tz=UTC)
                        sent_dt = min(raw_sent, now_utc)
                    else:
                        sent_dt = created_dt

                    extra_data: dict[str, object] = {
                        "turn_id": turn.turn_id,
                        "source_event_type": turn.source_event_type,
                    }
                    if turn.thinking_trace:
                        extra_data["thinking_trace"] = turn.thinking_trace
                    if turn.tool_calls:
                        extra_data["tool_calls"] = [
                            {
                                "call_id": tc.call_id,
                                "tool_name": tc.tool_name,
                                "arguments": tc.arguments,
                                "output": tc.output,
                                "exit_code": tc.exit_code,
                                "is_error": tc.is_error,
                                "compacted": tc.compacted,
                            }
                            for tc in turn.tool_calls
                        ]

                    db_msg = Message(
                        id=msg_id,
                        chat_id=chat_id,
                        role=turn.role.value,
                        content=turn.content,
                        sent_at=sent_dt,
                        sent_timezone="UTC",
                        extra_data=extra_data if extra_data else None,
                        is_active=True,
                    )
                    self._db.add(db_msg)

                created_ids.append(chat_id)

            except Exception as exc:
                logger.exception("Failed to import session: %s", exc)
                errors.append(str(exc))

        if created_ids:
            await self._db.commit()

        return SessionImportResult(
            imported_count=len(created_ids),
            created_chat_ids=created_ids,
            failed_count=len(errors),
            errors=errors,
        )

    def _coerce_parse_result(self, raw: TranscriptParseResult | dict[str, object]) -> TranscriptParseResult:
        """Coerce raw dictionary or TranscriptParseResult into TranscriptParseResult."""
        if isinstance(raw, TranscriptParseResult):
            return raw

        turns: list[CanonicalTranscriptTurn] = []
        raw_turns = raw.get("turns")
        if isinstance(raw_turns, list):
            for t in raw_turns:
                if isinstance(t, CanonicalTranscriptTurn):
                    turns.append(t)
                elif isinstance(t, dict):
                    role_str = str(t.get("role", "user")).lower()
                    try:
                        role = CanonicalTurnRole(role_str)
                    except ValueError:
                        role = CanonicalTurnRole.USER
                    turns.append(
                        CanonicalTranscriptTurn(
                            turn_id=str(t.get("turn_id", "")),
                            role=role,
                            content=str(t.get("content", "")),
                            thinking_trace=str(t.get("thinking_trace")) if t.get("thinking_trace") else None,
                            timestamp=float(t.get("timestamp") or 0.0),
                            source_event_type=str(t.get("source_event_type", "")),
                        )
                    )

        return TranscriptParseResult(
            session_id=str(raw.get("session_id", "session")),
            title=str(raw.get("title", "Imported Session")),
            turns=turns,
            source_platform=str(raw.get("source_platform", "external")),
            created_at=float(raw.get("created_at") or 0.0),
            updated_at=float(raw.get("updated_at") or 0.0),
            detected_workspace_hint=str(raw.get("detected_workspace_hint")) if raw.get("detected_workspace_hint") else None,
            total_tool_calls=int(raw.get("total_tool_calls") or 0),
        )
