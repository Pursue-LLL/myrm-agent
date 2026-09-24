"""Session event log and artifacts ZIP export pack endpoint.

[INPUT]
- myrm_agent_harness.agent.event_log.backends.file_backend::FileEventLogBackend
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault
- myrm_agent_harness.api::redact_sensitive_text
- app.database.models.chat::Chat
- app.database.models.artifact::Artifact, ArtifactVersion
- app.platform_utils.workspace_root::get_workspace_root

[OUTPUT]
- router: APIRouter with HEAD and GET /{chat_id}/export-pack endpoints

[POS]
- app.api.chats.chat.export_pack: Session export stream pack delivering
  verbatim event logs, subagent logs, and artifacts in a self-contained ZIP.
"""

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.api import redact_sensitive_text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.core.utils.errors import internal_error, not_found_error
from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.database.models.chat import Chat
from app.platform_utils.workspace_root import get_workspace_root

logger = logging.getLogger(__name__)

router = APIRouter()


class _ZipStreamBuffer:
    """In-memory chunk buffer for incremental ZIP streaming with O(1) memory."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def write(self, b: bytes) -> int:
        self._buf.extend(b)
        return len(b)

    def flush(self) -> None:
        pass

    def read_and_clear(self) -> bytes:
        chunk = bytes(self._buf)
        self._buf.clear()
        return chunk


def _is_safe_id(identifier: str) -> bool:
    """Validate identifier contains only alphanumeric, hyphen or underscore chars."""
    return bool(identifier and all(c.isalnum() or c in ("-", "_") for c in identifier) and len(identifier) <= 128)


def _sanitize_arcname(arcname: str) -> str:
    """Normalize and sanitize an archive path to prevent Zip Slip directory traversal."""
    parts = [p for p in arcname.replace("\\", "/").split("/") if p and p != "." and p != ".."]
    return "/".join(parts)


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_path_strictly_within(target: Path, base_dir: Path) -> bool:
    """Verify resolved target is strictly contained within base_dir (guards against symlink escape)."""
    try:
        target.resolve().relative_to(base_dir.resolve())
        return True
    except (ValueError, RuntimeError):
        return False


def _build_content_disposition(chat_title: str | None, chat_id: str) -> str:
    raw_title = chat_title or "chat"
    safe_ascii = (
        "".join(c for c in raw_title if c.isascii() and (c.isalnum() or c in ("-", "_"))).strip()
        or "session"
    )
    ascii_filename = f"session_{safe_ascii[:30]}_{chat_id[:8]}.zip"
    encoded_filename = quote(f"session_{raw_title}_{chat_id[:8]}.zip")
    return f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'


async def _generate_zip_stream(
    chat: Chat,
    log_dir: Path,
    db: AsyncSession,
    redact_secrets: bool,
    include_artifacts: bool,
    include_subagents: bool,
) -> AsyncIterator[bytes]:
    """Generate chunked ZIP stream yielding bytes incrementally with bounded memory."""
    buf = _ZipStreamBuffer()
    manifest_files: list[dict[str, object]] = []

    # 1. Read root session event log (with optional PII/secrets redaction)
    root_log_path = log_dir / f"{chat.id}.jsonl"
    root_log_bytes = b""
    if root_log_path.exists() and root_log_path.is_file():
        try:
            raw_text = root_log_path.read_text(encoding="utf-8", errors="replace")
            if redact_secrets:
                lines = [redact_sensitive_text(line) for line in raw_text.splitlines(keepends=True)]
                root_log_bytes = "".join(lines).encode("utf-8")
            else:
                root_log_bytes = raw_text.encode("utf-8")
        except Exception as exc:
            logger.warning("Failed to read root event log for session %s: %s", chat.id, exc)

    manifest_files.append(
        {
            "path": "session.jsonl",
            "size_bytes": len(root_log_bytes),
            "sha256": _compute_sha256(root_log_bytes),
            "status": "ok" if root_log_bytes else "empty_or_missing",
        }
    )

    # 2. Discover subagent logs if requested
    subagent_entries: list[tuple[str, bytes]] = []
    if include_subagents and log_dir.exists():
        sub_prefix = f"{chat.id}_"
        for log_file in log_dir.glob(f"{sub_prefix}*.jsonl"):
            if not log_file.is_file() or not _is_path_strictly_within(log_file, log_dir):
                continue
            sub_id = log_file.stem.removeprefix(sub_prefix)
            try:
                sub_text = log_file.read_text(encoding="utf-8", errors="replace")
                if redact_secrets:
                    sub_lines = [redact_sensitive_text(line) for line in sub_text.splitlines(keepends=True)]
                    sub_bytes = "".join(sub_lines).encode("utf-8")
                else:
                    sub_bytes = sub_text.encode("utf-8")
                arc_path = _sanitize_arcname(f"subagents/{sub_id}/session.jsonl")
                subagent_entries.append((arc_path, sub_bytes))
                manifest_files.append(
                    {
                        "path": arc_path,
                        "size_bytes": len(sub_bytes),
                        "sha256": _compute_sha256(sub_bytes),
                        "status": "ok",
                    }
                )
            except Exception as exc:
                logger.warning("Failed reading subagent log %s: %s", log_file.name, exc)

    # 3. Discover physical artifacts from database and ArtifactVault
    artifact_entries: list[tuple[str, bytes]] = []
    if include_artifacts:
        try:
            workspace_root = get_workspace_root()
            vault = ArtifactVault(str(workspace_root))
            vault_objects_dir = vault.objects_dir

            stmt = (
                select(Artifact)
                .options(selectinload(Artifact.versions))
                .where(Artifact.chat_id == chat.id, Artifact.is_deleted.is_(False))
            )
            result = await db.execute(stmt)
            artifacts = result.scalars().all()

            for art in artifacts:
                safe_art_name = "".join(c for c in art.name if c.isalnum() or c in ("-", "_", ".")).strip() or art.id
                for ver in art.versions:
                    vault_id = ver.vault_uri.removeprefix("vault://") if ver.vault_uri else ver.id
                    if not _is_safe_id(vault_id):
                        continue
                    obj_path = vault_objects_dir / vault_id
                    if (
                        obj_path.exists()
                        and obj_path.is_file()
                        and _is_path_strictly_within(obj_path, vault_objects_dir)
                    ):
                        try:
                            content = obj_path.read_bytes()
                            rel_arc = _sanitize_arcname(f"artifacts/{safe_art_name}/{ver.id}_{safe_art_name}")
                            artifact_entries.append((rel_arc, content))
                            manifest_files.append(
                                {
                                    "path": rel_arc,
                                    "size_bytes": len(content),
                                    "sha256": _compute_sha256(content),
                                    "status": "ok",
                                }
                            )
                        except Exception as read_err:
                            logger.warning("Failed reading artifact %s: %s", obj_path.name, read_err)
                            manifest_files.append(
                                {
                                    "path": f"artifacts/{safe_art_name}/{ver.id}_{safe_art_name}",
                                    "size_bytes": 0,
                                    "sha256": "",
                                    "status": "unreadable",
                                }
                            )
        except Exception as exc:
            logger.warning("Error collecting artifacts for chat %s: %s", chat.id, exc)

    # 4. Build manifest.json metadata
    manifest_dict = {
        "schema_version": "1.0",
        "export_type": "session_event_log_archive",
        "chat": {
            "id": chat.id,
            "title": chat.title,
            "source": chat.source,
            "agent_id": chat.agent_id,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
            "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
            "total_calls": chat.total_calls,
            "total_tokens": chat.total_tokens,
            "total_usd": chat.total_usd,
        },
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "options": {
            "redact_secrets": redact_secrets,
            "include_artifacts": include_artifacts,
            "include_subagents": include_subagents,
        },
        "integrity_report": {
            "total_files": len(manifest_files),
            "files": manifest_files,
        },
    }
    manifest_bytes = json.dumps(manifest_dict, indent=2, ensure_ascii=False).encode("utf-8")

    # 5. Incrementally write all files into the streaming ZIP buffer
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # Write manifest.json
        zf.writestr("manifest.json", manifest_bytes)
        chunk = buf.read_and_clear()
        if chunk:
            yield chunk

        # Write root session.jsonl
        zf.writestr("session.jsonl", root_log_bytes)
        chunk = buf.read_and_clear()
        if chunk:
            yield chunk

        # Write subagent event logs
        for arc_path, data in subagent_entries:
            zf.writestr(arc_path, data)
            chunk = buf.read_and_clear()
            if chunk:
                yield chunk

        # Write artifact files
        for arc_path, data in artifact_entries:
            zf.writestr(arc_path, data)
            chunk = buf.read_and_clear()
            if chunk:
                yield chunk

    # Final chunk containing the ZIP Central Directory
    final_chunk = buf.read_and_clear()
    if final_chunk:
        yield final_chunk


@router.head("/{chat_id}/export-pack")
async def preflight_export_pack(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Preflight check for session ZIP export pack (verifies chat existence and readiness)."""
    if not _is_safe_id(chat_id):
        raise not_found_error(resource=f"Chat session {chat_id}")

    chat_stmt = select(Chat).where(Chat.id == chat_id)
    chat_result = await db.execute(chat_stmt)
    chat = chat_result.scalar_one_or_none()
    if not chat:
        raise not_found_error(resource=f"Chat session {chat_id}")

    disposition = _build_content_disposition(chat.title, chat.id)
    return Response(
        status_code=200,
        headers={
            "Content-Type": "application/zip",
            "Content-Disposition": disposition,
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("/{chat_id}/export-pack")
async def export_chat_pack(
    chat_id: str,
    redact_secrets: bool = Query(True, description="Whether to redact sensitive secrets and API keys"),
    include_artifacts: bool = Query(True, description="Whether to include generated artifacts"),
    include_subagents: bool = Query(True, description="Whether to include subagent event logs"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export complete session event logs, subagent traces, and artifacts as a streaming ZIP pack."""
    if not _is_safe_id(chat_id):
        raise not_found_error(resource=f"Chat session {chat_id}")

    try:
        chat_stmt = select(Chat).where(Chat.id == chat_id)
        chat_result = await db.execute(chat_stmt)
        chat = chat_result.scalar_one_or_none()
        if not chat:
            raise not_found_error(resource=f"Chat session {chat_id}")

        log_dir = Path(settings.database.event_log_dir)

        # Durability Barrier: flush in-flight appends before read
        backend = FileEventLogBackend(log_dir=log_dir, session_id=chat_id)
        await backend.flush()

        stream = _generate_zip_stream(
            chat=chat,
            log_dir=log_dir,
            db=db,
            redact_secrets=redact_secrets,
            include_artifacts=include_artifacts,
            include_subagents=include_subagents,
        )

        disposition = _build_content_disposition(chat.title, chat.id)
        return StreamingResponse(
            stream,
            media_type="application/zip",
            headers={
                "Content-Disposition": disposition,
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(operation="Export chat pack", exception=exc) from exc
