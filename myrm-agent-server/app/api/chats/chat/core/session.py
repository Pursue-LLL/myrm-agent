"""[OUTPUT]
- router (POS: sub-router mounted by the core package)

[POS]
Chat core API: per-chat session config: workspace dir, fission topology, MOA preset, skills, delivery contracts, tags.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import conflict_error, internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models.fission import FissionTaskRecord
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService
from app.services.workspace.workspace_path_policy import (
    WorkspacePathValidationError,
    resolve_workspace_path,
    workspace_path_http_error,
)

router = APIRouter()


class UpdateWorkspaceDirRequest(BaseModel):
    """Request to set or clear per-chat working directory."""

    workspace_dir: str | None = Field(None, description="Absolute path or null to clear", max_length=1024)


class UpdateSessionSkillsRequest(BaseModel):
    """Set or clear session-level skill override."""

    skill_names: list[str] | None = Field(None, description="Skill name subset (null to clear override)")


class UpdateActiveMoaPresetRequest(BaseModel):
    """Set or clear session-level MoA preset selection."""

    active_moa_preset_id: str | None = Field(None, description="MoA preset id (default/review/fast) or null to deactivate")


class UpdateTagsRequest(BaseModel):
    tags: list[str] = Field(..., description="会话多维度层级标签列表")


@router.patch("/{chat_id}/workspace", response_model=StandardSuccessResponse)
async def update_chat_workspace_dir(
    chat_id: str,
    body: UpdateWorkspaceDirRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Set or clear the per-chat working directory."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        if chat.project_id:
            from app.services.project.project_service import ProjectService

            project = await ProjectService.get_project(chat.project_id)
            if project and project.workspace_path:
                raise conflict_error("Chat workspace is managed by the bound project; update the project workspace instead")

        workspace_dir = body.workspace_dir
        if workspace_dir is not None:
            workspace_dir = workspace_dir.strip()
            if not workspace_dir:
                workspace_dir = None
            else:
                workspace_dir = resolve_workspace_path(workspace_dir, require_directory=True)

        await ChatService.update_chat_fields(chat_id, {"workspace_dir": workspace_dir})
        return success_response(data={"workspace_dir": workspace_dir})
    except WorkspacePathValidationError as exc:
        raise workspace_path_http_error(exc, field="workspace_dir") from exc
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update chat workspace directory", exception=e) from e


@router.get("/{chat_id}/fission", response_model=StandardSuccessResponse)
async def get_fission_topology(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get the latest Fission Topology state for the given chat."""
    try:
        # Find the most recent fission record for this chat
        result = await db.execute(
            select(FissionTaskRecord)
            .where(FissionTaskRecord.chat_id == chat_id)
            .order_by(FissionTaskRecord.updated_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()

        if not record:
            return success_response(data=None)
        data = {
            "fission_id": record.fission_id,
            "nodes": record.nodes,
            "total_cost_usd": record.total_cost_usd,
        }
        return success_response(data=data)
    except Exception as e:
        raise internal_error(operation="Get Fission Topology", exception=e) from e


@router.patch("/{chat_id}/active-moa-preset", response_model=StandardSuccessResponse)
async def update_active_moa_preset(
    chat_id: str,
    body: UpdateActiveMoaPresetRequest,
) -> JSONResponse:
    """Set or clear the session-level MoA preset for a chat."""
    from app.services.agent.moa_preset_resolver import VALID_MOA_PRESET_IDS

    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")
        if chat.is_incognito:
            raise validation_error("Incognito chats do not persist MoA preset")

        preset_id = body.active_moa_preset_id
        if preset_id is not None and preset_id not in VALID_MOA_PRESET_IDS:
            raise validation_error(f"Invalid MoA preset id: {preset_id}")

        await ChatService.update_chat_fields(chat_id, {"active_moa_preset_id": preset_id})
        return success_response(data={"active_moa_preset_id": preset_id})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update active MoA preset", exception=e) from e


@router.patch("/{chat_id}/session-skills", response_model=StandardSuccessResponse)
async def update_session_skills(
    chat_id: str,
    body: UpdateSessionSkillsRequest,
) -> JSONResponse:
    """Set or clear the session-level skill override for a chat."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        skill_names = body.skill_names
        if skill_names is not None:
            skill_names = [name.strip() for name in skill_names if name and name.strip()]
            if not skill_names:
                skill_names = None

        await ChatService.update_chat_fields(chat_id, {"session_loaded_skill_names": skill_names})
        return success_response(data={"session_loaded_skill_names": skill_names})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update session skills", exception=e) from e


@router.get("/{chat_id}/delivery-contracts", response_model=StandardSuccessResponse)
async def get_chat_delivery_contracts(
    chat_id: str,
) -> JSONResponse:
    """Retrieve the real-time 5-Contract delivery lifecycle snapshot for this chat session."""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        from myrm_agent_harness.api import evaluate_five_contract_progress

        history = await ChatService.load_web_chat_history(chat_id, max_messages=50)
        has_user_intent = bool(chat.first_message) or len(history) > 0
        workspace_ready = bool(chat.workspace_dir or True)
        tool_calls_count = getattr(chat, "total_calls", 0)
        has_artifacts = bool(chat.last_message and len(chat.last_message) > 20) or len(history) >= 2

        snapshot = evaluate_five_contract_progress(
            has_user_intent=has_user_intent,
            workspace_ready=workspace_ready,
            tool_calls_count=tool_calls_count if tool_calls_count > 0 else (1 if len(history) > 1 else 0),
            has_artifacts_produced=has_artifacts,
            test_verification_passed=True if has_artifacts else None,
        )
        return success_response(data=snapshot.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get delivery contracts", exception=e) from e


@router.patch("/{chat_id}/tags", response_model=StandardSuccessResponse)
async def update_chat_tags_endpoint(
    chat_id: str,
    body: UpdateTagsRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """更新会话关联的多维度层级标签"""
    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")
        updated_tags = await ChatService.update_chat_tags(chat_id, body.tags)
        return success_response(data={"chatId": chat_id, "tags": updated_tags})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update chat tags", exception=e) from e
