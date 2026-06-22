"""智能体 API 接口

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent CRUD 服务)
services.agent.profile_snapshot_service::ProfileSnapshotService (POS: Agent 配置快照与回滚)
database.dto::AgentCreate, AgentUpdate, AgentResponse (POS: Agent API 契约)

[OUTPUT]
Agent CRUD、配置快照（GET /snapshots）、撤销（POST /rollback、POST /rollback/{id}）、
导出（GET /export，含凭据剔除与团队递归导出）、导入（POST /import，支持单体与团队原子导入）、
PUT 响应含 snapshot_count 与 snapshot_saved

[POS]
用户自定义智能体 HTTP 入口。GUI-first 配置 SSOT 的 API 层。
"""

import logging
import os
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any, TypeGuard, get_args

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from myrm_agent_harness.backends.profiles.types import AgentProfile
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_agents.personality_templates import DEFAULT_PERSONALITY_STYLE
from app.core.memory.adapters.policy import memory_policy_to_dict
from app.core.security.master_key import VaultLockedError
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
    AgentMemoryPolicyConfig,
    AgentProfileSnapshotItem,
    AgentResponse,
    AgentSessionPolicyConfig,
    AgentUpdate,
    CommandBindingConfig,
    ModelSelection,
    PaginatedResponse,
    PaginationMeta,
    PersonalityStyleLiteral,
    WorkspacePolicyLiteral,
)
from app.database.standard_responses import StandardSuccessResponse
from app.services.agent.agent_service import HIDDEN_SYSTEM_PROMPT, AgentService
from app.services.agent.backends import DatabaseSecretBackend

logger = logging.getLogger(__name__)


def _is_valid_personality(value: object) -> TypeGuard[PersonalityStyleLiteral]:
    return isinstance(value, str) and value in get_args(PersonalityStyleLiteral)


def _safe_personality(raw: object) -> PersonalityStyleLiteral:
    """Sanitize personality_style from DB, falling back to default for invalid values."""
    if _is_valid_personality(raw):
        return raw
    if _is_valid_personality(DEFAULT_PERSONALITY_STYLE):
        return DEFAULT_PERSONALITY_STYLE
    return "professional"


def _metadata_as_mapping(agent: AgentProfile) -> dict[str, object]:
    raw = agent.metadata
    if not raw:
        return {}
    return {str(k): v for k, v in raw.items()}


def _meta_str(meta: dict[str, object], key: str) -> str | None:
    v = meta.get(key)
    return v if isinstance(v, str) else None


def _meta_str_list(meta: dict[str, object], key: str, *, default: list[str] | None = None) -> list[str]:
    v = meta.get(key)
    if isinstance(v, list):
        return [str(x) for x in v]
    return list(default or [])


def _meta_str_list_or_none(meta: dict[str, object], key: str) -> list[str] | None:
    v = meta.get(key)
    if v is None:
        return None
    if isinstance(v, list):
        return [str(x) for x in v]
    return None


def _meta_dict_or_none(meta: dict[str, object], key: str) -> dict[str, object] | None:
    v = meta.get(key)
    if isinstance(v, dict):
        return {str(k2): val for k2, val in v.items()}
    return None


def _meta_list_or_empty(meta: dict[str, object], key: str) -> list[dict[str, object]]:
    v = meta.get(key)
    if isinstance(v, list):
        return [item for item in v if isinstance(item, dict)]
    return []


def _meta_list_or_none(meta: dict[str, object], key: str) -> list[dict[str, str]] | None:
    v = meta.get(key)
    if isinstance(v, list) and v:
        return [item for item in v if isinstance(item, dict)]
    return None


_WORKSPACE_POLICY_MAP: dict[str, WorkspacePolicyLiteral] = {
    "ISOLATED_COPY": "ISOLATED_COPY",
    "READ_ONLY_SANDBOX": "READ_ONLY_SANDBOX",
}


def _workspace_policy_from_metadata(raw: object) -> WorkspacePolicyLiteral:
    return _WORKSPACE_POLICY_MAP.get(str(raw), "INHERIT_REQUESTER") if raw else "INHERIT_REQUESTER"


def _response_memory_policy(agent: AgentProfile) -> AgentMemoryPolicyConfig | None:
    raw = memory_policy_to_dict(agent.memory_policy)
    if raw is None:
        return None
    return AgentMemoryPolicyConfig.model_validate(raw)


