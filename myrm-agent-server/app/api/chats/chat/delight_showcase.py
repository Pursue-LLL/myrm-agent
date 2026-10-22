"""[INPUT]
- Query parameters: category, q
- Path parameters: chat_id, template_id
- Request bodies: ValidateSandboxRequest, CreateSandboxContractRequest
- DelightShowcaseService: Domain service

[OUTPUT]
- GET /chats/delight-templates: List hobbyist templates
- GET /chats/delight-templates/{template_id}: Retrieve single template detail
- POST /chats/{chat_id}/delight-sandbox/validate: Validate single-file artifact
- POST /chats/{chat_id}/delight-sandbox/contract: Create verified sandbox contract

[POS]
API route layer for Zero-Code Hobbyist Delight & Single-File Sandbox (Item 40 P0).
Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import error_response, success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.artifacts.delight_showcase import DelightShowcaseService

router = APIRouter()


class ValidateSandboxRequest(BaseModel):
    html_source: str = Field(..., min_length=1, description="Raw HTML source of the single-file artifact")
    title: str = Field(default="Delight Sandbox", max_length=100, description="Artifact title")


class CreateSandboxContractRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="Artifact title")
    html_source: str = Field(..., min_length=1, description="Raw HTML source of the single-file artifact")


@router.get("/delight-templates", response_model=StandardSuccessResponse)
async def list_delight_templates(
    category: str | None = Query(default=None, description="Optional category filter"),
    q: str | None = Query(default=None, description="Optional search keyword"),
) -> JSONResponse:
    """Lists prebuilt zero-code hobbyist delight templates across celebrations, games, and romance."""
    service = DelightShowcaseService.get_instance()
    templates = service.list_templates(category=category, query=q)
    return success_response(
        data=[
            {
                "template_id": t.template_id,
                "title": t.title,
                "category": t.category,
                "description": t.description,
                "prompt_seed": t.prompt_seed,
                "tags": t.tags,
                "icon_name": t.icon_name,
                "is_featured": t.is_featured,
                "created_at_ms": t.created_at_ms,
            }
            for t in templates
        ]
    )


@router.get("/delight-templates/{template_id}", response_model=StandardSuccessResponse)
async def get_delight_template(
    template_id: str = Path(..., description="Unique template identifier"),
) -> JSONResponse:
    """Retrieves full detail and source code of a prebuilt delight template."""
    service = DelightShowcaseService.get_instance()
    template = service.get_template(template_id)
    if template is None:
        return error_response(message=f"Template '{template_id}' not found", status_code=404)

    return success_response(
        data={
            "template_id": template.template_id,
            "title": template.title,
            "category": template.category,
            "description": template.description,
            "prompt_seed": template.prompt_seed,
            "html_source": template.html_source,
            "tags": template.tags,
            "icon_name": template.icon_name,
            "is_featured": template.is_featured,
            "created_at_ms": template.created_at_ms,
        }
    )


@router.post("/{chat_id}/delight-sandbox/validate", response_model=StandardSuccessResponse)
async def validate_delight_sandbox(
    payload: ValidateSandboxRequest,
    chat_id: str = Path(..., description="Session identifier"),
) -> JSONResponse:
    """Validates single-file self-containment and returns compiled artifact with mobile viewport safeguards."""
    service = DelightShowcaseService.get_instance()
    result = service.validate_and_compile(payload.html_source, title=payload.title)
    return success_response(
        data={
            "is_valid": result.is_valid,
            "issues": result.issues,
            "has_canvas": result.has_canvas,
            "has_audio": result.has_audio,
            "has_tailwind": result.has_tailwind,
            "compiled_html": result.compiled_html,
        }
    )


@router.post("/{chat_id}/delight-sandbox/contract", response_model=StandardSuccessResponse)
async def create_delight_sandbox_contract(
    payload: CreateSandboxContractRequest,
    chat_id: str = Path(..., description="Session identifier"),
) -> JSONResponse:
    """Compiles and registers an immutable SingleFileSandboxContract for instant presentation."""
    service = DelightShowcaseService.get_instance()
    contract = service.create_contract(
        session_id=chat_id,
        title=payload.title,
        html_source=payload.html_source,
    )
    return success_response(
        data={
            "contract_id": contract.contract_id,
            "session_id": contract.session_id,
            "title": contract.title,
            "has_canvas": contract.has_canvas,
            "has_audio": contract.has_audio,
            "has_tailwind": contract.has_tailwind,
            "is_self_contained": contract.is_self_contained,
            "compiled_html": contract.compiled_html,
            "finalized_at_ms": contract.finalized_at_ms,
        }
    )
