"""External transcript incremental synchronization service.

[INPUT]
- myrm_agent_harness.toolkits.memory.strategies.incremental_transcript::IncrementalTranscriptParser (POS: 增量转录流解析器)
- app.services.memory.imports.secret_scrubber::scrub_sensitive_data (POS: 敏感凭据过滤管道)
- app.services.chat.conversation_recall_index_service::ConversationRecallIndexService (POS: 会话召回索引生命周期服务)
- app.database.models.chat::Chat (POS: 聊天会话域模型)
- sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
- ExternalTranscriptSyncResult: Sync summary report DTO.
- ExternalTranscriptSyncService: Incremental watermark synchronization boundary.

[POS]
Server-level incremental sync engine for external agent transcripts (Claude Code, Codex).
Manages file offsets, applies privacy scrubbing, isolates chats from the main sidebar,
and drives FTS5 conversation recall indexing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chat import Chat
from app.services.chat.conversation_recall_index_service import (
    ConversationRecallIndexService,
)
from app.services.memory.imports.secret_scrubber import scrub_sensitive_data
from myrm_agent_harness.toolkits.memory.strategies.incremental_transcript import (
    IncrementalTranscriptParser,
    TranscriptTurn,
)

logger = logging.getLogger(__name__)

DEFAULT_WATERMARK_FILE = Path("data/external_transcript_watermarks.json")


@dataclass(slots=True)
class ExternalTranscriptSyncResult:
    """Result report of an incremental external transcript sync."""

    synced_files: int = 0
    new_turns: int = 0
    affected_chats: list[str] = field(default_factory=list)
    skipped_files: int = 0
    errors: list[str] = field(default_factory=list)


class ExternalTranscriptSyncService:
    """Service to incrementally ingest and index external transcripts."""

    def __init__(self, watermark_path: Path | None = None) -> None:
        self.watermark_path = watermark_path or DEFAULT_WATERMARK_FILE

    def load_watermarks(self) -> dict[str, dict[str, object]]:
        """Load persistent watermark mapping (file_path -> {offset, mtime, last_synced_at})."""
        if not self.watermark_path.exists():
            return {}
        try:
            with open(self.watermark_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Failed to load transcript watermarks: %s", exc)
            return {}

    def save_watermarks(self, watermarks: dict[str, dict[str, object]]) -> None:
        """Persist watermark state safely to disk."""
        try:
            self.watermark_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.watermark_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(watermarks, f, indent=2, ensure_ascii=False)
            temp_path.replace(self.watermark_path)
        except Exception as exc:
            logger.warning("Failed to persist transcript watermarks: %s", exc)

    async def sync_file(
        self,
        db: AsyncSession,
        file_path: Path,
        *,
        source: str = "external:claude_code",
        watermarks: dict[str, dict[str, object]] | None = None,
    ) -> tuple[int, str | None]:
        """Incrementally sync a single JSONL file into chats and recall index.

        Returns (new_turns_count, chat_id).
        """
        if not file_path.is_file():
            return 0, None

        path_str = str(file_path.resolve())
        stat = file_path.stat()
        current_mtime = stat.st_mtime
        current_size = stat.st_size

        wm = watermarks.get(path_str, {}) if watermarks is not None else {}
        last_offset = int(wm.get("offset", 0))
        last_mtime = float(wm.get("mtime", 0.0))

        # Skip if file has not been modified and size did not increase
        if current_mtime <= last_mtime and current_size <= last_offset:
            return 0, None

        # Handle file truncation/rotation: if file became smaller, reset offset
        if current_size < last_offset:
            last_offset = 0

        with open(file_path, "rb") as stream:
            chunk = IncrementalTranscriptParser.parse_stream(stream, start_offset=last_offset)

        if not chunk.turns and chunk.new_byte_offset == last_offset:
            return 0, None

        # Derive a stable virtual chat_id for this external transcript
        path_hash = hashlib.sha256(path_str.encode("utf-8")).hexdigest()[:16]
        chat_id = f"ext_{source.split(':')[-1]}_{path_hash}"
        title = chunk.session_title or file_path.stem.replace("_", " ").title()

        # Ensure Chat exists with incognito isolation
        await self._ensure_isolated_chat(db, chat_id=chat_id, title=title, source=source)

        # Ingest turns into conversation recall index
        for turn_idx, turn in enumerate(chunk.turns):
            await self._ingest_turn(db, chat_id=chat_id, turn=turn, turn_idx=turn_idx)

        # Update watermark in memory
        if watermarks is not None:
            watermarks[path_str] = {
                "offset": chunk.new_byte_offset,
                "mtime": current_mtime,
                "last_synced_at": datetime.now(UTC).isoformat(),
            }

        return len(chunk.turns), chat_id

    async def sync_directory(
        self,
        db: AsyncSession,
        directory_path: Path,
        *,
        source: str = "external:claude_code",
    ) -> ExternalTranscriptSyncResult:
        """Scan directory for JSONL transcripts and sync incrementally."""
        result = ExternalTranscriptSyncResult()
        if not directory_path.is_dir():
            result.errors.append(f"Directory not found: {directory_path}")
            return result

        watermarks = self.load_watermarks()
        jsonl_files = list(directory_path.glob("**/*.jsonl"))

        for file_path in jsonl_files:
            try:
                turns_count, chat_id = await self.sync_file(
                    db,
                    file_path,
                    source=source,
                    watermarks=watermarks,
                )
                if turns_count > 0 and chat_id:
                    result.synced_files += 1
                    result.new_turns += turns_count
                    if chat_id not in result.affected_chats:
                        result.affected_chats.append(chat_id)
                else:
                    result.skipped_files += 1
            except Exception as exc:
                logger.error("Error syncing transcript %s: %s", file_path, exc)
                result.errors.append(f"{file_path.name}: {exc}")

        # Persist updated watermarks
        self.save_watermarks(watermarks)
        return result

    async def _ensure_isolated_chat(
        self,
        db: AsyncSession,
        *,
        chat_id: str,
        title: str,
        source: str,
    ) -> None:
        """Ensure external chat is stored with is_incognito=True to isolate from sidebar."""
        stmt = select(Chat).where(Chat.id == chat_id)
        res = await db.execute(stmt)
        chat = res.scalars().first()

        if chat is None:
            new_chat = Chat(
                id=chat_id,
                title=title[:500],
                source=source,
                is_incognito=True,  # Critical: isolates from user sidebar
                action_mode="fast",
            )
            db.add(new_chat)
            await db.flush()
        elif chat.title != title and title != "Untitled":
            chat.title = title[:500]
            await db.flush()

    async def _ingest_turn(
        self,
        db: AsyncSession,
        *,
        chat_id: str,
        turn: TranscriptTurn,
        turn_idx: int,
    ) -> None:
        """Sanitize and append turn messages to conversation recall index."""
        now = datetime.now(UTC)
        ts = self._parse_iso_datetime(turn.timestamp) or now

        # User message
        if turn.user_content:
            scrubbed_user = scrub_sensitive_data(turn.user_content)
            user_msg_id = f"{chat_id}_u_{int(ts.timestamp())}_{turn_idx}"
            await ConversationRecallIndexService.append_message(
                db,
                chat_id=chat_id,
                message_id=user_msg_id,
                role="user",
                content=scrubbed_user,
                sent_at=ts,
            )

        # Assistant message
        if turn.assistant_content:
            scrubbed_asst = scrub_sensitive_data(turn.assistant_content)
            asst_msg_id = f"{chat_id}_a_{int(ts.timestamp())}_{turn_idx}"
            await ConversationRecallIndexService.append_message(
                db,
                chat_id=chat_id,
                message_id=asst_msg_id,
                role="assistant",
                content=scrubbed_asst,
                sent_at=ts,
            )

    @staticmethod
    def _parse_iso_datetime(dt_str: str) -> datetime | None:
        """Safely parse ISO timestamp string into UTC datetime."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            return None
