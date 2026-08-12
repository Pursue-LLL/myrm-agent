"""Skill synchronization and backup protocol.

Provides a unified export/import mechanism for user skills to solve
the "data island" problem across Desktop, Web, and SaaS deployments.

Also integrates the harness-level SkillSyncManager for collective
skill evolution sync (shared skill repository push/pull).
"""

import asyncio
import hashlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from myrm_agent_harness.agent.skills.evolution.core.types import SkillRecord
from myrm_agent_harness.agent.skills.evolution.execution.sandbox_validator import SandboxValidator
from pydantic import BaseModel

from app.api.skills._deploy_capability import require_local_skills_capability
from app.core.skills.creation.service import skill_creation_service
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _packaged_files(skill_dir: Path) -> list[Path]:
    """List files in a skill directory that participate in backup packages."""
    return sorted(
        p
        for p in skill_dir.rglob("*")
        if p.is_file() and p.suffix in (".md", ".json", ".py", ".sh", ".txt")
    )


def _skill_dir_sha256(skill_dir: Path) -> str:
    """Aggregate SHA-256 of every packaged file inside a skill directory.

    The digest covers relative paths plus file bytes, so both content and
    structure changes are detected.
    """
    hasher = hashlib.sha256()
    for file_path in _packaged_files(skill_dir):
        hasher.update(file_path.relative_to(skill_dir).as_posix().encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(file_path.read_bytes())
        hasher.update(b"\x00")
    return hasher.hexdigest()


def _parse_skill_version(content: str) -> int:
    """Extract ``version`` from SKILL.md frontmatter (defaults to 1)."""
    match = re.search(r"^version:\s*(\d+)", content, re.MULTILINE)
    return int(match.group(1)) if match else 1


def _build_export_manifest(base_path: Path) -> dict:
    """Build the backup manifest for every local skill directory."""
    from app.core.skills.providers.local import compute_local_skill_id

    skills: list[dict] = []
    for item in sorted(base_path.iterdir()):
        if not item.is_dir():
            continue
        skill_md = item / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            skills.append(
                {
                    "name": item.name,
                    "skill_id": compute_local_skill_id(item),
                    "sha256": _skill_dir_sha256(item),
                    "version": _parse_skill_version(skill_md.read_text(encoding="utf-8")),
                }
            )
        except OSError:
            continue
    return {
        "format": "myrm-skills-backup",
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "skills": skills,
    }


def _read_manifest(extract_dir: Path) -> dict | None:
    """Read and validate the optional manifest.json inside an import ZIP."""
    manifest_path = extract_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("format") != "myrm-skills-backup":
        return None
    return data


def _create_export_zip() -> io.BytesIO:
    base_path = skill_creation_service.base_path
    memory_file = io.BytesIO()
    manifest = _build_export_manifest(base_path)
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
        )
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
        logger.error("Failed to export skills: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed") from e


@dataclass
class ImportSummary:
    """Result of a backup ZIP import, including drift detection details."""

    imported_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    hash_mismatch_count: int = 0
    has_manifest: bool = False
    imported_skills: list[str] = field(default_factory=list)


def _safe_extract(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    """Extract archive members while rejecting path traversal (zip-slip).

    Each member name must resolve to a path inside ``extract_dir``. Backslash
    separators are normalized to forward slashes for the check (the ZIP spec
    only allows ``/``; a ``\\``-separated ``..`` is a real traversal vector on
    Windows). Absolute paths and escaping ``..`` segments raise ``ValueError``.
    """
    root = extract_dir.resolve()
    for info in zf.infolist():
        raw = info.filename
        if raw.startswith("/") or raw.startswith("\\") or re.match(r"^[A-Za-z]:", raw):
            raise ValueError(f"Unsafe archive member path: {raw!r}")
        normalized = raw.replace("\\", "/")
        target = (extract_dir / normalized).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"Unsafe archive member path: {raw!r}")
    zf.extractall(extract_dir)


async def _process_import_zip(zip_data: bytes) -> ImportSummary:
    base_path = skill_creation_service.base_path
    summary = ImportSummary()

    # Initialize sandbox validator for security scanning
    validator = SandboxValidator(timeout_seconds=5.0)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_zip_path = Path(tmpdir) / "upload.zip"
        with open(tmp_zip_path, "wb") as f:
            f.write(zip_data)

        extract_dir = Path(tmpdir) / "extracted"
        with zipfile.ZipFile(tmp_zip_path, "r") as zf:
            _safe_extract(zf, extract_dir)

        manifest = _read_manifest(extract_dir)
        summary.has_manifest = manifest is not None
        manifest_hashes: dict[str, str] = {}
        if manifest:
            manifest_hashes = {
                entry["name"]: entry["sha256"]
                for entry in manifest.get("skills", [])
                if isinstance(entry, dict) and "name" in entry and "sha256" in entry
            }

        base_path.mkdir(parents=True, exist_ok=True)

        for item in extract_dir.iterdir():
            if item.name == "manifest.json":
                continue
            if not item.is_dir():
                continue
            skill_md_path = item / "SKILL.md"
            if not skill_md_path.exists():
                continue

            # 0. Verify package integrity against the manifest (if present).
            zip_hash = _skill_dir_sha256(item)
            expected_hash = manifest_hashes.get(item.name)
            if expected_hash and zip_hash != expected_hash:
                summary.hash_mismatch_count += 1
                logger.warning(
                    "Manifest hash mismatch for imported skill %s (drift detected)", item.name
                )

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

            # 2. If safe, decide between skip / overwrite / fresh import.
            target_dir = base_path / item.name
            if target_dir.exists() and _skill_dir_sha256(target_dir) == zip_hash:
                # Identical content already on disk: no-op import.
                summary.unchanged_count += 1
            else:
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                    summary.updated_count += 1
                shutil.copytree(item, target_dir)
                summary.imported_count += 1
            summary.imported_skills.append(item.name)
    return summary


@router.post("/import")
async def import_user_skills(
    file: Annotated[UploadFile, File(description="A ZIP file containing SKILL.md directories")],
) -> dict[str, str | int | bool]:
    """Import a ZIP file containing skills into the user's local skill directory."""
    require_local_skills_capability()
    fname = file.filename or ""
    if not fname.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files are supported.")

    try:
        zip_data = await file.read()
        summary = await _process_import_zip(zip_data)

        # Auto-enable imported skills
        if summary.imported_skills:
            from app.core.skills.providers.local import compute_local_skill_id

            config = await skills_service.user_config.get_config()
            for skill_name in summary.imported_skills:
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
        logger.error("Failed to import skills: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Import failed") from e

    if summary.imported_count > 0 or summary.updated_count > 0:
        from app.core.skills.config_version import bump_skill_config_version

        bump_skill_config_version()

    return {
        "status": "success",
        "message": (
            f"Successfully imported {summary.imported_count} skills, "
            f"updated {summary.updated_count}, skipped {summary.unchanged_count}."
        ),
        "imported_count": summary.imported_count,
        "updated_count": summary.updated_count,
        "unchanged_count": summary.unchanged_count,
        "hash_mismatch_count": summary.hash_mismatch_count,
        "has_manifest": summary.has_manifest,
    }


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
