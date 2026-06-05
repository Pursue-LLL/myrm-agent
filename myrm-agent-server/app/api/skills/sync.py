"""Skill synchronization and backup protocol.

Provides a unified export/import mechanism for user skills to solve
the "data island" problem across Desktop, Web, and SaaS deployments.

Also integrates the harness-level SkillSyncManager for collective
skill evolution sync (shared skill repository push/pull).
"""

import asyncio
import io
import logging
import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord
from myrm_agent_harness.agent.skills.evolution.execution.sandbox_validator import SandboxValidator
from pydantic import BaseModel

from app.core.skills.creation.service import skill_creation_service
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _create_export_zip() -> io.BytesIO:
    base_path = skill_creation_service.base_path
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(base_path):
            for file in files:
                file_path = Path(root) / file
                # Only include standard skill files
                if file_path.suffix in (".md", ".json", ".py", ".sh", ".txt"):
                    arcname = file_path.relative_to(base_path)
                    zf.write(file_path, arcname)

    memory_file.seek(0)
    return memory_file


@router.get("/export")
async def export_user_skills() -> StreamingResponse:
    """Export all local skills for a user as a standard ZIP file."""
    base_path = skill_creation_service.base_path
    if not base_path.exists() or not base_path.is_dir():
        raise HTTPException(status_code=404, detail="No local skills directory found.")

    try:
        memory_file = await asyncio.to_thread(_create_export_zip)

        def iterfile() -> Iterator[bytes]:
            yield memory_file.read()

        return StreamingResponse(
            iterfile(),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=myrm_skills_backup_default.zip"},
        )
    except Exception as e:
        logger.error("Failed to export skills: %s", e)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}") from e


async def _process_import_zip(zip_data: bytes) -> tuple[int, list[str]]:
    base_path = skill_creation_service.base_path
    import_count = 0
    imported_skills = []

    # Initialize sandbox validator for security scanning
    validator = SandboxValidator(timeout_seconds=5.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_zip_path = Path(tmpdir) / "upload.zip"
        with open(tmp_zip_path, "wb") as f:
            f.write(zip_data)

        extract_dir = Path(tmpdir) / "extracted"
        with zipfile.ZipFile(tmp_zip_path, "r") as zf:
            zf.extractall(extract_dir)

        base_path.mkdir(parents=True, exist_ok=True)

        for item in extract_dir.iterdir():
            if item.is_dir():
                skill_md_path = item / "SKILL.md"
                if skill_md_path.exists():
                    # 1. Security Scan before importing
                    try:
                        with open(skill_md_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        # Create a temporary SkillRecord for validation
                        # We only need the content and name for dry_run_skill
                        from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage

                        temp_skill = SkillRecord(
                            skill_id=f"temp_{item.name}",
                            name=item.name,
                            description="Temporary skill for import validation",
                            content=content,
                            path=str(skill_md_path),
                            lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
                        )

                        # Run the sandbox validation
                        is_safe, error_msg = await validator.dry_run_skill(temp_skill)
                        if not is_safe:
                            logger.warning(f"Security scan failed for imported skill: {item.name}")
                            raise ValueError(f"Skill {item.name} failed security scan: {error_msg}")

                    except Exception as e:
                        if isinstance(e, ValueError):
                            raise
                        logger.error(f"Error during security scan for {item.name}: {e}")
                        raise ValueError(f"Failed to scan skill {item.name} for security: {e}") from e

                    # 2. If safe, proceed with import
                    target_dir = base_path / item.name
                    if target_dir.exists():
                        shutil.rmtree(target_dir)
                    shutil.copytree(item, target_dir)
                    import_count += 1
                    imported_skills.append(item.name)
    return import_count, imported_skills


@router.post("/import")
async def import_user_skills(
    file: Annotated[UploadFile, File(description="A ZIP file containing SKILL.md directories")],
) -> dict[str, str | int]:
    """Import a ZIP file containing skills into the user's local skill directory."""
    fname = file.filename or ""
    if not fname.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are supported.")

    try:
        zip_data = await file.read()
        import_count, imported_skills = await _process_import_zip(zip_data)

        # Auto-enable imported skills
        if import_count > 0:
            from app.core.skills.providers.local import compute_local_skill_id

            config = await skills_service.user_config.get_config()
            for skill_name in imported_skills:
                skill_dir = skill_creation_service.base_path / skill_name
                skill_id = compute_local_skill_id(skill_dir)
                if skill_id not in config.enabled_local_skill_ids:
                    config.enabled_local_skill_ids.append(skill_id)
            await skills_service.user_config.save_config(config)

    except zipfile.BadZipFile as e:
        raise HTTPException(status_code=400, detail="Invalid ZIP file format.") from e
    except ValueError as e:
        # Security scan failed or other validation error
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to import skills: %s", e)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}") from e

    if import_count > 0:
        from app.core.skills.config_version import bump_skill_config_version

        bump_skill_config_version()

    return {"status": "success", "message": f"Successfully imported {import_count} skills.", "imported_count": import_count}


# --- Collective Sync Endpoints (SkillSyncManager integration) ---


class SyncStatusResponse(BaseModel):
    enabled: bool
    last_sync_at: str | None = None
    pending_push_count: int = 0
    pending_pull_count: int = 0
    is_syncing: bool = False


class SyncTriggerResponse(BaseModel):
    success: bool
    push_count: int = 0
    pull_new: int = 0
    pull_updated: int = 0
    error: str = ""


def _get_sync_manager():
    """Get the SkillSyncManager instance from skill sync idle integration."""
    from myrm_agent_harness.agent.skills.sync.idle_integration import _sync_manager_ref

    if _sync_manager_ref is None:
        raise HTTPException(
            status_code=503,
            detail="Skill sync not configured. Enable shared sync in settings.",
        )
    return _sync_manager_ref


@router.get("/sync/status")
async def get_sync_status() -> SyncStatusResponse:
    """Get current skill sync status for UI display."""
    try:
        manager = _get_sync_manager()
        status = await manager.get_status()
        return SyncStatusResponse(
            enabled=status.enabled,
            last_sync_at=status.last_sync_at.isoformat() if status.last_sync_at else None,
            pending_push_count=status.pending_push_count,
            pending_pull_count=status.pending_pull_count,
            is_syncing=status.is_syncing,
        )
    except HTTPException:
        return SyncStatusResponse(enabled=False)


@router.post("/sync/trigger")
async def trigger_sync() -> SyncTriggerResponse:
    """Manually trigger a full bidirectional skill sync."""
    manager = _get_sync_manager()

    if manager.is_syncing:
        raise HTTPException(status_code=409, detail="Sync already in progress")

    push_result, pull_result = await manager.full_sync()

    if push_result.pushed_count > 0 or pull_result.new_count > 0 or pull_result.updated_count > 0:
        from app.core.skills.config_version import bump_skill_config_version

        bump_skill_config_version()

    return SyncTriggerResponse(
        success=push_result.success and pull_result.success,
        push_count=push_result.pushed_count,
        pull_new=pull_result.new_count,
        pull_updated=pull_result.updated_count,
        error=push_result.error or pull_result.error or "",
    )
