"""External transcript memory recall API operations.

[INPUT]
- app.database.session::get_db (POS: 数据库会话依赖)
- app.services.memory.imports.external_transcript_sync::ExternalTranscriptSyncService (POS: 外部 Agent 会话增量同步服务)
- sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
- router: /external-transcripts endpoints for syncing and status inspection.

[POS]
API operations for external agent transcript recall management.
Supports local directory scan and cloud-mode browser file batch uploads.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.memory.imports.external_transcript_sync import (
    ExternalTranscriptSyncService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/external-transcripts")


class ExternalFilePayload(BaseModel):
    """File payload uploaded from browser File System API in cloud mode."""

    filename: str = Field(..., description="Original filename ending with .jsonl")
    content: str = Field(..., description="Raw text content of transcript")


class ExternalTranscriptSyncRequest(BaseModel):
    """Request payload to trigger incremental transcript sync."""

    directory_path: str | None = Field(
        None, description="Local folder path (e.g. ~/.claude/projects)"
    )
    source: str = Field(
        "external:claude_code",
        description="Source identifier (external:claude_code, external:codex)",
    )
    uploaded_files: list[ExternalFilePayload] | None = Field(
        None, description="Batch uploaded files for cloud/sandbox mode"
    )


class ExternalTranscriptSyncResponse(BaseModel):
    """Summary of the incremental sync run."""

    synced_files: int
    new_turns: int
    affected_chats: list[str]
    skipped_files: int
    errors: list[str]


class ExternalTranscriptStatusResponse(BaseModel):
    """Current external transcript sync status and watermarks."""

    enabled: bool
    tracked_files_count: int
    last_synced_at: str | None
    default_directory: str


@router.post("/sync", response_model=ExternalTranscriptSyncResponse)
async def sync_external_transcripts(
    req: ExternalTranscriptSyncRequest,
    db: AsyncSession = Depends(get_db),
) -> ExternalTranscriptSyncResponse:
    """Trigger incremental sync of external transcripts from directory or upload."""
    service = ExternalTranscriptSyncService()
    result_synced_files = 0
    result_new_turns = 0
    result_affected_chats: list[str] = []
    result_skipped = 0
    result_errors: list[str] = []

    # Path A: Local directory scan
    if req.directory_path:
        target_dir = Path(req.directory_path).expanduser()
        if not target_dir.is_dir():
            return ExternalTranscriptSyncResponse(
                synced_files=0,
                new_turns=0,
                affected_chats=[],
                skipped_files=0,
                errors=[f"Directory does not exist: {req.directory_path}"],
            )
        dir_res = await service.sync_directory(db, target_dir, source=req.source)
        await db.commit()
        return ExternalTranscriptSyncResponse(
            synced_files=dir_res.synced_files,
            new_turns=dir_res.new_turns,
            affected_chats=dir_res.affected_chats,
            skipped_files=dir_res.skipped_files,
            errors=dir_res.errors,
        )

    # Path B: Cloud / browser uploaded files
    if req.uploaded_files:
        watermarks = service.load_watermarks()
        for up_file in req.uploaded_files:
            try:
                # Save content to a temporary workspace cache file
                cache_dir = Path("data/external_transcripts_cache")
                cache_dir.mkdir(parents=True, exist_ok=True)
                target_file = cache_dir / Path(up_file.filename).name
                # Remove cached file if present to guarantee fresh upload detection
                if target_file.exists():
                    watermarks.pop(str(target_file.resolve()), None)
                target_file.write_text(up_file.content, encoding="utf-8")

                turns_count, chat_id = await service.sync_file(
                    db, target_file, source=req.source, watermarks=watermarks
                )
                if turns_count > 0 and chat_id:
                    result_synced_files += 1
                    result_new_turns += turns_count
                    if chat_id not in result_affected_chats:
                        result_affected_chats.append(chat_id)
                else:
                    result_skipped += 1
            except Exception as exc:
                result_errors.append(f"{up_file.filename}: {exc}")

        service.save_watermarks(watermarks)
        await db.commit()
        return ExternalTranscriptSyncResponse(
            synced_files=result_synced_files,
            new_turns=result_new_turns,
            affected_chats=result_affected_chats,
            skipped_files=result_skipped,
            errors=result_errors,
        )

    # Default fallback: scan standard ~/.claude/projects if present
    default_dir = Path.home() / ".claude" / "projects"
    if default_dir.is_dir():
        def_res = await service.sync_directory(db, default_dir, source=req.source)
        await db.commit()
        return ExternalTranscriptSyncResponse(
            synced_files=def_res.synced_files,
            new_turns=def_res.new_turns,
            affected_chats=def_res.affected_chats,
            skipped_files=def_res.skipped_files,
            errors=def_res.errors,
        )

    return ExternalTranscriptSyncResponse(
        synced_files=0,
        new_turns=0,
        affected_chats=[],
        skipped_files=0,
        errors=["No directory specified and default ~/.claude/projects not found."],
    )


@router.get("/status", response_model=ExternalTranscriptStatusResponse)
async def get_external_transcript_status() -> ExternalTranscriptStatusResponse:
    """Query external transcript indexing status and tracking metrics."""
    service = ExternalTranscriptSyncService()
    watermarks = service.load_watermarks()
    last_synced = None
    for entry in watermarks.values():
        if isinstance(entry, dict) and entry.get("last_synced_at"):
            ts = str(entry["last_synced_at"])
            if last_synced is None or ts > last_synced:
                last_synced = ts

    default_path = str(Path.home() / ".claude" / "projects")
    return ExternalTranscriptStatusResponse(
        enabled=True,
        tracked_files_count=len(watermarks),
        last_synced_at=last_synced,
        default_directory=default_path,
    )
