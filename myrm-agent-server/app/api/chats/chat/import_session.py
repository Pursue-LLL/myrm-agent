"""API endpoint for importing external session transcripts directly into chats.

[INPUT]
- ImportTranscriptRequest / Multipart File: Raw JSON / JSONL external transcript payload
- db: AsyncSession database dependency

[OUTPUT]
- ImportTranscriptResponse: Created chat ID, title, and token reduction metrics

[POS]
app/api/chats/chat/import_session.py
Enables zero-friction one-click import of external conversation transcripts (Claude Code, Codex, Hermes)
directly from chat sidebar or creation dialog with strict Prompt Cache affinity.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from myrm_agent_harness.runtime.context.transcripts import (
    ClaudeTranscriptParser,
    CleanTranscriptReducer,
    CodexTranscriptParser,
    HermesTranscriptParser,
    TranscriptParseResult,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models import Chat, Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["chat-import"])


class ImportTranscriptRequest(BaseModel):
    """Payload for importing a raw transcript string."""

    raw_content: str = Field(..., description="Raw JSON or JSONL transcript string")
    source_hint: str | None = Field(None, description="Optional platform hint: claude, codex, hermes")
    target_workspace: str | None = Field(None, description="Optional target workspace directory")
    target_agent_id: str | None = Field(None, description="Optional target agent id")
    title_override: str | None = Field(None, description="Optional custom title for the imported session")


class ImportTranscriptResponse(BaseModel):
    """Result of external session transcript import."""

    ok: bool = True
    chat_id: str
    title: str
    turns_count: int
    source_platform: str
    raw_tokens_estimate: int
    clean_tokens_estimate: int
    reduction_ratio: float


def _detect_and_parse_high_fidelity(
    raw_content: str,
    source_hint: str | None,
    default_session_id: str,
) -> TranscriptParseResult | None:
    """Attempt high-fidelity parser if payload matches vendor signature."""
    raw_stripped = raw_content.strip()
    hint = (source_hint or "").lower().strip()

    if hint in {"claude", "claude_code"} or "tool_use" in raw_stripped or "<thinking>" in raw_stripped:
        try:
            import io
            parser = ClaudeTranscriptParser()
            res = parser.parse_stream(io.StringIO(raw_content), default_session_id=default_session_id)
            if res.turns:
                return res
        except Exception as e:
            logger.debug("Claude high-fidelity parse failed, falling back: %s", e)

    if hint in {"codex", "codex_cli"} or '"role": "developer"' in raw_stripped:
        try:
            import io
            parser = CodexTranscriptParser()
            res = parser.parse_stream(io.StringIO(raw_content), default_session_id=default_session_id)
            if res.turns:
                return res
        except Exception as e:
            logger.debug("Codex high-fidelity parse failed, falling back: %s", e)

    if hint in {"hermes"} or "hermes" in raw_stripped[:200].lower():
        try:
            import io
            parser = HermesTranscriptParser()
            res = parser.parse_stream(io.StringIO(raw_content), default_session_id=default_session_id)
            if res.turns:
                return res
        except Exception as e:
            logger.debug("Hermes high-fidelity parse failed, falling back: %s", e)

    return None


@router.post("/import-transcript", response_model=ImportTranscriptResponse)
async def import_transcript_json(
    req: ImportTranscriptRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportTranscriptResponse:
    """Import a raw JSON/JSONL transcript text directly into a native chat."""
    if not req.raw_content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript content cannot be empty",
        )

    return await _process_import(
        raw_content=req.raw_content,
        source_hint=req.source_hint,
        target_workspace=req.target_workspace,
        target_agent_id=req.target_agent_id,
        title_override=req.title_override,
        db=db,
    )


@router.post("/import-transcript/file", response_model=ImportTranscriptResponse)
async def import_transcript_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    source_hint: Annotated[str | None, Form()] = None,
    target_workspace: Annotated[str | None, Form()] = None,
    target_agent_id: Annotated[str | None, Form()] = None,
    title_override: Annotated[str | None, Form()] = None,
) -> ImportTranscriptResponse:
    """Import an uploaded JSON/JSONL transcript file directly into a native chat."""
    content_bytes = await file.read()
    raw_content = content_bytes.decode("utf-8", errors="replace").strip()
    if not raw_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    return await _process_import(
        raw_content=raw_content,
        source_hint=source_hint,
        target_workspace=target_workspace,
        target_agent_id=target_agent_id,
        title_override=title_override or file.filename,
        db=db,
    )


async def _process_import(
    raw_content: str,
    source_hint: str | None,
    target_workspace: str | None,
    target_agent_id: str | None,
    title_override: str | None,
    db: AsyncSession,
) -> ImportTranscriptResponse:
    lines = raw_content.splitlines()

    # Pass through CleanTranscriptReducer for Token reduction metrics and secret scrubbing
    clean_res = CleanTranscriptReducer.reduce(lines)
    if not clean_res.turns:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid conversational turns could be extracted from transcript",
        )

    chat_id = f"chat_{clean_res.source_tool}_{uuid4().hex[:16]}"
    effective_title = (
        title_override.strip()
        if title_override and title_override.strip()
        else (clean_res.session_title or "Imported Conversation")[:60]
    )
    workspace_dir = target_workspace or clean_res.cwd or "/workspace"
    now_utc = datetime.now(tz=UTC)

    first_msg = clean_res.turns[0].user_content if clean_res.turns else ""
    last_msg = clean_res.turns[-1].assistant_content if clean_res.turns else ""

    # Create first-class chat (is_incognito=False guarantees sidebar visibility)
    new_chat = Chat(
        id=chat_id,
        agent_id=target_agent_id,
        title=effective_title,
        first_message=first_msg,
        last_message=last_msg,
        action_mode="fast",
        source=f"imported_{clean_res.source_tool}",
        workspace_dir=workspace_dir,
        is_incognito=False,
        created_at=now_utc,
        updated_at=now_utc,
    )
    db.add(new_chat)

    # Persist turns as Message records
    total_raw_tokens = sum(t.raw_tokens_estimate for t in clean_res.turns)
    total_clean_tokens = sum(t.clean_tokens_estimate for t in clean_res.turns)

    for turn in clean_res.turns:
        # User message
        if turn.user_content:
            u_msg = Message(
                id=f"msg_{chat_id[:24]}_{turn.turn_index}_u",
                chat_id=chat_id,
                role="user",
                content=turn.user_content,
                sent_at=now_utc,
                sent_timezone="UTC",
                created_at=now_utc,
            )
            db.add(u_msg)

        # Assistant message with folded tools
        if turn.assistant_content:
            extra: dict[str, object] = {}
            if turn.tools_summary:
                extra["tools_summary"] = turn.tools_summary

            a_msg = Message(
                id=f"msg_{chat_id[:24]}_{turn.turn_index}_a",
                chat_id=chat_id,
                role="assistant",
                content=turn.assistant_content,
                sent_at=now_utc,
                sent_timezone="UTC",
                extra_data=extra if extra else None,
                created_at=now_utc,
            )
            db.add(a_msg)

    await db.commit()

    return ImportTranscriptResponse(
        ok=True,
        chat_id=chat_id,
        title=effective_title,
        turns_count=len(clean_res.turns),
        source_platform=clean_res.source_tool,
        raw_tokens_estimate=total_raw_tokens,
        clean_tokens_estimate=total_clean_tokens,
        reduction_ratio=clean_res.reduction_ratio,
    )
