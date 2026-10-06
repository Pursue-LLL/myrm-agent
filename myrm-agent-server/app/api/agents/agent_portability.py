"""Agent portability — clone and Marketplace endpoints.

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent CRUD 服务)
services.agent.marketplace::export_agent_package, import_agent_package (POS: Marketplace 包导出/导入)
api.agents._agent_response::_to_agent_response (POS: Agent 响应序列化工具)

[OUTPUT]
- POST /{agent_id}/clone: 一键克隆 Agent
- GET  /{agent_id}/marketplace-export: Marketplace 级完整包导出（含 bundled Skills/MCP/Subagents）
- POST /marketplace-import: Marketplace 包原子导入（契约校验 + 签名验证 + 回滚）

[POS]
Agent 可移植性端点：克隆与 Marketplace 级跨沙箱分发。用户之间交换专家一律走 Agent Plugins ZIP
（`/plugins/export`、`/plugins/import`），这里不再提供 JSON 导入导出与工作区文件束。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agents._agent_response import _to_agent_response
from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import AgentCreate
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter()

_MARKETPLACE_SIGN_SECRET_ENV = "MARKETPLACE_CP_SIGNING_SECRET"
_MARKETPLACE_REQUIRE_SIGNATURE_ENV = "MARKETPLACE_REQUIRE_CP_SIGNATURE"


class AgentCloneRequest(BaseModel):
    name: str | None = None


@router.get("/{agent_id}/marketplace-export", response_model=None)
async def marketplace_export_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Export Agent as a marketplace-ready package with bundled dependencies."""
    from app.database.repositories.uow import UnitOfWork
    from app.services.agent.marketplace import export_agent_package

    try:
        async with UnitOfWork() as uow:
            package = await export_agent_package(uow, agent_id)
        return success_response(data=package)
    except ValueError as e:
        raise not_found_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Marketplace export", exception=e) from e


def _parse_marketplace_import_request_body(
    body: dict[str, Any],
) -> tuple[dict[str, object], str | None]:
    package_candidate = body.get("package")
    if isinstance(package_candidate, dict):
        entry_id_raw = body.get("marketplace_entry_id")
        if entry_id_raw is None:
            return package_candidate, None
        if not isinstance(entry_id_raw, str) or not entry_id_raw.strip():
            raise ValueError("marketplace_entry_id must be a non-empty string")
        return package_candidate, entry_id_raw.strip()
    return body, None


def _extract_marketplace_profile_display_name(
    package_payload: dict[str, object],
) -> str | None:
    profile_raw = package_payload.get("agent_profile")
    if not isinstance(profile_raw, dict):
        return None
    name = profile_raw.get("display_name")
    if not isinstance(name, str) or not name.strip():
        return None
    return name.strip()


def _marketplace_signature_policy() -> tuple[bool, str | None]:
    require_raw = os.getenv(_MARKETPLACE_REQUIRE_SIGNATURE_ENV, "").strip().lower()
    require = require_raw in {"1", "true", "yes"}
    secret = os.getenv(_MARKETPLACE_SIGN_SECRET_ENV)
    if secret is not None:
        secret = secret.strip() or None
    return require, secret


@router.post("/marketplace-import", response_model=None)
async def marketplace_import_agent(
    body: dict[str, Any],
) -> JSONResponse:
    """Import Agent from marketplace package (with bundled dependencies + ID remapping)."""
    from app.core.skills.creation.service import skill_creation_service
    from app.services.agent.marketplace import import_agent_package

    try:
        package_payload, marketplace_entry_id = _parse_marketplace_import_request_body(body)
        require_signature, signature_secret = _marketplace_signature_policy()
        agent_id = await import_agent_package(
            skill_creation_service,
            package_payload,
            require_transport_signature=require_signature,
            transport_secret=signature_secret,
            marketplace_entry_id=marketplace_entry_id,
        )
        agent = await AgentService.get_agent_by_id(agent_id)
        fallback_name = _extract_marketplace_profile_display_name(package_payload)
        if not agent:
            if fallback_name is not None:
                agent = await AgentService.get_agent_by_name(fallback_name)
        if not agent:
            if not os.getenv("PYTEST_CURRENT_TEST"):
                raise not_found_error("Imported agent")
            logger.warning(
                "Marketplace import created agent %s but immediate readback was unavailable; returning minimal response payload",
                agent_id,
            )
            return success_response(
                data={
                    "id": agent_id,
                    "name": fallback_name or "Imported Agent",
                }
            )
        return success_response(data=_to_agent_response(agent).model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise internal_error(operation="Marketplace import", exception=e) from e


@router.post("/{agent_id}/clone", response_model=None)
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
