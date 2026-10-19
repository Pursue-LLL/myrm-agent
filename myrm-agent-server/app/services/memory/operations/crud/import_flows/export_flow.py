"""Memory export flow handlers.

[INPUT]
app.services.memory.archive.archive::MemoryArchiveService (POS: 记忆归档服务)

[OUTPUT]
export_memories, export_rules_safe, preview_rules_safe, export_memories_markdown,
export_memory_archive: JSON/Markdown/ZIP export endpoints and their previews.

[POS]
Export half of the memory operations handlers, split from the import flows so
each module owns one lifecycle phase.
"""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryOperationKind,
    MemoryOperationStatus,
)

from app.database.connection import get_session
from app.schemas.memory.archive import (
    MemoryArchiveExportResponse,
)
from app.schemas.memory.crud import (
    MEMORY_EXPORT_VERSION,
    MemoryExportResponse,
)
from app.services.memory.archive.archive import MemoryArchiveService
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.operations.crud._common import _record_memory_event

logger = logging.getLogger(__name__)


async def export_memories(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryExportResponse:
    """Export all user memories as portable JSON (excludes embeddings)."""
    raw_export = await manager.export_all()
    data: dict[str, list[dict[str, object]]] = {}
    if isinstance(raw_export, dict):
        for k, entries in raw_export.items():
            key = str(k)
            if not isinstance(entries, list):
                data[key] = []
                continue
            rows: list[dict[str, object]] = []
            for item in entries:
                if isinstance(item, dict):
                    rows.append({str(ik): iv for ik, iv in item.items()})
            data[key] = rows
    total = sum(len(entries) for entries in data.values())
    return MemoryExportResponse(version=MEMORY_EXPORT_VERSION, data=data, total_count=total)


async def export_rules_safe(
    manager: MemoryManager = Depends(get_crud_memory_manager),
    agent_id: str | None = Query(default=None, description="Filter by agent scope"),
    rule_ids: str | None = Query(default=None, description="Comma-separated rule IDs to export"),
    output_format: str = Query(default="markdown", description="Output format: markdown or json"),
) -> StreamingResponse:
    """Export procedural rules with privacy sanitization for safe sharing."""
    ids_list = [r.strip() for r in rule_ids.split(",") if r.strip()] if rule_ids else None
    results = await manager.export_rules_safe(
        agent_id=agent_id,
        rule_ids=ids_list,
        output_format=output_format,
    )
    if not results:
        raise HTTPException(status_code=404, detail="No rules found matching criteria")

    ext = "json" if output_format == "json" else "md"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in results:
            filename = f"rule_{str(item['id'])[:8]}.{ext}"
            zf.writestr(filename, str(item["rendered"]))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="rules_safe_{len(results)}.zip"',
            "X-Export-Count": str(len(results)),
        },
    )


async def preview_rules_safe(
    manager: MemoryManager = Depends(get_crud_memory_manager),
    agent_id: str | None = Query(default=None, description="Filter by agent scope"),
    rule_ids: str | None = Query(default=None, description="Comma-separated rule IDs to preview"),
    output_format: str = Query(default="markdown", description="Output format: markdown or json"),
) -> list[dict[str, object]]:
    """Preview sanitized rules without downloading (for frontend diff display)."""
    ids_list = [r.strip() for r in rule_ids.split(",") if r.strip()] if rule_ids else None
    return await manager.export_rules_safe(
        agent_id=agent_id,
        rule_ids=ids_list,
        output_format=output_format,
    )


async def export_memories_markdown(
    manager: MemoryManager = Depends(get_crud_memory_manager),
    agent_id: str | None = Query(default=None, description="Filter by agent scope"),
) -> StreamingResponse:
    """Export all memories as a ZIP of Markdown files with YAML frontmatter."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        counts = await manager.export_markdown(tmp_dir, agent_id=agent_id)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            from pathlib import Path

            root = Path(tmp_dir)
            for file_path in root.rglob("*.md"):
                arcname = str(file_path.relative_to(root))
                zf.write(file_path, arcname)

        buf.seek(0)
        total = sum(counts.values())
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="memories_markdown_{total}.zip"',
                "X-Export-Count": str(total),
            },
        )


async def export_memory_archive(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryArchiveExportResponse:
    """Export the single-user memory surface as a GUI-reviewable archive."""

    async with get_session() as db:
        archive = await MemoryArchiveService(db).export_archive(manager)
    await _record_memory_event(
        kind=MemoryOperationKind.OBSERVE,
        status=MemoryOperationStatus.SUCCESS,
        summary="Memory archive exported.",
        metadata={
            "archive_version": archive.manifest.version,
            "section_count": len(archive.manifest.sections),
            "content_redacted": archive.manifest.content_redacted,
        },
    )
    return MemoryArchiveExportResponse(archive=archive)
