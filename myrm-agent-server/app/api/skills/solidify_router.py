"""[INPUT] SolidifySkillRequest and ExternalPreviewCreateRequest schemas.
[OUTPUT] Endpoints for 1-click skill solidification and isolated clean preview pages.
[POS] app/api/skills/solidify_router.py.
"""

from fastapi import APIRouter, HTTPException, Response, status

from app.services.skills.solidify import (
    ExternalPreviewCreateRequest,
    ExternalPreviewMetadata,
    SkillSolidifyService,
    SolidifySkillRequest,
    SolidifySkillResponse,
)

router = APIRouter(prefix="/solidify", tags=["skills-solidify"])


@router.post("", response_model=SolidifySkillResponse, status_code=status.HTTP_201_CREATED)
def solidify_skill_endpoint(payload: SolidifySkillRequest) -> SolidifySkillResponse:
    """Solidify deliverable into 4-in-1 standard reusable skill bundle."""
    service = SkillSolidifyService.get_instance()
    try:
        return service.solidify_skill(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to solidify skill: {str(exc)}",
        ) from exc


@router.post("/preview", response_model=ExternalPreviewMetadata, status_code=status.HTTP_201_CREATED)
def create_external_preview_endpoint(payload: ExternalPreviewCreateRequest) -> ExternalPreviewMetadata:
    """Register isolated clean deliverable preview for true browser rendering."""
    service = SkillSolidifyService.get_instance()
    try:
        return service.register_clean_preview(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register preview: {str(exc)}",
        ) from exc


@router.get("/preview/{preview_id}", response_class=Response)
def get_clean_preview_page(preview_id: str) -> Response:
    """Render clean deliverable in full browser with CSP relaxation & no-referrer to prevent broken assets."""
    service = SkillSolidifyService.get_instance()
    result = service.get_clean_preview(preview_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview session not found or expired")

    content, content_type, _ = result
    headers = {
        "Content-Security-Policy": "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(
        content=content,
        media_type=f"{content_type}; charset=utf-8",
        headers=headers,
    )