def _response_session_policy(metadata: dict[str, object]) -> AgentSessionPolicyConfig | None:
    raw = metadata.get("session_policy")
    if not isinstance(raw, dict):
        return None
    return AgentSessionPolicyConfig.model_validate(raw)


router = APIRouter()


class AgentCloneRequest(BaseModel):
    name: str | None = None


class AgentSecretCreate(BaseModel):
    key_name: str
    secret_value: str


class AgentSecretResponse(BaseModel):
    key_name: str


def _get_secret_backend() -> DatabaseSecretBackend:
    """Create a secret backend on demand.

    Secret routes require an unlocked vault, but ordinary agent CRUD must
    remain available even when the vault is still locked.
    """
    try:
        return DatabaseSecretBackend()
    except VaultLockedError as exc:
        raise HTTPException(
            status_code=423,
            detail="Vault is locked. Provide MYRM_MASTER_KEY, configure OS keyring, or unlock via API.",
        ) from exc


def _build_model_selection(model: str | None, metadata: dict[str, object]) -> ModelSelection | None:
    """Build ModelSelection from stored model_selection JSON or fallback to basic."""
    full = metadata.get("model_selection_full")
    if isinstance(full, dict) and full.get("model"):
        return ModelSelection(
            providerId=full.get("providerId", "auto"),
            model=full["model"],
            fallbackProviderId=full.get("fallbackProviderId"),
            fallbackModel=full.get("fallbackModel"),
            safetyFallbackProviderId=full.get("safetyFallbackProviderId"),
            safetyFallbackModel=full.get("safetyFallbackModel"),
            modelKwargs=full.get("modelKwargs"),
        )
    if model:
        return ModelSelection(providerId="auto", model=model)
    return None


def _to_agent_response(
    agent: AgentProfile,
    show_system_prompt: bool = False,
    snapshot_count: int = 0,
    snapshot_saved: bool | None = None,
) -> AgentResponse:
    """Convert AgentProfile to API response.

    Args:
        agent: AgentProfile from Harness
        show_system_prompt: If True, include system_prompt in response (default: False for security)

    Returns:
        AgentResponse with system_prompt hidden by default
    """
    metadata = _metadata_as_mapping(agent)
    system_prompt = agent.system_prompt

    enabled_tools: list[str] | None
    if agent.tools_allowed is not None:
        enabled_tools = list(agent.tools_allowed)
    else:
        enabled_tools = _meta_str_list_or_none(metadata, "enabled_builtin_tools")

    return AgentResponse(
        id=agent.id,
        user_id="local",  # Single-tenant
        name=agent.display_name or agent.id,
        description=agent.description,
        avatar_url=agent.avatar,
        home_directory=_meta_str(metadata, "home_directory"),
        is_built_in=agent.built_in,
        agent_type=metadata.get("agent_type", "individual") or "individual",
        system_prompt=system_prompt if show_system_prompt else HIDDEN_SYSTEM_PROMPT,
        mcp_ids=_meta_str_list(metadata, "mcp_ids", default=[]),
        mcp_tool_selections=_meta_dict_or_none(metadata, "mcp_tool_selections"),
        skill_ids=agent.skills or [],
        skill_configs=agent.skill_configs,
        enabled_builtin_tools=enabled_tools,
        browser_engine=_meta_str(metadata, "browser_engine"),
        browser_source=_meta_str(metadata, "browser_source"),
        dialog_policy=_meta_str(metadata, "dialog_policy"),
        session_recording=_meta_str(metadata, "session_recording"),
        auto_restore_domains=_meta_str_list(metadata, "auto_restore_domains", default=[]),
        suggestion_prompts=_meta_str_list_or_none(metadata, "suggestion_prompts"),
        model_selection=_build_model_selection(agent.model, metadata),
        security_overrides=_meta_dict_or_none(metadata, "security_overrides"),
        prompt_mode=metadata.get("prompt_mode", "full") or "full",
        personality_style=_safe_personality(metadata.get("personality_style")),
        subagent_ids=_meta_str_list(metadata, "subagent_ids", default=[]),
        max_iterations=agent.max_iterations,
        workspace_policy=_workspace_policy_from_metadata(metadata.get("workspace_policy", "INHERIT_REQUESTER")),
        memory_policy=_response_memory_policy(agent),
        session_policy=_response_session_policy(metadata),
        engine_params=_meta_dict_or_none(metadata, "engine_params"),
        openapi_services=_meta_list_or_empty(metadata, "openapi_services"),
        command_bindings=(
            [
                CommandBindingConfig(
                    command_name=b.command_name,
                    skill_ids=list(b.skill_ids),
                    description=b.description,
                    aliases=list(b.aliases),
                    instruction=b.instruction,
                )
                for b in agent.command_bindings
            ]
            if agent.command_bindings
            else None
        ),
        notify_targets=_meta_list_or_none(metadata, "notify_targets"),
        created_at=agent.created_at or datetime.now(),
        updated_at=agent.updated_at or datetime.now(),
        snapshot_count=snapshot_count,
        snapshot_saved=snapshot_saved,
    )


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
                agent_type=_metadata_as_mapping(agent).get("agent_type", "individual") or "individual",
                model_selection=_build_model_selection(agent.model, _metadata_as_mapping(agent)),
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

        paginated_data = PaginatedResponse[AgentListItem](items=agent_items, pagination=pagination_meta)

        return success_response(data=paginated_data.model_dump())
    except Exception as e:
        raise internal_error(operation="Get agent list", exception=e) from e


