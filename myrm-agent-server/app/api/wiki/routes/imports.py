"""Wiki folder/zip/obsidian 批量导入路由。

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiMapEventType,
)

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import shared
from app.api.wiki.routes.schemas_import import (
    ImportFolderRequest,
    ImportResultResponse,
    ObsidianImportRequest,
    ObsidianImportResultResponse,
)
from app.api.wiki.routes.shared import (
    _build_import_message,
    _publish_import_raw,
    _schedule_post_import_dedup_scan,
    _track_import_publish_result,
    _validate_import_conflict_options,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)


router = APIRouter(tags=["wiki"])


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
            try:
                content = src_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = src_file.read_text(encoding="latin-1")
                except Exception:
                    logger.warning(f"Skipping unreadable file: {src_file}")
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
                shared._refresh_wiki_cognitive_map(
                    archiver,
                    WikiMapEventType.IMPORT,
                    f"Imported {len(enqueued_paths)} file(s) without auto-compile",
                    {"files_enqueued": len(enqueued_paths)},
                )

        if enqueued_paths or files_superseded > 0:
            await shared._after_wiki_vault_mutation(archiver, "import folder")

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
                try:
                    file_content = src_file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    try:
                        file_content = src_file.read_text(encoding="latin-1")
                    except Exception:
                        logger.warning(f"Skipping unreadable file in ZIP: {src_file}")
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
                    shared._refresh_wiki_cognitive_map(
                        archiver,
                        WikiMapEventType.IMPORT,
                        f"Imported {len(enqueued_paths)} file(s) from ZIP without auto-compile",
                        {"files_enqueued": len(enqueued_paths)},
                    )

            if enqueued_paths or files_superseded > 0:
                await shared._after_wiki_vault_mutation(archiver, "import zip")

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


async def _process_obsidian_vault(
    vault_root: Path,
    archiver: MemoryToWikiArchiver,
    auto_compile: bool,
    *,
    on_conflict: Literal["skip", "supersede"] = "skip",
    supersede_reason: str = "",
    source_label: str = "",
    agent_id: str | None = None,
) -> ObsidianImportResultResponse:
    """Shared logic for processing an Obsidian vault directory into Wiki."""
    from app.services.wiki.obsidian import (
        ObsidianImportStats,
        prepare_obsidian_file,
    )

    scanned_files = archiver._structure.scan_folder(vault_root, [".md"])
    stats = ObsidianImportStats(files_scanned=len(scanned_files))

    assets_dir = archiver._structure.wiki_dir / "assets"
    enqueued_paths: list[Path] = []
    conflict_paths: list[str] = []
    security_blocked_paths: list[str] = []
    security_redacted_paths: list[str] = []

    for src_file in scanned_files:
        try:
            prepared = prepare_obsidian_file(src_file, vault_root, assets_dir)
            if prepared is None:
                stats.files_skipped += 1
                continue

            result = await _publish_import_raw(
                archiver._structure,
                prepared.relative_path,
                prepared.content,
                on_conflict=on_conflict,
                supersede_reason=supersede_reason,
            )
            skipped_conflict, superseded = _track_import_publish_result(
                result,
                enqueued_paths=enqueued_paths,
                conflict_paths=conflict_paths,
                security_blocked_paths=security_blocked_paths,
                security_redacted_paths=security_redacted_paths,
            )
            stats.files_skipped_conflict += skipped_conflict
            stats.files_superseded += superseded

            if result.conflict_skipped or result.security_blocked:
                continue

            stats.files_processed += 1
            stats.images_copied += prepared.images_copied
            if prepared.metadata:
                stats.frontmatter_parsed += 1
                tags = prepared.metadata.get("tags")
                if isinstance(tags, list):
                    stats.tags_extracted += len(tags)
                elif tags:
                    stats.tags_extracted += 1
        except Exception as exc:
            stats.files_skipped += 1
            stats.errors.append(f"{src_file.name}: {exc}")
            logger.warning("Skipping Obsidian file %s: %s", src_file, exc)

    if enqueued_paths:
        archiver._queue.add_batch(enqueued_paths)
        if auto_compile:
            archiver._compiler.start_background_worker()
        else:
            shared._refresh_wiki_cognitive_map(
                archiver,
                WikiMapEventType.IMPORT,
                f"Imported {len(enqueued_paths)} Obsidian note(s) without auto-compile",
                {
                    "files_enqueued": len(enqueued_paths),
                    "source": source_label or "obsidian",
                },
            )

    suffix = f" from {source_label}" if source_label else ""
    message_parts = [
        f"Imported {stats.files_processed} Obsidian notes{suffix}",
        f"({stats.tags_extracted} tags, {stats.images_copied} images)",
    ]
    if stats.files_skipped_conflict:
        message_parts.append(f"{stats.files_skipped_conflict} conflict(s) skipped")
    if stats.files_superseded:
        message_parts.append(f"{stats.files_superseded} superseded")
    if security_blocked_paths:
        message_parts.append(f"{len(security_blocked_paths)} blocked (sensitive content)")
    if security_redacted_paths:
        message_parts.append(f"{len(security_redacted_paths)} redacted")
    if stats.files_skipped:
        message_parts.append(f"{stats.files_skipped} skipped")
    if auto_compile:
        message_parts.append("compilation started")
    if enqueued_paths or stats.files_superseded > 0:
        await shared._after_wiki_vault_mutation(archiver, "import obsidian")
    if enqueued_paths:
        await _schedule_post_import_dedup_scan(agent_id)
    if stats.images_copied > 0:
        from app.services.wiki.asset_index_service import schedule_wiki_asset_index

        schedule_wiki_asset_index(archiver, agent_id=agent_id)
    return ObsidianImportResultResponse(
        success=True,
        files_scanned=stats.files_scanned,
        files_processed=stats.files_processed,
        files_skipped=stats.files_skipped,
        files_skipped_conflict=stats.files_skipped_conflict,
        files_superseded=stats.files_superseded,
        files_security_blocked=len(security_blocked_paths),
        files_security_redacted=len(security_redacted_paths),
        conflict_paths=conflict_paths,
        security_blocked_paths=security_blocked_paths,
        security_redacted_paths=security_redacted_paths,
        tags_extracted=stats.tags_extracted,
        images_copied=stats.images_copied,
        message=", ".join(message_parts),
    )


@router.post("/import/obsidian", response_model=ObsidianImportResultResponse)
async def import_obsidian_vault(
    request: ObsidianImportRequest,
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ObsidianImportResultResponse:
    """Import an Obsidian vault with frontmatter parsing and image embed handling."""
    _validate_import_conflict_options(request.on_conflict, request.supersede_reason)
    try:
        vault_root = Path(request.vault_path)
        if not vault_root.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"Vault directory not found: {request.vault_path}",
            )
        return await _process_obsidian_vault(
            vault_root,
            archiver,
            request.auto_compile,
            on_conflict=request.on_conflict,
            supersede_reason=request.supersede_reason,
            agent_id=agent_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Obsidian vault import failed: %s", e)
        raise HTTPException(status_code=500, detail="Obsidian vault import failed") from e


@router.post("/import/obsidian-zip", response_model=ObsidianImportResultResponse)
async def import_obsidian_zip(
    archiver: Annotated[MemoryToWikiArchiver, Depends(_get_wiki_archiver)],
    file: UploadFile = File(..., description="ZIP of Obsidian vault"),
    auto_compile: bool = Query(True),
    on_conflict: Literal["skip", "supersede"] = Query("skip"),
    supersede_reason: str = Query(""),
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> ObsidianImportResultResponse:
    """Upload an Obsidian vault as ZIP (for WebUI / cloud-hosted deployments)."""
    import zipfile

    _MAX_ZIP_BYTES = 100 * 1024 * 1024
    _validate_import_conflict_options(on_conflict, supersede_reason)

    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")
    if file.size and file.size > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            zip_path = tmp_path / "vault.zip"
            raw_bytes = await file.read()
            if len(raw_bytes) > _MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="ZIP file too large (max 100 MB)")
            zip_path.write_bytes(raw_bytes)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path / "vault")

            vault_root = tmp_path / "vault"
            top_items = list(vault_root.iterdir())
            if len(top_items) == 1 and top_items[0].is_dir():
                vault_root = top_items[0]

            return await _process_obsidian_vault(
                vault_root,
                archiver,
                auto_compile,
                on_conflict=on_conflict,
                supersede_reason=supersede_reason,
                source_label="ZIP",
                agent_id=agent_id,
            )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from None
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Obsidian ZIP import failed: %s", e)
        raise HTTPException(status_code=500, detail="Obsidian ZIP import failed") from e
