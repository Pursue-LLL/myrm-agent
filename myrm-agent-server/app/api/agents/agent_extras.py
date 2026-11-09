"""Agent auxiliary endpoints — secrets, statistics, action-space evaluation.

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent CRUD 服务)
services.agent.backends::DatabaseSecretBackend (POS: Agent Secrets 加密存储)
services.agent.builtin_specs.builtin_tool_validation::RequiredBuiltinTools (POS: 内建工具类型)
core.skills.loader::create_skill_backend (POS: 与 Agent 运行时同一份技能后端组装，Turn1 预览的技能来源)
core.security.master_key::MasterKeyProvider (POS: 安全金库密钥派生模块)
core.security.master_key::VaultLockedError (POS: 缺少主密钥时抛出，携带当前状态)
api.security.vault_errors::vault_locked_error (POS: Vault HTTP 错误映射)

[OUTPUT]
- GET    /{agent_id}/secrets: 列出 Agent 机密名称（不含明文）
- POST   /{agent_id}/secrets: 创建/更新 Agent 机密
- DELETE /{agent_id}/secrets/{key_name}: 删除 Agent 机密
- GET    /{agent_id}/statistics: Agent 使用统计（会话/消息/最后使用）
- POST   /evaluate-action-space: 动作空间复杂度 ASCS 评估 + Turn1 catalog_preview（inline/hidden/search_mounted）

[POS]
Agent 辅助端点。Secrets 管理、使用统计、动作空间复杂度评估。机密端点依赖金库，锁定或仍在解析时返回 423；其余端点不受金库状态影响。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security.vault_errors import vault_locked_error
from app.core.security.master_key import MasterKeyProvider, VaultLockedError
from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.schemas.responses import StandardSuccessResponse
from app.services.agent.agent_service import AgentService
from app.services.agent.backends import DatabaseSecretBackend
from app.services.agent.builtin_specs.builtin_tool_validation import RequiredBuiltinTools

router = APIRouter()


class AgentSecretCreate(BaseModel):
    key_name: str
    secret_value: str


class AgentSecretResponse(BaseModel):
    key_name: str


async def _secret_backend() -> DatabaseSecretBackend:
    """Create a secret backend on demand.

    Secret routes require an unlocked vault, but ordinary agent CRUD must
    remain available even when the vault is still locked.
    """
    try:
        return DatabaseSecretBackend(master_key=await MasterKeyProvider.ensure_master_key(grace_sec=0))
    except VaultLockedError as exc:
        raise vault_locked_error(exc) from exc


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

        secret_manager = await _secret_backend()
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

        secret_manager = await _secret_backend()
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

        secret_manager = await _secret_backend()
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
    """获取智能体使用统计（会话数、消息数、最后使用时间）"""
    try:
        agent = await AgentService.get_agent_by_id(agent_id)
        if not agent:
            raise not_found_error("Agent")

        from app.database.models import Chat, Message

        sessions_result = await db.execute(select(func.count(Chat.id)).where(Chat.agent_id == agent_id))
        total_sessions = sessions_result.scalar_one()

        messages_result = await db.execute(
            select(func.count(Message.id)).join(Chat, Message.chat_id == Chat.id).where(Chat.agent_id == agent_id)
        )
        total_messages = messages_result.scalar_one()

        last_chat_result = await db.execute(
            select(Chat.updated_at).where(Chat.agent_id == agent_id).order_by(Chat.updated_at.desc()).limit(1)
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
    skill_configs: dict[str, dict[str, object]] = {}
    mcp_servers: list[str]
    enabled_builtin_tools: RequiredBuiltinTools


async def _build_catalog_preview(
    skill_ids: list[str],
    skill_configs: dict[str, dict[str, object]],
) -> dict[str, int | bool]:
    """Turn1 bound-skill catalog preview — the skills, resolver and renderer the agent runtime runs.

    The skills come out of the same backend composition the agent factories build (`create_skill_backend` +
    `load_skills`), so a skill counts once, under the name the model sees, with the runtime's availability verdict.
    Workspace, MCP and trust overrides depend on the session and are not part of the preview.
    """
    from myrm_agent_harness.agent.skills.runtime.catalog_display import (
        resolve_catalog_display_skills,
        should_mount_skill_search_tool,
    )
    from myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery import render_bound_skills_catalog
    from myrm_agent_harness.backends.skills.types import SkillMetadata
    from myrm_agent_harness.utils.text_utils import get_token_count

    from app.core.skills.effective_skill_ids import resolve_runtime_skill_ids
    from app.core.skills.loader import create_skill_backend
    from app.core.skills.store.service import skills_service

    runtime_skill_ids = await resolve_runtime_skill_ids(skill_ids)
    skills: list[SkillMetadata] = []
    if runtime_skill_ids:
        user_config = await skills_service.user_config.get_config()
        backend = await create_skill_backend(
            storage=skills_service.storage,
            skill_ids=runtime_skill_ids,
            user_id="default",
            allowed_prebuilt_ids=frozenset(user_config.enabled_prebuilt_ids),
        )
        skills = await backend.load_skills(runtime_skill_ids)

    resolution = resolve_catalog_display_skills(skills, skill_configs=skill_configs)
    rendered = render_bound_skills_catalog(skills, skill_configs=skill_configs)
    search_mounted = bool(skills) and should_mount_skill_search_tool(skills, skill_configs=skill_configs)
    return {
        "inline_count": len(resolution.display_skills),
        "hidden_count": resolution.hidden_skill_count,
        "overflow_count": resolution.overflow_count,
        "catalog_tokens": get_token_count(rendered.xml) if rendered is not None else 0,
        "search_mounted": search_mounted,
    }


@router.post("/evaluate-action-space")
async def evaluate_action_space(
    req: ActionSpaceEvalRequest,
) -> JSONResponse:
    """评估给定工具集的动作空间复杂度 (Action Space Complexity Score - ASCS)"""
    try:
        from myrm_agent_harness.agent.tool_management.action_space import (
            ActionSpaceProfiler,
        )

        from app.core.skills.store.service import skills_service

        total_score = 0

        for skill in await skills_service.get_skills_by_ids(skill_ids=req.skill_ids):
            is_core = req.skill_configs.get(skill.id, {}).get("is_core", True)
            cost = ActionSpaceProfiler.BASE_TOOL_COST + (len(skill.description or "") // 50)
            if not is_core:
                cost = int(cost * 0.5)
            total_score += cost

        total_score += ActionSpaceProfiler.estimate_external_load(
            mcp_count=len(req.mcp_servers),
            builtin_count=len(req.enabled_builtin_tools),
        )

        max_safe_score = 1500
        noise_level = min(100, round((total_score / max_safe_score) * 100))
        accuracy_level = 100 - noise_level

        catalog_preview = await _build_catalog_preview(req.skill_ids, req.skill_configs)

        return success_response(
            data={
                "ascs_score": total_score,
                "max_safe_score": max_safe_score,
                "accuracy_level": accuracy_level,
                "is_critical": noise_level >= 80,
                "is_high": noise_level > 50,
                "catalog_preview": catalog_preview,
            }
        )
    except Exception as e:
        raise internal_error(operation="Evaluate Action Space", exception=e) from e
