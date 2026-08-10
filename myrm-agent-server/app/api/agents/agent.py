"""Agent core CRUD, snapshots, avatar, file-serve endpoints.

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent CRUD 服务)
services.agent.profile.profile_snapshot_service::ProfileSnapshotService (POS: Agent 配置快照与回滚)
database.dto::AgentCreate, AgentUpdate, AgentResponse (POS: Agent API 契约)
_agent_response::_to_agent_response, _metadata_as_mapping (POS: 序列化共享层)
services.agent.external_cli_gate::ExternalCliBackendUnavailableError (POS: 外部 CLI 后端不可用异常)
services.agent.skill_instance_resolver::SkillConfigValidationError (POS: Skill 配置校验异常)

[OUTPUT]
Agent CRUD（list/get/create/update/delete）、配置快照（GET /snapshots）、
撤销（POST /rollback）、Avatar 上传、文件服务。

[POS]
用户自定义智能体核心 HTTP 端点。GUI-first 配置 SSOT 的 API 层。
"""

import logging
import os
from math import ceil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agents._agent_response import (
    _build_model_selection,
    _meta_str,
    _metadata_as_mapping,
    _resolve_enabled_builtin_tools,
    _to_agent_response,
)
from app.core.utils.errors import (
    internal_error,
    not_found_error,
    permission_error,
    validation_error,
)
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import (
    AgentCreate,
    AgentListItem,
    AgentProfileSnapshotItem,
    AgentUpdate,
    PaginatedResponse,
    PaginationMeta,
)
from app.schemas.responses import StandardSuccessResponse
from app.services.agent.agent_service import AgentService
from app.services.agent.external_cli_gate import ExternalCliBackendUnavailableError
from app.services.agent.skill_instance_resolver import SkillConfigValidationError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=StandardSuccessResponse)
async def get_agents(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量，1-100"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取用户的智能体列表（支持分页）"""
    try:
        agents, total = await AgentService.get_agent_list(page, page_size)

        agent_items = [
            AgentListItem(
                id=agent.id,
                name=agent.display_name or agent.id,
                description=agent.description,
                avatar_url=agent.avatar,
                is_built_in=agent.built_in,
                agent_type=_metadata_as_mapping(agent).get("agent_type", "individual")
                or "individual",
                prompt_mode=_metadata_as_mapping(agent).get("prompt_mode", "full")
                or "full",
                enabled_builtin_tools=_resolve_enabled_builtin_tools(agent),
                model_selection=_build_model_selection(
                    agent.model, _metadata_as_mapping(agent)
                ),
                created_at=agent.created_at,
                updated_at=agent.updated_at,
            )
            for agent in agents
        ]

        total_pages = ceil(total / page_size) if total > 0 else 1
        pagination_meta = PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )

        paginated_data = PaginatedResponse[AgentListItem](
            items=agent_items, pagination=pagination_meta
        )

        return success_response(data=paginated_data.model_dump())
    except Exception as e:
        raise internal_error(operation="Get agent list", exception=e) from e


