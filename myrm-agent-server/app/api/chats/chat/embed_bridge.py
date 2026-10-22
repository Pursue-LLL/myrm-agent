"""[INPUT]
- Path parameters: chat_id
- Request bodies: ValidateOriginRequest, SetEmbedPolicyRequest, InjectHostContextRequest, GenerateSnippetRequest
- EmbedBridgeService: Domain service

[OUTPUT]
- POST /chats/embed/validate-origin: Validate host origin permission
- POST /chats/{chat_id}/embed/policy: Set embed security policy
- GET /chats/{chat_id}/embed/policy: Get embed security policy
- POST /chats/{chat_id}/embed/inject-context: Inject host webpage context
- GET /chats/{chat_id}/embed/context: Get latest injected context
- POST /chats/{chat_id}/embed/generate-snippet: Generate embed script snippet

[POS]
API route layer for Embeddable Agent Widget & Host Context Bridge (Item 41 P1).
Strictly under 200 lines. Zero `Any`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import error_response, success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.artifacts.embed_bridge import EmbedBridgeService

router = APIRouter()


class ValidateOriginRequest(BaseModel):
    origin: str = Field(..., min_length=1, description="Host origin URL (e.g., https://example.com)")
    chat_id: str | None = Field(default=None, description="Optional chat session ID for policy check")


class SetEmbedPolicyRequest(BaseModel):
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"], description="Allowed host origins")
    allow_form_capture: bool = Field(default=True, description="Whether to capture host active form fields")
    allow_selection_capture: bool = Field(default=True, description="Whether to capture selected text")


class InjectHostContextRequest(BaseModel):
    origin: str = Field(..., min_length=1, description="Host window origin")
    current_url: str = Field(..., min_length=1, description="Current host page URL")
    page_title: str = Field(default="", description="Host document title")
    selected_text: str = Field(default="", description="Selected text in host DOM")
    form_fields: dict[str, str] = Field(default_factory=dict, description="Active form inputs map")
    user_metadata: dict[str, str] = Field(default_factory=dict, description="Custom host metadata")


class GenerateSnippetRequest(BaseModel):
    base_url: str = Field(default="", description="Base URL of Myrm server")
    mode: Literal["floating_bubble", "slideout_drawer", "inline_container"] = Field(
        default="floating_bubble", description="Widget presentation mode"
    )
    theme: str = Field(default="light", description="Widget visual theme")
    allowed_origin: str = Field(default="*", description="Restricted embed origin")


@router.post("/embed/validate-origin", response_model=StandardSuccessResponse)
async def validate_host_origin(body: ValidateOriginRequest) -> JSONResponse:
    """Validates if the provided origin meets cross-origin bridge security policy."""
    svc = EmbedBridgeService.get_instance()
    is_valid = svc.validate_origin(body.origin, body.chat_id)
    return success_response(data={"valid": is_valid, "origin": body.origin})


@router.post("/{chat_id}/embed/policy", response_model=StandardSuccessResponse)
async def set_embed_policy(
    body: SetEmbedPolicyRequest,
    chat_id: str = Path(..., description="Chat session ID"),
) -> JSONResponse:
    """Configures embed security policy for a specific chat session."""
    svc = EmbedBridgeService.get_instance()
    policy = svc.set_security_policy(
        session_id=chat_id,
        allowed_origins=body.allowed_origins,
        allow_form_capture=body.allow_form_capture,
        allow_selection_capture=body.allow_selection_capture,
    )
    return success_response(data={
        "allowed_origins": policy.allowed_origins,
        "allow_form_capture": policy.allow_form_capture,
        "allow_selection_capture": policy.allow_selection_capture,
    })


@router.get("/{chat_id}/embed/policy", response_model=StandardSuccessResponse)
async def get_embed_policy(
    chat_id: str = Path(..., description="Chat session ID"),
) -> JSONResponse:
    """Retrieves embed security policy for a specific chat session."""
    svc = EmbedBridgeService.get_instance()
    policy = svc.get_security_policy(chat_id)
    return success_response(data={
        "allowed_origins": policy.allowed_origins,
        "allow_form_capture": policy.allow_form_capture,
        "allow_selection_capture": policy.allow_selection_capture,
    })


@router.post("/{chat_id}/embed/inject-context", response_model=StandardSuccessResponse)
async def inject_host_context(
    body: InjectHostContextRequest,
    chat_id: str = Path(..., description="Chat session ID"),
) -> JSONResponse:
    """Validates host origin and injects external page snapshot into the session."""
    svc = EmbedBridgeService.get_instance()
    try:
        injected = svc.inject_host_context(
            session_id=chat_id,
            origin=body.origin,
            current_url=body.current_url,
            page_title=body.page_title,
            selected_text=body.selected_text,
            form_fields=body.form_fields,
            user_metadata=body.user_metadata,
        )
    except PermissionError as exc:
        return error_response(code=403, message=str(exc))

    return success_response(data={
        "session_id": injected.session_id,
        "context_text": injected.context_text,
        "injected_at_ms": injected.injected_at_ms,
        "snapshot": {
            "origin": injected.snapshot.origin,
            "current_url": injected.snapshot.current_url,
            "page_title": injected.snapshot.page_title,
            "selected_text": injected.snapshot.selected_text,
            "form_fields": injected.snapshot.form_fields,
        },
    })


@router.get("/{chat_id}/embed/context", response_model=StandardSuccessResponse)
async def get_latest_host_context(
    chat_id: str = Path(..., description="Chat session ID"),
) -> JSONResponse:
    """Retrieves the latest injected host context for the session."""
    svc = EmbedBridgeService.get_instance()
    injected = svc.get_latest_context(chat_id)
    if injected is None:
        return success_response(data=None)

    return success_response(data={
        "session_id": injected.session_id,
        "context_text": injected.context_text,
        "injected_at_ms": injected.injected_at_ms,
        "snapshot": {
            "origin": injected.snapshot.origin,
            "current_url": injected.snapshot.current_url,
            "page_title": injected.snapshot.page_title,
            "selected_text": injected.snapshot.selected_text,
        },
    })


@router.post("/{chat_id}/embed/generate-snippet", response_model=StandardSuccessResponse)
async def generate_embed_snippet(
    request: Request,
    body: GenerateSnippetRequest,
    chat_id: str = Path(..., description="Chat session ID"),
) -> JSONResponse:
    """Generates a plug-and-play script embed snippet."""
    svc = EmbedBridgeService.get_instance()
    base_url = body.base_url.strip() or str(request.base_url).rstrip("/")
    snippet = svc.generate_embed_snippet(
        chat_id=chat_id,
        base_url=base_url,
        mode=body.mode,
        theme=body.theme,
        allowed_origin=body.allowed_origin,
    )
    return success_response(data={
        "chat_id": chat_id,
        "mode": body.mode,
        "theme": body.theme,
        "allowed_origin": body.allowed_origin,
        "snippet": snippet,
    })
