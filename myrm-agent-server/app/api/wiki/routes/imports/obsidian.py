"""[INPUT]
- myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map::WikiMapEventType (POS: OKF 认知地图模块入口。提供 wiki/index.md, wiki/log.md, wiki/hot.md 与 wiki/SCHEMA.md 的确定性免 LLM 构建与刷新。)
- app.api.wiki.archiver_dependency::_get_wiki_archiver (POS: Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault)
- app.api.wiki.routes::vault_effects (POS: Wiki API route submodules.)
- app.api.wiki.routes.import_helpers::_publish_import_raw / _schedule_post_import_dedup_scan / _track_import_publish_result / _validate_import_conflict_options (POS: folder/zip/obsidian/urls/video 五条导入路径共用；不感知具体来源。)
- app.api.wiki.routes.schemas_import::ObsidianImportRequest / ObsidianImportResultResponse (POS: Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。)
- app.services.wiki::MemoryToWikiArchiver (POS: Top-level wiki facade. Domain subpackages (vault / maintain / governance / obsidian /)

[OUTPUT]
- _process_obsidian_vault: Shared logic for processing an Obsidian vault directory into Wiki.
- import_obsidian_vault: Import an Obsidian vault with frontmatter parsing and image embed handling.
- import_obsidian_zip: Upload an Obsidian vault as ZIP (for WebUI / cloud-hosted deployments).

[POS]
Wiki 批量导入子包的一部分；由 __init__.py 聚合为单一 router。
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from myrm_agent_harness.toolkits.wiki.pipeline.cognitive_map import (
    WikiMapEventType,
)

from app.api.wiki.archiver_dependency import get_scoped_wiki_archiver as _get_wiki_archiver
from app.api.wiki.routes import vault_effects
from app.api.wiki.routes.import_helpers import (
    _publish_import_raw,
    _schedule_post_import_dedup_scan,
    _track_import_publish_result,
    _validate_import_conflict_options,
)
from app.api.wiki.routes.schemas_import import (
    ObsidianImportRequest,
    ObsidianImportResultResponse,
)
from app.services.wiki import MemoryToWikiArchiver

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


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
            vault_effects._refresh_wiki_cognitive_map(
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
        await vault_effects._after_wiki_vault_mutation(archiver, "import obsidian")
    if enqueued_paths:
        await _schedule_post_import_dedup_scan(agent_id)
    if stats.images_copied > 0:
        from app.services.wiki.asset_index_service import schedule_wiki_asset_index

        schedule_wiki_asset_index(archiver, agent_id=agent_id)
    return ObsidianImportResultResponse(
        success=True,
        files_scanned=stats.files_scanned,
        files_processed=stats.files_processed,
        files_enqueued=len(enqueued_paths),
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
