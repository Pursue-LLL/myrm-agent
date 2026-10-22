"""[INPUT]
- PromoteScratchpadRequest: Pydantic payload describing scratchpad to promote
- ProjectPromotionService: Backend service converting scratchpad draft to persisted workspace files

[OUTPUT]
- router: APIRouter handling POST /api/v1/workspace/promote

[POS]
Workspace API router for dual-track workspace promotion from transient scratchpads.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.workspace.promotion import ProjectPromotionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workspace-promotion"])


class PromoteScratchpadRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=200, description="Scratchpad title")]
    content: Annotated[str, Field(min_length=1, description="Scratchpad markdown content")]
    target_project_name: Annotated[str | None, Field(default=None, max_length=100, description="Optional target project folder name")]
    init_readme: Annotated[bool, Field(default=True, description="Whether to generate README.md")]
    temporary_tags: Annotated[list[str], Field(default_factory=list, description="Associated tag labels")]


class PromoteScratchpadResponse(BaseModel):
    project_name: str
    target_directory: str
    created_files: list[str]
    initial_context_prompt: str
    promoted_at: str
    provenance_metadata: dict[str, str]


@router.post(
    "/promote",
    response_model=PromoteScratchpadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Promote transient scratchpad into permanent project workspace",
)
async def promote_scratchpad(
    payload: PromoteScratchpadRequest,
) -> PromoteScratchpadResponse:
    try:
        result = ProjectPromotionService.promote_scratchpad(
            title=payload.title,
            content=payload.content,
            target_project_name=payload.target_project_name,
            init_readme=payload.init_readme,
            temporary_tags=payload.temporary_tags,
        )
        return PromoteScratchpadResponse(
            project_name=result.project_name,
            target_directory=result.target_directory,
            created_files=result.created_files,
            initial_context_prompt=result.initial_context_prompt,
            promoted_at=result.promoted_at,
            provenance_metadata=result.provenance_metadata,
        )
    except Exception as exc:
        logger.exception("Failed to promote scratchpad")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to promote scratchpad: {exc}",
        ) from exc
