"""Skill packaging and upload endpoints

Endpoints for downloading skills as ZIP and uploading skill packages.
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.api.skills.schemas import PackagePreviewResponse, SkillPackageInfoResponse, UploadSkillResponse
from app.core.skills.packaging import skill_packaging_service

logger = logging.getLogger(__name__)

router = APIRouter()


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
        
    redactions_response = None
    if result.redactions:
        redactions_response = {
            filename: [
                {"line_number": r["line_number"], "original": r["original"], "redacted": r["redacted"], "reason": r["reason"]}
                for r in file_redactions
            ]
            for filename, file_redactions in result.redactions.items()
        }
        
    return PackagePreviewResponse(
        success=result.success,
        is_safe=result.is_safe,
        error=result.error,
        redactions=redactions_response
    )

@router.get("/{skill_id}/download")
async def download_skill(
    skill_id: str,
    apply_redactions: bool = Query(False, description="Whether to apply redactions to sensitive information"),
) -> Response:
    """Download skill as ZIP package

    Args:
        skill_id: Skill ID
        apply_redactions: Whether to apply redactions to sensitive information

    Returns:
        ZIP file
    """
    result = await skill_packaging_service.package_skill(skill_id, apply_redactions=apply_redactions)

    if not result.success:
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
        user_id: User ID (from auth header)

    Returns:
        Upload result
    """
    # Validate file type (supports .zip and .skill formats, .skill is essentially ZIP)
    if not file.filename or not (file.filename.endswith(".zip") or file.filename.endswith(".skill")):
        raise HTTPException(status_code=400, detail="Please upload .zip or .skill file")

    # Read content
    content = await file.read()

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
    # Validate file type (supports .zip and .skill formats, .skill is essentially ZIP)
    if not file.filename or not (file.filename.endswith(".zip") or file.filename.endswith(".skill")):
        raise HTTPException(status_code=400, detail="Please upload .zip or .skill file")

    # Read content
    content = await file.read()

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
        user_id: User ID

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
