"""[INPUT]
- myrm_agent_harness.toolkits.file_parsers::TextDecodingError / read_text_file (POS: file bytes to text in UTF-8, a Unicode BOM encoding or an identifiable legacy encoding such as GBK)
- myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map::WikiMapEventType (POS: OKF 认知地图模块入口。提供 wiki/index.md, wiki/log.md, wiki/hot.md 与 wiki/SCHEMA.md 的确定性免 LLM 构建与刷新。)
- app.api.wiki.archiver_dependency::_get_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault)
- app.api.wiki.routes::vault_effects (POS: Wiki API route submodules.)
- app.api.wiki.routes.import_helpers::_build_import_message / _publish_import_raw / _schedule_post_import_dedup_scan / _track_import_publish_result / _validate_import_conflict_options (POS: folder/zip/obsidian/urls/video 五条导入路径共用；不感知具体来源。)
- app.api.wiki.routes.schemas_import::ImportFolderRequest / ImportResultResponse (POS: Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian /)

[OUTPUT]
- import_folder: Batch import all text documents from a local folder into the wiki raw/ directory.
- import_zip: Upload and import a ZIP archive of documents into the wiki.

[POS]
Wiki 批量导入子包的一部分；由 __init__.py 聚合为单一 router。文本经 read_text_file 解码，编码无法可靠识别的文件被跳过
（计入 files_scanned，不计入 files_enqueued）。
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from myrm_agent_harness.toolkits.file_parsers import TextDecodingError, read_text_file
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiMapEventType,
)

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import vault_effects
from app.api.wiki.routes.import_helpers import (
    _build_import_message,
    _publish_import_raw,
    _schedule_post_import_dedup_scan,
    _track_import_publish_result,
    _validate_import_conflict_options,
)
from app.api.wiki.routes.schemas_import import (
    ImportFolderRequest,
    ImportResultResponse,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


async def _read_import_text(src_file: Path) -> str | None:
    """The text of one file to import, or None when its encoding cannot be identified reliably.

    Reading runs in a worker thread because identifying a legacy encoding is CPU-bound.
    """
    try:
        return await asyncio.to_thread(read_text_file, src_file)
    except TextDecodingError:
        logger.warning("Skipped %s: not UTF-8 text and its encoding could not be identified reliably", src_file)
        return None


@router.post("/import/folder", response_model=ImportResultResponse)
async def import_folder(
    request: ImportFolderRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ImportResultResponse:
    """Batch import all text documents from a local folder into the wiki raw/ directory."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)
    try:
        source_dir = Path(request.folder_path)
        scanned_files = archiver._structure.scan_folder(source_dir, request.extensions)

        if not scanned_files:
            return ImportResultResponse(
                success=True,
                files_scanned=0,
                files_enqueued=0,
                message="No matching files found",
            )

        enqueued_paths: list[Path] = []
        conflict_paths: list[str] = []
        security_blocked_paths: list[str] = []
        security_redacted_paths: list[str] = []
        files_skipped_conflict = 0
        files_superseded = 0

        for src_file in scanned_files:
            content = await _read_import_text(src_file)
            if content is None:
                continue

            rel_path = src_file.relative_to(source_dir).as_posix()
            result = await _publish_import_raw(
                archiver._structure,
                rel_path,
                content,
                on_conflict=request.on_conflict,
                supersede_reason=request.supersede_reason,
            )
            skipped, superseded = _track_import_publish_result(
                result,
                enqueued_paths=enqueued_paths,
                conflict_paths=conflict_paths,
                security_blocked_paths=security_blocked_paths,
                security_redacted_paths=security_redacted_paths,
            )
            files_skipped_conflict += skipped
            files_superseded += superseded

        if enqueued_paths:
            archiver._queue.add_batch(enqueued_paths)
            if request.auto_compile:
                archiver._compiler.start_background_worker()
            else:
                vault_effects._refresh_wiki_cognitive_map(
                    archiver,
                    WikiMapEventType.IMPORT,
                    f"Imported {len(enqueued_paths)} file(s) without auto-compile",
                    {"files_enqueued": len(enqueued_paths)},
                )

        if enqueued_paths or files_superseded > 0:
            await vault_effects._after_wiki_vault_mutation(archiver, "import folder")

        if enqueued_paths:
            await _schedule_post_import_dedup_scan(agent_id)

        return ImportResultResponse(
            success=True,
            files_scanned=len(scanned_files),
            files_enqueued=len(enqueued_paths),
            files_skipped_conflict=files_skipped_conflict,
            files_superseded=files_superseded,
            files_security_blocked=len(security_blocked_paths),
            files_security_redacted=len(security_redacted_paths),
            conflict_paths=conflict_paths,
            security_blocked_paths=security_blocked_paths,
            security_redacted_paths=security_redacted_paths,
            message=_build_import_message(
                enqueued=len(enqueued_paths),
                skipped_conflict=files_skipped_conflict,
                superseded=files_superseded,
                security_blocked=len(security_blocked_paths),
                security_redacted=len(security_redacted_paths),
                auto_compile=request.auto_compile,
            ),
        )
    except FileNotFoundError as e:
        logger.warning("Folder import source not found: %s", e)
        raise HTTPException(status_code=404, detail="Source folder not found") from e
    except Exception as e:
        logger.error(f"Folder import failed: {e}")
        raise HTTPException(status_code=500, detail="Folder import failed") from e


@router.post("/import/zip", response_model=ImportResultResponse)
async def import_zip(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    file: UploadFile = File(..., description="ZIP file to import"),
    extensions: str = Query(".md,.txt,.org", description="Comma-separated extensions"),
    auto_compile: bool = Query(True, description="Start compilation after import"),
    on_conflict: Literal["skip", "supersede"] = Query(
        "skip",
        description="When a raw file already exists with different content",
    ),
    supersede_reason: str = Query("", description="Required when on_conflict is supersede"),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ImportResultResponse:
    """Upload and import a ZIP archive of documents into the wiki."""
    import zipfile

    _MAX_ZIP_BYTES = 100 * 1024 * 1024  # 100 MB
    _validate_import_conflict_options(on_conflict, supersede_reason)

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    if file.size and file.size > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")

    ext_list = [e.strip() for e in extensions.split(",") if e.strip()]

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            zip_path = tmp_path / "upload.zip"

            content = await file.read()
            if len(content) > _MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")
            zip_path.write_bytes(content)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path / "extracted")

            extracted_dir = tmp_path / "extracted"
            scanned_files = archiver._structure.scan_folder(extracted_dir, ext_list)

            if not scanned_files:
                return ImportResultResponse(
                    success=True,
                    files_scanned=0,
                    files_enqueued=0,
                    message="No matching files in ZIP",
                )

            enqueued_paths: list[Path] = []
            conflict_paths: list[str] = []
            security_blocked_paths: list[str] = []
            security_redacted_paths: list[str] = []
            files_skipped_conflict = 0
            files_superseded = 0

            for src_file in scanned_files:
                file_content = await _read_import_text(src_file)
                if file_content is None:
                    continue

                rel_path = src_file.relative_to(extracted_dir).as_posix()
                result = await _publish_import_raw(
                    archiver._structure,
                    rel_path,
                    file_content,
                    on_conflict=on_conflict,
                    supersede_reason=supersede_reason,
                )
                skipped, superseded = _track_import_publish_result(
                    result,
                    enqueued_paths=enqueued_paths,
                    conflict_paths=conflict_paths,
                    security_blocked_paths=security_blocked_paths,
                    security_redacted_paths=security_redacted_paths,
                )
                files_skipped_conflict += skipped
                files_superseded += superseded

            if enqueued_paths:
                archiver._queue.add_batch(enqueued_paths)
                if auto_compile:
                    archiver._compiler.start_background_worker()
                else:
                    vault_effects._refresh_wiki_cognitive_map(
                        archiver,
                        WikiMapEventType.IMPORT,
                        f"Imported {len(enqueued_paths)} file(s) from ZIP without auto-compile",
                        {"files_enqueued": len(enqueued_paths)},
                    )

            if enqueued_paths or files_superseded > 0:
                await vault_effects._after_wiki_vault_mutation(archiver, "import zip")

            if enqueued_paths:
                await _schedule_post_import_dedup_scan(agent_id)

            return ImportResultResponse(
                success=True,
                files_scanned=len(scanned_files),
                files_enqueued=len(enqueued_paths),
                files_skipped_conflict=files_skipped_conflict,
                files_superseded=files_superseded,
                files_security_blocked=len(security_blocked_paths),
                files_security_redacted=len(security_redacted_paths),
                conflict_paths=conflict_paths,
                security_blocked_paths=security_blocked_paths,
                security_redacted_paths=security_redacted_paths,
                message=_build_import_message(
                    enqueued=len(enqueued_paths),
                    skipped_conflict=files_skipped_conflict,
                    superseded=files_superseded,
                    security_blocked=len(security_blocked_paths),
                    security_redacted=len(security_redacted_paths),
                    auto_compile=auto_compile,
                    source_label=" from ZIP",
                ),
            )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZIP import failed: {e}")
        raise HTTPException(status_code=500, detail="ZIP import failed") from e