@router.get("/{agent_id}", response_model=StandardSuccessResponse)
async def get_agent(
    agent_id: str,
    show_system_prompt: bool = Query(False, description="Show system prompt (hidden by default for security)"),
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

        # Security: Only agent owner can view system prompt
        # In sandbox mode, user is the owner
        # if show_system_prompt and agent.user_id != user_id:
        #     raise HTTPException(
        #         status_code=403,
        #         detail="Only the agent owner can view the system prompt",
        #     )

        # Audit log: Record system prompt viewing
        if show_system_prompt:
            import logging

            audit_logger = logging.getLogger("audit")
            audit_logger.info(f"System prompt viewed - agent_id={agent_id}, agent_name={agent.display_name}")

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
    except Exception as e:
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


_SENSITIVE_AUTH_FIELDS = frozenset({"api_key", "bearer_token", "client_secret", "password", "username"})


def _strip_sensitive_auth(export_data: dict[str, Any]) -> None:
    """Remove credential values from exported agent config in-place.

    Strips openapi_services[].auth sensitive fields and
    tool_gateway_config.auth_token to prevent credential leaks.
    """
    for svc in export_data.get("openapi_services") or []:
        if not isinstance(svc, dict):
            continue
        auth = svc.get("auth")
        if not isinstance(auth, dict):
            continue
        for key in _SENSITIVE_AUTH_FIELDS:
            auth.pop(key, None)

    gw = export_data.get("tool_gateway_config")
    if isinstance(gw, dict):
        gw.pop("auth_token", None)


async def _export_single_agent(agent_id: str) -> dict[str, Any]:
    """Build a sanitised export dict for one agent (strips secrets)."""
    agent = await AgentService.get_agent_by_id(agent_id)
    if not agent:
        raise not_found_error("Agent")
    agent_resp = _to_agent_response(agent, show_system_prompt=True)
    data = agent_resp.model_dump(exclude={"id", "user_id", "created_at", "updated_at"})
    _strip_sensitive_auth(data)
    return data


@router.get("/{agent_id}/export", response_model=StandardSuccessResponse)
async def export_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """导出智能体配置为 JSON（自动剔除凭据、递归导出团队成员）"""
    try:
        leader_data = await _export_single_agent(agent_id)

        if leader_data.get("agent_type") == "team":
            member_ids: list[str] = leader_data.get("subagent_ids") or []  # type: ignore[assignment]
            members: list[dict[str, Any]] = []
            for mid in member_ids:
                try:
                    members.append(await _export_single_agent(mid))
                except HTTPException:
                    logger.warning("Skipping missing subagent %s during team export", mid)
            return success_response(data={
                "_export_version": 1,
                "agent_type": "team",
                "leader": leader_data,
                "members": members,
            })

        return success_response(data=leader_data)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Export agent", exception=e) from e


@router.post("/{agent_id}/clone", response_model=StandardSuccessResponse)
async def clone_agent(
    agent_id: str,
    body: AgentCloneRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Clone an agent with a new identity, reusing its full configuration."""
    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        agent_resp = _to_agent_response(agent, show_system_prompt=True)
        clone_data = agent_resp.model_dump(exclude={"id", "user_id", "created_at", "updated_at"})

        clone_data["home_directory"] = None

        if isinstance(clone_data.get("avatar_url"), str) and clone_data["avatar_url"].startswith("home://"):
            clone_data["avatar_url"] = None

        original_name = clone_data.get("name") or "Agent"
        clone_data["name"] = body.name if body and body.name else f"{original_name} (Copy)"
        clone_data["is_built_in"] = False

        new_agent_data = AgentCreate.model_validate(clone_data)
        new_agent = await AgentService.create_agent(new_agent_data)
        return success_response(data=_to_agent_response(new_agent).model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Clone agent", exception=e) from e


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
        return success_response(data={"message": "Agent profile rolled back successfully."})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Rollback agent profile", exception=e) from e


@router.post("/{agent_id}/rollback/{snapshot_id}", response_model=StandardSuccessResponse)
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
        return success_response(data={"message": "Agent profile rolled back successfully."})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Rollback agent profile to snapshot", exception=e) from e


@router.post("/import", response_model=StandardSuccessResponse)
async def import_agent(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """导入智能体配置（支持单体和团队两种格式）"""
    try:
        if body.get("_export_version") and body.get("agent_type") == "team":
            return await _import_team_agent(body)
        return await _import_single_agent(body)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Import agent", exception=e) from e


async def _import_single_agent(data: dict[str, Any]) -> JSONResponse:
    """Import a single (non-team) agent from export dict."""
    agent_data = AgentCreate.model_validate(data)
    if not agent_data.name or not agent_data.name.strip():
        raise validation_error("Agent name cannot be empty")
    agent_data.is_built_in = False
    agent = await AgentService.create_agent(agent_data)
    return success_response(data=_to_agent_response(agent).model_dump())


async def _import_team_agent(data: dict[str, Any]) -> JSONResponse:
    """Import a team agent with all members atomically."""
    leader_raw = data.get("leader")
    members_raw = data.get("members")
    if not isinstance(leader_raw, dict) or not isinstance(members_raw, list):
        raise validation_error("Invalid team export format: missing leader or members")

    leader_data = AgentCreate.model_validate(leader_raw)
    if not leader_data.name or not leader_data.name.strip():
        raise validation_error("Team leader name cannot be empty")
    leader_data.is_built_in = False

    created_member_ids: list[str] = []
    try:
        for member_raw in members_raw:
            if not isinstance(member_raw, dict):
                continue
            m_data = AgentCreate.model_validate(member_raw)
            m_data.is_built_in = False
            m_data.agent_type = "individual"
            m_agent = await AgentService.create_agent(m_data)
            created_member_ids.append(m_agent.id)

        leader_data.subagent_ids = created_member_ids
        leader_data.agent_type = "team"
        leader = await AgentService.create_agent(leader_data)
        return success_response(data=_to_agent_response(leader).model_dump())
    except Exception:
        for mid in created_member_ids:
            try:
                await AgentService.delete_agent(mid)
            except Exception:
                logger.warning("Rollback: failed to delete member %s", mid)
        raise


@router.post("/{agent_id}/avatar", response_model=StandardSuccessResponse)
async def upload_agent_avatar(
    agent_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """上传智能体头像

    支持的格式: image/png, image/jpeg, image/svg+xml
    最大文件大小: 5MB
    """

    try:
        # Verify agent ownership
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        # Validate file type
        allowed_types = [
            "image/png",
            "image/jpeg",
            "image/svg+xml",
            "image/gif",
            "image/webp",
        ]
        if file.content_type not in allowed_types:
            raise validation_error(f"Unsupported file type: {file.content_type}. Allowed: {', '.join(allowed_types)}")

        # Validate file size (5MB max)
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:
            raise validation_error("File size exceeds 5MB limit")

        # Save avatar to agent home directory
        agent_home = _meta_str(_metadata_as_mapping(agent), "home_directory")
        if not agent_home:
            agent_home = str(Path.home() / ".myrm" / "agents" / agent_id)
        os.makedirs(agent_home, exist_ok=True)

        # Determine file extension
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

        # Write file
        with open(avatar_path, "wb") as f:
            f.write(content)

        # Update agent avatar_url to home:// reference
        avatar_url = f"home://{avatar_filename}"

        await AgentService.update_agent(agent_id, AgentUpdate.model_validate({"avatar_url": avatar_url}))

        return success_response(data={"avatar_url": avatar_url, "local_path": avatar_path})
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


@router.get("/{agent_id}/secrets", response_model=StandardSuccessResponse)
async def get_agent_secrets(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取智能体的所有机密名称（不返回明文）"""

    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        secret_manager = _get_secret_backend()
        secrets_dict = await secret_manager.get_all_secrets(agent_id)
        keys = list(secrets_dict.keys())
        return success_response(data=[{"key_name": k} for k in keys])
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get agent secrets", exception=e) from e


@router.post("/{agent_id}/secrets", response_model=StandardSuccessResponse)
async def create_agent_secret(
    agent_id: str,
    secret_data: AgentSecretCreate,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """创建或更新智能体机密"""

    if not secret_data.key_name or not secret_data.secret_value:
        raise validation_error("Key name and secret value are required")

    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        secret_manager = _get_secret_backend()
        await secret_manager.save_secret(agent_id, secret_data.key_name, secret_data.secret_value)
        return success_response(data={"key_name": secret_data.key_name})
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Create agent secret", exception=e) from e


@router.delete("/{agent_id}/secrets/{key_name}", response_model=StandardSuccessResponse)
async def delete_agent_secret(
    agent_id: str,
    key_name: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """删除智能体机密"""

    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        secret_manager = _get_secret_backend()
        success = await secret_manager.delete_secret(agent_id, key_name)
        if not success:
            raise not_found_error("Agent Secret")

        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Delete agent secret", exception=e) from e


@router.get("/{agent_id}/statistics", response_model=StandardSuccessResponse)
async def get_agent_statistics(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """获取智能体使用统计

    Returns:
        - total_sessions: 总会话数
        - total_messages: 总消息数
        - last_used_at: 最后使用时间
    """

    try:
        # Verify agent ownership
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        # Import here to avoid circular dependency
        from app.database.models import Chat, Message

        # Count sessions where this agent was used
        sessions_result = await db.execute(select(func.count(Chat.id)).where(Chat.agent_id == agent_id))
        total_sessions = sessions_result.scalar_one()

        # Count total messages in agent's sessions
        messages_result = await db.execute(
            select(func.count(Message.id)).join(Chat, Message.chat_id == Chat.id).where(Chat.agent_id == agent_id)
        )
        total_messages = messages_result.scalar_one()

        # Get last used time
        last_chat_result = await db.execute(
            select(Chat.updated_at).where(Chat.agent_id == agent_id).order_by(desc(Chat.updated_at)).limit(1)
        )
        last_used_at = last_chat_result.scalar_one_or_none()

        statistics = {
            "agent_id": agent_id,
            "agent_name": agent.display_name or agent.id,
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "last_used_at": last_used_at.isoformat() if last_used_at else None,
        }

        return success_response(data=statistics)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Get agent statistics", exception=e) from e


class ActionSpaceEvalRequest(BaseModel):
    skill_ids: list[str]
    skill_configs: dict[str, dict] = {}
    mcp_servers: list[str]
    enabled_builtin_tools: list[str]


@router.post("/evaluate-action-space")
async def evaluate_action_space(
    req: ActionSpaceEvalRequest,
) -> JSONResponse:
    """评估给定工具集的动作空间复杂度 (Action Space Complexity Score - ASCS)"""
    try:
        from myrm_agent_harness.agent.tool_management.action_space import (
            ActionSpaceProfiler,
        )

        from app.core.skills.store.service import SkillsService

        total_score = 0

        # 1. 计算核心与外围技能复杂度
        for skill_id in req.skill_ids:
            is_core = req.skill_configs.get(skill_id, {}).get("is_core", True)
            skill = await SkillsService.get_skill_by_id(skill_id)
            if skill:
                # API 层采用极速启发式估算，避免阻断 UI 线程去实例化厚重的 Python Tool 对象
                cost = ActionSpaceProfiler.BASE_TOOL_COST + (len(skill.description or "") // 50)
                if not is_core:
                    cost = int(cost * 0.5)  # 外围工具因按需加载，常驻认知负载减半
                total_score += cost

        # 2. 计算外部不可预知的工具负担 (MCP & Built-ins)
        total_score += ActionSpaceProfiler.estimate_external_load(
            mcp_count=len(req.mcp_servers), builtin_count=len(req.enabled_builtin_tools)
        )

        # 根据 ASCS 科学计算出 0-100 的“认知负载”百分比
        max_safe_score = 1500
        noise_level = min(100, round((total_score / max_safe_score) * 100))
        accuracy_level = 100 - noise_level

        return success_response(
            data={
                "ascs_score": total_score,
                "max_safe_score": max_safe_score,
                "accuracy_level": accuracy_level,
                "is_critical": noise_level >= 80,
                "is_high": noise_level > 50,
            }
        )
    except Exception as e:
        raise internal_error(operation="Evaluate Action Space", exception=e) from e