@router.get("/{agent_id}", response_model=StandardSuccessResponse)
async def get_agent(
    agent_id: str,
    show_system_prompt: bool = Query(
        False, description="Show system prompt (hidden by default for security)"
    ),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取智能体详情

    Security: System prompt is hidden by default. Set show_system_prompt=true to reveal it.
    Only the agent owner can view the system prompt.
    """
    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        if show_system_prompt:
            audit_logger = logging.getLogger("audit")
            audit_logger.info(
                f"System prompt viewed - agent_id={agent_id}, agent_name={agent.display_name}"
            )

        return success_response(
            data=_to_agent_response(
                agent,
                show_system_prompt=show_system_prompt,
                snapshot_count=await AgentService.count_profile_snapshots(agent_id),
            ).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get agent", exception=e) from e


@router.post("", response_model=StandardSuccessResponse)
async def create_agent(
    agent_data: AgentCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """创建智能体"""
    if not agent_data.name or not agent_data.name.strip():
        raise validation_error("Agent name cannot be empty")

    try:
        agent = await AgentService.create_agent(agent_data)
        return success_response(data=_to_agent_response(agent).model_dump())
    except HTTPException:
        raise
    except Exception as e:
        if isinstance(e, ExternalCliBackendUnavailableError):
            raise validation_error(str(e)) from e
        if isinstance(e, SkillConfigValidationError):
            raise validation_error(str(e)) from e
        raise internal_error(operation="Create agent", exception=e) from e


@router.put("/{agent_id}", response_model=StandardSuccessResponse)
async def update_agent(
    agent_id: str,
    agent_data: AgentUpdate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """更新智能体"""
    if agent_data.name is not None and not agent_data.name.strip():
        raise validation_error("Agent name cannot be empty")

    try:
        existing = await AgentService.get_agent_by_id(agent_id)
        if not existing:
            raise not_found_error("Agent")
        if existing.built_in:
            raise permission_error("Built-in agents cannot be modified")

        outcome = await AgentService.update_agent(agent_id, agent_data)
        if not outcome:
            raise not_found_error("Agent")

        return success_response(
            data=_to_agent_response(
                outcome.profile,
                snapshot_count=await AgentService.count_profile_snapshots(agent_id),
                snapshot_saved=outcome.snapshot_saved,
            ).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        if isinstance(e, ExternalCliBackendUnavailableError):
            raise validation_error(str(e)) from e
        if isinstance(e, SkillConfigValidationError):
            raise validation_error(str(e)) from e
        raise internal_error(operation="Update agent", exception=e) from e


@router.delete("/{agent_id}", response_model=StandardSuccessResponse)
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """删除智能体"""
    try:
        success = await AgentService.delete_agent(agent_id)
        if not success:
            raise not_found_error("Agent")

        return success_response()
    except PermissionError as e:
        raise permission_error(str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Delete agent", exception=e) from e


@router.get("/{agent_id}/snapshots", response_model=StandardSuccessResponse)
async def list_agent_snapshots(
    agent_id: str,
    limit: int = Query(10, ge=1, le=10, description="Max snapshots to return"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """List agent profile snapshots for time-machine rollback."""
    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        snapshots = await AgentService.list_profile_snapshots(agent_id, limit=limit)
        items = [
            AgentProfileSnapshotItem(
                id=s.id,
                agent_id=s.agent_id,
                reason=s.reason,
                snapshot_data=s.snapshot_data,
                created_at=s.created_at,
            ).model_dump()
            for s in snapshots
        ]
        return success_response(data=items)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="List agent snapshots", exception=e) from e


@router.post("/{agent_id}/rollback", response_model=StandardSuccessResponse)
async def rollback_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Rollback agent profile to the last auto-saved snapshot."""
    try:
        success = await AgentService.rollback_profile(agent_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="No snapshot found for rollback or agent missing.",
            )
        return success_response(
            data={"message": "Agent profile rolled back successfully."}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Rollback agent profile", exception=e) from e


@router.post(
    "/{agent_id}/rollback/{snapshot_id}", response_model=StandardSuccessResponse
)
async def rollback_agent_to_snapshot(
    agent_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Rollback agent profile to a specific snapshot."""
    try:
        success = await AgentService.rollback_profile_to_snapshot(agent_id, snapshot_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Snapshot not found or agent missing.",
            )
        return success_response(
            data={"message": "Agent profile rolled back successfully."}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(
            operation="Rollback agent profile to snapshot", exception=e
        ) from e


@router.post("/{agent_id}/avatar", response_model=StandardSuccessResponse)
async def upload_agent_avatar(
    agent_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """上传智能体头像（支持 png/jpeg/svg/gif/webp，最大 5MB）"""
    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        allowed_types = [
            "image/png",
            "image/jpeg",
            "image/svg+xml",
            "image/gif",
            "image/webp",
        ]
        if file.content_type not in allowed_types:
            raise validation_error(
                f"Unsupported file type: {file.content_type}. Allowed: {', '.join(allowed_types)}"
            )

        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise validation_error("File size exceeds 5MB limit")

        agent_home = _meta_str(_metadata_as_mapping(agent), "home_directory")
        if not agent_home:
            agent_home = str(Path.home() / ".myrm" / "agents" / agent_id)
        os.makedirs(agent_home, exist_ok=True)

        ext_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/svg+xml": "svg",
            "image/gif": "gif",
            "image/webp": "webp",
        }
        ext = ext_map.get(file.content_type, "png")
        avatar_filename = f"avatar.{ext}"
        avatar_path = os.path.join(agent_home, avatar_filename)

        with open(avatar_path, "wb") as f:
            f.write(content)

        avatar_url = f"home://{avatar_filename}"

        await AgentService.update_agent(
            agent_id, AgentUpdate.model_validate({"avatar_url": avatar_url})
        )

        return success_response(
            data={"avatar_url": avatar_url, "local_path": avatar_path}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Upload agent avatar", exception=e) from e


@router.get("/{agent_id}/files/{filename:path}")
async def get_agent_file(
    agent_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve files from an agent's home directory (e.g. avatar images)."""
    agent = await AgentService.get_agent_by_id(agent_id)
    if not agent:
        raise not_found_error("Agent")

    agent_home = _meta_str(_metadata_as_mapping(agent), "home_directory")
    if not agent_home:
        agent_home = str(Path.home() / ".myrm" / "agents" / agent_id)

    try:
        from myrm_agent_harness.agent.security.path_security import safe_join_path

        file_path = safe_join_path(agent_home, filename)
    except ValueError as exc:
        raise validation_error("Invalid file path") from exc

    if not file_path.is_file():
        raise not_found_error("File")

    return FileResponse(file_path)
