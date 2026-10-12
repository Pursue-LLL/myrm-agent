"""Skill packaging and upload endpoints.

[INPUT]
- app.core.skills.packaging::skill_packaging_service, SKILL_CHANGED_SINCE_PREVIEW, ExportFormat
  (POS: skill ZIP packaging with redaction preview, validation, unpack and register.)
- app.api.skills.schemas::PackagePreviewResponse, SkillPackageInfoResponse, UploadSkillResponse,
  redaction_responses (POS: wire models.)

[OUTPUT]
- router: GET /{skill_id}/preview (redaction preview + review digest), POST /{skill_id}/export
  (ZIP; 409 skill_changed_since_preview when kept findings no longer match the files),
  POST /upload, POST /validate, POST /workspace/package.

[POS]
API-layer skill package download and upload; thin delegation to the packaging service.
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.skills.schemas import (
    PackagePreviewResponse,
    SkillPackageInfoResponse,
    UploadSkillResponse,
    redaction_responses,
)
from app.core.skills.packaging import SKILL_CHANGED_SINCE_PREVIEW, ExportFormat, skill_packaging_service

logger = logging.getLogger(__name__)

router = APIRouter()


async def _read_skill_archive(file: UploadFile) -> bytes:
    """Read an uploaded ``.zip`` or ``.skill`` package (a ``.skill`` file is a ZIP)."""
    if not file.filename or not file.filename.endswith((".zip", ".skill")):
        raise HTTPException(status_code=400, detail="Please upload .zip or .skill file")
    return await file.read()


@router.get("/{skill_id}/preview", response_model=PackagePreviewResponse)
async def preview_skill_package(
    skill_id: str,
) -> PackagePreviewResponse:
    """Preview skill package before downloading to check for sensitive information.

    Args:
        skill_id: Skill ID

    Returns:
        Preview result including any redactions
    """
    result = await skill_packaging_service.package_skill(skill_id, preview_only=True)

    if not result.success:
        raise HTTPException(status_code=404, detail=result.error)

    return PackagePreviewResponse(
        success=result.success,
        is_safe=result.is_safe,
        error=result.error,
        redactions=redaction_responses(result.redactions) if result.redactions else None,
        eval_cases_count=result.eval_cases_count,
        review_digest=result.review_digest,
    )


class ExportSkillRequest(BaseModel):
    """Export options: which findings to redact, which to keep, and the archive format."""

    apply_redactions: bool = False
    ignored_redactions: dict[str, list[int]] | None = None
    export_format: ExportFormat = "agent_plugin"
    review_digest: str | None = None  # from the preview; required when ignored_redactions keeps findings


@router.post("/{skill_id}/export")
async def export_skill(
    skill_id: str,
    request: ExportSkillRequest,
) -> Response:
    """Export skill as ZIP package

    Args:
        skill_id: Skill ID
        request: Export options including redaction preferences and format

    Returns:
        ZIP file
    """
    result = await skill_packaging_service.package_skill(
        skill_id,
        apply_redactions=request.apply_redactions,
        ignored_redactions=request.ignored_redactions,
        export_format=request.export_format,
        review_digest=request.review_digest,
    )

    if not result.success:
        if result.error_code == SKILL_CHANGED_SINCE_PREVIEW:
            raise HTTPException(
                status_code=409,
                detail={"message": result.error, "error_code": result.error_code},
            )
        raise HTTPException(status_code=404, detail=result.error)

    return Response(
        content=result.zip_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


@router.post("/upload", response_model=UploadSkillResponse)
async def upload_skill(
    file: UploadFile = File(...),
    force: bool = Query(False, description="Whether to force overwrite skill with same name"),
) -> UploadSkillResponse:
    """Upload skill package and register

    Args:
        file: Skill package file (supports .zip or .skill format)
        force: Whether to force overwrite skill with same name

    Returns:
        Upload result
    """
    content = await _read_skill_archive(file)

    # Unpack and register
    result = await skill_packaging_service.unpack_and_register(
        zip_content=content,
        force=force,
    )

    return UploadSkillResponse(
        success=result.success,
        skill_id=result.skill_id,
        skill_name=result.skill_name,
        error=result.error,
        restored_eval_cases=result.restored_eval_cases,
    )


@router.post("/validate", response_model=SkillPackageInfoResponse)
async def validate_skill_zip(
    file: UploadFile = File(...),
) -> SkillPackageInfoResponse:
    """Validate skill package (without registration)

    Used to validate package validity before upload

    Args:
        file: Skill package file (supports .zip or .skill format)

    Returns:
        Skill package information
    """
    content = await _read_skill_archive(file)

    # Validate
    info = await skill_packaging_service.validate_skill_zip(content)

    return SkillPackageInfoResponse(
        name=info.name,
        description=info.description,
        version=info.version,
        author=info.author,
        files=info.files,
        is_valid=info.is_valid,
        validation_errors=info.validation_errors,
    )


@router.post("/workspace/package")
async def package_workspace_directory(
    chat_id: str = Form(..., description="Chat ID"),
    directory: str = Form("", description="Directory path to package (relative to workspace root)"),
    container_id: str | None = Form(None, description="Container ID (Docker mode)"),
) -> Response:
    """Package workspace directory as ZIP

    Used to package skill directories generated by skill-creator

    Args:
        chat_id: Chat ID
        directory: Directory path to package
        container_id: Container ID (Docker mode)

    Returns:
        ZIP file
    """
    result = await skill_packaging_service.package_workspace_directory(
        chat_id=chat_id,
        directory=directory,
        container_id=container_id,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return Response(
        content=result.zip_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )
