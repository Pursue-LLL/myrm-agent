"""[INPUT]
- Path parameters: chat_id, variant_id
- Request bodies: RegisterVariantRequest, AddAnnotationRequest, FinalizeContractRequest
- UiVisualAlignmentService: Domain service

[OUTPUT]
- GET /chats/{chat_id}/ui-variants: List variants
- POST /chats/{chat_id}/ui-variants: Register new variant
- POST /chats/{chat_id}/ui-variants/{variant_id}/annotations: Add visual annotation
- GET /chats/{chat_id}/ui-variants/{variant_id}/annotations: List annotations for variant
- POST /chats/{chat_id}/ui-variants/finalize: Finalize approved variant into VisualContract
- GET /chats/{chat_id}/ui-variants/contract: Get latest visual contract

[POS]
API route layer for Multi-Turn UI Design Visual Alignment Workflow (Item 39 P0).
Strictly under 200 lines. Zero `Any`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import error_response, success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.artifacts.ui_alignment import UiVisualAlignmentService

router = APIRouter()


class RegisterVariantRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120, description="Title of the UI variant")
    style_theme: Literal[
        "modern_bento", "minimal_dark", "glassmorphism", "neo_brutalism", "custom"
    ] = Field(default="modern_bento", description="Visual design theme")
    html_content: str = Field(..., description="High fidelity HTML / Tailwind mock structure")
    css_tokens: dict[str, str] = Field(default_factory=dict, description="Design tokens and palette")
    description: str = Field(default="", description="Design notes or layout rationale")
    variant_id: str | None = Field(default=None, description="Optional custom variant ID")


class AddAnnotationRequest(BaseModel):
    x: float = Field(..., ge=0.0, le=100.0, description="X coordinate percentage")
    y: float = Field(..., ge=0.0, le=100.0, description="Y coordinate percentage")
    width: float = Field(..., ge=0.0, le=100.0, description="Bounding box width percentage")
    height: float = Field(..., ge=0.0, le=100.0, description="Bounding box height percentage")
    comment: str = Field(..., min_length=1, max_length=1000, description="Visual feedback commentary")
    label: str = Field(default="visual_feedback", max_length=50, description="Category or priority tag")


class FinalizeContractRequest(BaseModel):
    approved_variant_id: str = Field(..., min_length=1, description="The approved variant ID")


@router.get("/{chat_id}/ui-variants", response_model=StandardSuccessResponse)
async def list_ui_variants(
    chat_id: str = Path(..., description="Session identifier"),
) -> JSONResponse:
    """Lists all UI design variants generated for this session."""
    service = UiVisualAlignmentService.get_instance()
    variants = service.list_variants(chat_id)
    return success_response(
        data=[
            {
                "variant_id": v.variant_id,
                "title": v.title,
                "style_theme": v.style_theme,
                "html_content": v.html_content,
                "css_tokens": v.css_tokens,
                "description": v.description,
                "created_at_ms": v.created_at_ms,
            }
            for v in variants
        ]
    )


@router.post("/{chat_id}/ui-variants", response_model=StandardSuccessResponse)
async def register_ui_variant(
    payload: RegisterVariantRequest,
    chat_id: str = Path(..., description="Session identifier"),
) -> JSONResponse:
    """Registers a new UI design mockup variant for interactive comparison."""
    service = UiVisualAlignmentService.get_instance()
    variant = service.register_variant(
        session_id=chat_id,
        title=payload.title,
        style_theme=payload.style_theme,
        html_content=payload.html_content,
        css_tokens=payload.css_tokens,
        description=payload.description,
        variant_id=payload.variant_id,
    )
    return success_response(
        data={
            "variant_id": variant.variant_id,
            "title": variant.title,
            "style_theme": variant.style_theme,
            "html_content": variant.html_content,
            "css_tokens": variant.css_tokens,
            "description": variant.description,
            "created_at_ms": variant.created_at_ms,
        }
    )


@router.post(
    "/{chat_id}/ui-variants/{variant_id}/annotations",
    response_model=StandardSuccessResponse,
)
async def add_visual_annotation(
    payload: AddAnnotationRequest,
    chat_id: str = Path(..., description="Session identifier"),
    variant_id: str = Path(..., description="Target UI variant ID"),
) -> JSONResponse:
    """Attaches a visual bounding box feedback annotation to a specific variant."""
    service = UiVisualAlignmentService.get_instance()
    variant = service.get_variant(chat_id, variant_id)
    if variant is None:
        return error_response(message=f"Variant '{variant_id}' not found in chat '{chat_id}'", status_code=404)

    annotation = service.add_annotation(
        variant_id=variant_id,
        x=payload.x,
        y=payload.y,
        width=payload.width,
        height=payload.height,
        comment=payload.comment,
        label=payload.label,
    )
    return success_response(
        data={
            "annotation_id": annotation.annotation_id,
            "variant_id": annotation.variant_id,
            "x": annotation.x,
            "y": annotation.y,
            "width": annotation.width,
            "height": annotation.height,
            "comment": annotation.comment,
            "label": annotation.label,
            "created_at_ms": annotation.created_at_ms,
        }
    )


@router.get(
    "/{chat_id}/ui-variants/{variant_id}/annotations",
    response_model=StandardSuccessResponse,
)
async def list_visual_annotations(
    chat_id: str = Path(..., description="Session identifier"),
    variant_id: str = Path(..., description="Target UI variant ID"),
) -> JSONResponse:
    """Lists all canvas feedback annotations for the specified variant."""
    service = UiVisualAlignmentService.get_instance()
    variant = service.get_variant(chat_id, variant_id)
    if variant is None:
        return error_response(message=f"Variant '{variant_id}' not found in chat '{chat_id}'", status_code=404)

    annotations = service.list_annotations(variant_id)
    return success_response(
        data=[
            {
                "annotation_id": a.annotation_id,
                "variant_id": a.variant_id,
                "x": a.x,
                "y": a.y,
                "width": a.width,
                "height": a.height,
                "comment": a.comment,
                "label": a.label,
                "created_at_ms": a.created_at_ms,
            }
            for a in annotations
        ]
    )


@router.post("/{chat_id}/ui-variants/finalize", response_model=StandardSuccessResponse)
async def finalize_visual_contract(
    payload: FinalizeContractRequest,
    chat_id: str = Path(..., description="Session identifier"),
) -> JSONResponse:
    """Finalizes the approved UI variant into an immutable contract with downstream agent prompt."""
    service = UiVisualAlignmentService.get_instance()
    try:
        contract = service.finalize_contract(chat_id, payload.approved_variant_id)
    except ValueError as exc:
        return error_response(message=str(exc), status_code=404)

    return success_response(
        data={
            "contract_id": contract.contract_id,
            "session_id": contract.session_id,
            "approved_variant_id": contract.approved_variant_id,
            "style_theme": contract.style_theme,
            "dom_outline": contract.dom_outline,
            "design_tokens": contract.design_tokens,
            "annotations_count": len(contract.annotations),
            "enforcement_prompt": contract.enforcement_prompt,
            "finalized_at_ms": contract.finalized_at_ms,
        }
    )


@router.get("/{chat_id}/ui-variants/contract", response_model=StandardSuccessResponse)
async def get_visual_contract(
    chat_id: str = Path(..., description="Session identifier"),
) -> JSONResponse:
    """Retrieves the latest finalized visual design contract for this session."""
    service = UiVisualAlignmentService.get_instance()
    contract = service.get_latest_contract(chat_id)
    if contract is None:
        return success_response(data=None)

    return success_response(
        data={
            "contract_id": contract.contract_id,
            "session_id": contract.session_id,
            "approved_variant_id": contract.approved_variant_id,
            "style_theme": contract.style_theme,
            "dom_outline": contract.dom_outline,
            "design_tokens": contract.design_tokens,
            "annotations_count": len(contract.annotations),
            "enforcement_prompt": contract.enforcement_prompt,
            "finalized_at_ms": contract.finalized_at_ms,
        }
    )
