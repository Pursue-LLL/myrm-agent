"""Agent auxiliary endpoints — secrets, statistics, action-space evaluation.

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent CRUD 服务)
services.agent.backends::DatabaseSecretBackend (POS: Agent Secrets 加密存储)
services.agent.builtin_specs.builtin_tool_validation::RequiredBuiltinTools (POS: 内建工具类型)

[OUTPUT]
- GET    /{agent_id}/secrets: 列出 Agent 机密名称（不含明文）
- POST   /{agent_id}/secrets: 创建/更新 Agent 机密
- DELETE /{agent_id}/secrets/{key_name}: 删除 Agent 机密
- GET    /{agent_id}/statistics: Agent 使用统计（会话/消息/最后使用）
- POST   /evaluate-action-space: 动作空间复杂度 ASCS 评估 + Turn1 catalog_preview（inline/hidden/search_mounted）

[POS]
Agent 辅助端点。Secrets 管理、使用统计、动作空间复杂度评估。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.master_key import VaultLockedError
from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.schemas.responses import StandardSuccessResponse
from app.services.agent.agent_service import AgentService
from app.services.agent.backends import DatabaseSecretBackend
from app.services.agent.builtin_specs.builtin_tool_validation import RequiredBuiltinTools

logger = logging.getLogger(__name__)

router = APIRouter()


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
    enabled_builtin_tools: RequiredBuiltinTools


async def _build_catalog_preview(
    skill_ids: list[str],
    skill_configs: dict[str, dict],
) -> dict[str, int | bool]:
    """Turn1 bound-skill catalog preview — harness SSOT for inline/hidden/search gate."""
    from myrm_agent_harness.agent.skills.runtime.catalog_display import (
        SKILL_SELECT_INLINE_MAX,
        resolve_catalog_display_skills,
        should_mount_skill_search_tool,
    )
    from myrm_agent_harness.backends.skills.types import SkillMetadata

    from app.core.skills.store.service import skills_service
    from app.core.skills.utils import normalize_skill_name

    stored_skills = await skills_service.get_skills_by_ids(skill_ids=skill_ids)
    metadata_list: list[SkillMetadata] = []
    for skill in stored_skills:
        try:
            name = normalize_skill_name(skill.name)
        except ValueError:
            logger.warning("Skipping skill with invalid name for catalog preview: %s", skill.name)
            continue
        metadata_list.append(
            SkillMetadata(
                name=name,
                description=skill.description or "",
                storage_skill_id=skill.id,
                storage_path=skill.storage_path,
                token_cost=skill.token_cost,
                always=skill.always,
                model_invocable=skill.model_invocable,
                available=skill.available,
            )
        )

    configs = skill_configs or None
    resolution = resolve_catalog_display_skills(metadata_list, skill_configs=configs)
    search_mounted = bool(metadata_list) and should_mount_skill_search_tool(
        metadata_list,
        skill_configs=configs,
    )
    return {
        "inline_count": len(resolution.display_skills),
        "hidden_count": resolution.hidden_skill_count,
        "search_mounted": search_mounted,
        "inline_cap": SKILL_SELECT_INLINE_MAX,
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

        for skill_id in req.skill_ids:
            is_core = req.skill_configs.get(skill_id, {}).get("is_core", True)
            skill = await skills_service.get_skill_by_id(skill_id)
            if skill:
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
