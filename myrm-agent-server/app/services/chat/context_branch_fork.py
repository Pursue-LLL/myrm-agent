"""Fork a new chat from a volume-backed context snapshot bookmark.

[INPUT]
- myrm_agent_harness.runtime.context.context_branches (POS: branch manifest lookup)
- myrm_agent_harness.runtime.context.transparent_reader (POS: gzip/jsonl snapshot read)
- app.database.models (POS: Chat, Message, ConversationFork ORM)
- app.services.chat.conversation_recall_index_service (POS: recall index rebuild)

[OUTPUT]
- ContextBranchForkService.fork_from_branch (POS: create child chat from snapshot jsonl)

[POS]
Business-layer fork from CompactedSummaryView snapshot bookmarks (OpenClaw branch parity).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, ConversationFork, Message
from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

logger = logging.getLogger(__name__)

_LANGCHAIN_TYPE_TO_ROLE: dict[str, str] = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
}


class BranchForkResult(NamedTuple):
    success: bool
    new_chat_id: str | None
    parent_chat_id: str
    branch_id: str
    message_count: int
    error: str | None = None


def _resolve_snapshot_path(session_id: str, snapshot_path: str) -> Path:
    from myrm_agent_harness.runtime.execution_paths import CONTEXT_ROOT, PERSISTENT_ROOT

    normalized = snapshot_path.strip()
    if not normalized:
        raise ValueError("snapshot_path is empty")

    candidates: list[Path] = []
    raw = Path(normalized)
    if raw.is_absolute():
        candidates.append(raw)
    else:
        rel = normalized.removeprefix("/persistent/").lstrip("/")
        candidates.append(Path(PERSISTENT_ROOT) / rel)
        candidates.append(Path(PERSISTENT_ROOT) / normalized)
        candidates.append(Path(CONTEXT_ROOT) / session_id / "snapshots" / Path(normalized).name)
        if not normalized.endswith(".gz"):
            candidates.append(Path(f"{PERSISTENT_ROOT}/{rel}.gz"))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(f"Snapshot not found for path: {snapshot_path}")


def _content_to_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "\n".join(parts)
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def _parse_snapshot_messages(text: str) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("_meta") is True:
            continue
        msg_type = record.get("type")
        if not isinstance(msg_type, str):
            continue
        role = _LANGCHAIN_TYPE_TO_ROLE.get(msg_type)
        if role is None:
            continue
        content = _content_to_text(record.get("content"))
        extra: dict[str, object] = {}
        for key in ("tool_calls", "tool_call_id", "name", "additional_kwargs", "reasoning_content"):
            value = record.get(key)
            if value is not None:
                extra[key] = value
        messages.append(
            {
                "role": role,
                "content": content,
                "extra_data": extra or None,
            }
        )
    return messages


class ContextBranchForkService:
    @staticmethod
    async def fork_from_branch(
        db: AsyncSession,
        parent_chat_id: str,
        branch_id: str,
        new_title: str | None = None,
    ) -> BranchForkResult:
        from myrm_agent_harness.runtime.context.context_branches import get_context_branch
        from myrm_agent_harness.runtime.context.transparent_reader import read_context_file_sync

        branch = get_context_branch(parent_chat_id, branch_id)
        if branch is None:
            return BranchForkResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                branch_id=branch_id,
                message_count=0,
                error="Bookmark not found",
            )

        parent_stmt = select(Chat).where(Chat.id == parent_chat_id)
        parent_result = await db.execute(parent_stmt)
        parent_chat = parent_result.scalar_one_or_none()
        if parent_chat is None:
            return BranchForkResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                branch_id=branch_id,
                message_count=0,
                error="Chat not found",
            )

        try:
            snapshot_file = _resolve_snapshot_path(parent_chat_id, branch.snapshot_path)
            raw_text = read_context_file_sync(snapshot_file)
        except (OSError, ValueError, FileNotFoundError) as exc:
            logger.warning(
                "Context branch fork snapshot read failed chat=%s branch=%s: %s",
                parent_chat_id,
                branch_id,
                exc,
            )
            return BranchForkResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                branch_id=branch_id,
                message_count=0,
                error=str(exc),
            )

        parsed = _parse_snapshot_messages(raw_text)
        if not parsed:
            return BranchForkResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                branch_id=branch_id,
                message_count=0,
                error="Snapshot contains no messages",
            )

        new_chat_id = str(uuid4())
        title = (new_title or branch.label or "Snapshot branch").strip()[:255] or "Snapshot branch"

        if parent_chat.sandbox_base_dir:
            fork_workspace_dir = parent_chat.sandbox_base_dir
        elif parent_chat.workspace_dir:
            fork_workspace_dir = parent_chat.workspace_dir
        else:
            from app.services.chat.chat_service import ChatService
            from app.services.chat.effective_workspace import resolve_effective_chat_workspace

            parent_dto = await ChatService.get_chat_metadata(parent_chat_id)
            fork_workspace_dir = (
                await resolve_effective_chat_workspace(parent_dto, jit_fallback=False)
                if parent_dto is not None
                else None
            )

        new_chat = Chat(
            id=new_chat_id,
            agent_id=parent_chat.agent_id,
            title=title,
            source=parent_chat.source,
            channel_session_key=None,
            session_loaded_skill_names=parent_chat.session_loaded_skill_names,
            action_mode=parent_chat.action_mode,
            workspace_dir=fork_workspace_dir,
            sandbox_base_dir=None,
            project_id=parent_chat.project_id,
            is_incognito=parent_chat.is_incognito,
            compacted_summary=None,
            compacted_before_id=None,
            compacted_at=None,
            compacted_tokens_saved=None,
            session_notes_json=parent_chat.session_notes_json,
        )
        db.add(new_chat)

        base_time = datetime.now(UTC)
        for index, item in enumerate(parsed):
            msg_time = base_time + timedelta(milliseconds=index)
            extra_data = item.get("extra_data")
            db.add(
                Message(
                    id=str(uuid4()),
                    chat_id=new_chat_id,
                    role=str(item["role"]),
                    content=str(item["content"]),
                    sent_at=msg_time,
                    sent_timezone="UTC",
                    created_at=msg_time,
                    extra_data=extra_data if isinstance(extra_data, dict) else None,
                )
            )

        db.add(
            ConversationFork(
                child_chat_id=new_chat_id,
                parent_chat_id=parent_chat_id,
                fork_checkpoint_id=None,
                fork_message_index=len(parsed) - 1,
            )
        )
        await db.flush()
        await ConversationRecallIndexService.rebuild_chat(db, new_chat_id)

        try:
            await db.commit()
        except Exception as exc:
            logger.exception("Failed to commit context branch fork")
            await db.rollback()
            return BranchForkResult(
                success=False,
                new_chat_id=None,
                parent_chat_id=parent_chat_id,
                branch_id=branch_id,
                message_count=0,
                error=str(exc),
            )

        logger.info(
            "Context branch fork created parent=%s branch=%s child=%s messages=%d",
            parent_chat_id,
            branch_id,
            new_chat_id,
            len(parsed),
        )
        return BranchForkResult(
            success=True,
            new_chat_id=new_chat_id,
            parent_chat_id=parent_chat_id,
            branch_id=branch_id,
            message_count=len(parsed),
            error=None,
        )
