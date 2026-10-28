"""Session directory access API: grant and revoke one directory root of a chat.

[INPUT]
- app.services.agent.session_access_service (POS: grant/revoke with persistence and the deployment-boundary gate)
- app.services.chat.effective_workspace::resolve_effective_chat_workspace (POS: the workspace relative paths resolve against)

[OUTPUT]
- POST /{chat_id}/session-access-roots: grant one root; a grant the server refuses answers 403
- PATCH /{chat_id}/session-access-roots: revoke one root

[POS]
Directory-grant endpoints of a chat (desktop drag-and-drop and the approval card's grant list share the service).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import internal_error, not_found_error, permission_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()


class GrantSessionAccessRootRequest(BaseModel):
    """Grant one session-scoped directory access root."""

    path: str = Field(
        ...,
        description="Absolute or workspace-relative directory path to grant",
        min_length=1,
    )
    writable: bool = Field(
        default=True,
        description="Whether write access is granted",
    )
    label: str | None = Field(
        default=None,
        description="Optional display label for this grant",
    )


class RevokeSessionAccessRootRequest(BaseModel):
    """Revoke one session-scoped directory grant."""

    path: str = Field(
        ...,
        description="Absolute or workspace-relative directory path to revoke",
        min_length=1,
    )


@router.post("/{chat_id}/session-access-roots", response_model=StandardSuccessResponse)
async def grant_session_access_root_endpoint(
    chat_id: str,
    body: GrantSessionAccessRootRequest,
) -> JSONResponse:
    """Grant one directory root for this chat session (e.g. from desktop drag-and-drop)."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        from app.services.chat.effective_workspace import (
            resolve_effective_chat_workspace,
        )

        workspace_dir = await resolve_effective_chat_workspace(
            chat,
            jit_fallback=False,
        )

        from app.services.agent.session_access_service import (
            DirectoryGrantRefusedError,
            access_roots_to_json,
            grant_chat_session_access_root,
        )

        try:
            updated = await grant_chat_session_access_root(
                chat_id,
                body.path.strip(),
                writable=body.writable,
                label=body.label.strip() if body.label else "",
                workspace_dir=workspace_dir,
                sandbox_active=bool(chat.sandbox_base_dir),
            )
        except DirectoryGrantRefusedError as refusal:
            raise permission_error(str(refusal)) from refusal
        return success_response(data={"session_access_roots": access_roots_to_json(updated)})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Grant session access root", exception=e) from e


@router.patch("/{chat_id}/session-access-roots", response_model=StandardSuccessResponse)
async def revoke_session_access_root(
    chat_id: str,
    body: RevokeSessionAccessRootRequest,
) -> JSONResponse:
    """Revoke one HITL-granted directory root for this chat session."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        from app.services.chat.effective_workspace import (
            resolve_effective_chat_workspace,
        )

        workspace_dir = await resolve_effective_chat_workspace(
            chat,
            jit_fallback=False,
        )

        from app.services.agent.session_access_service import (
            access_roots_to_json,
            revoke_chat_session_access_root,
        )

        updated = await revoke_chat_session_access_root(
            chat_id,
            body.path.strip(),
            workspace_dir=workspace_dir,
        )
        return success_response(data={"session_access_roots": access_roots_to_json(updated)})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Revoke session access root", exception=e) from e
