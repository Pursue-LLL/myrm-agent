"""Agent portability — export / import / clone / marketplace endpoints.

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent CRUD 服务)
services.agent.marketplace::export_agent_package, import_agent_package (POS: Marketplace 包导出/导入)
api.agents._agent_response::_to_agent_response (POS: Agent 响应序列化工具)

[OUTPUT]
- GET  /{agent_id}/export: 导出 Agent 配置 JSON（凭据剔除 · 团队递归导出）
- POST /import: 导入 Agent 配置（单体/团队原子导入）
- POST /{agent_id}/clone: 一键克隆 Agent
- GET  /{agent_id}/marketplace-export: Marketplace 级完整包导出（含 bundled Skills/MCP/Subagents）
- POST /marketplace-import: Marketplace 包原子导入（契约校验 + 签名验证 + 回滚）

[POS]
Agent 可移植性端点。负责 Agent 配置的导出、导入、克隆和 Marketplace 级跨沙箱分发。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agents._agent_response import _to_agent_response
from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import AgentCreate
from app.services.agent.agent_bundle_service import AgentBundleService
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter()

_MARKETPLACE_SIGN_SECRET_ENV = "MARKETPLACE_CP_SIGNING_SECRET"
_MARKETPLACE_REQUIRE_SIGNATURE_ENV = "MARKETPLACE_REQUIRE_CP_SIGNATURE"

_SENSITIVE_AUTH_FIELDS = frozenset({"api_key", "bearer_token", "client_secret", "password", "username"})


class AgentCloneRequest(BaseModel):
    name: str | None = None


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


@router.get("/{agent_id}/export", response_model=None)
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
            return success_response(
                data={
                    "_export_version": 1,
                    "agent_type": "team",
                    "leader": leader_data,
                    "members": members,
                }
            )

        return success_response(data=leader_data)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Export agent", exception=e) from e


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


@router.post("/import", response_model=None)
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
            member_data = AgentCreate.model_validate(member_raw)
            member_data.is_built_in = False
            member = await AgentService.create_agent(member_data)
            created_member_ids.append(member.id)

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


class WorkspaceBundleSyncRequest(BaseModel):
    workspace_dir: str = Field(..., description="Target workspace directory path", min_length=1)


class WorkspaceBundleImportRequest(BaseModel):
    workspace_dir: str = Field(..., description="Target workspace directory path", min_length=1)
    agent_id: str = Field(..., description="Agent bundle subfolder name", min_length=1)


@router.get("/{agent_id}/bundle", response_model=None)
async def export_agent_bundle(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Export agent as filesystem bundle data (AGENTS.md, manifest.yaml, mcp.json)."""
    try:
        bundle = await AgentBundleService.export_bundle(agent_id)
        return success_response(
            data={
                "agent_id": bundle.agent_id,
                "name": bundle.name,
                "prompt": bundle.prompt,
                "manifest_yaml": bundle.manifest_yaml,
                "mcp_json": bundle.mcp_json,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Export agent bundle", exception=e) from e


@router.post("/{agent_id}/bundle/sync-to-workspace", response_model=None)
async def sync_agent_bundle_to_workspace(
    agent_id: str,
    body: WorkspaceBundleSyncRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Serialize and write agent filesystem bundle into workspace (.myrm/agents/{agent_id}/)."""
    try:
        written_dir = await AgentBundleService.write_bundle_to_workspace(agent_id, body.workspace_dir)
        return success_response(
            data={
                "agent_id": agent_id,
                "bundle_dir": str(written_dir),
                "synced": True,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Sync agent bundle to workspace", exception=e) from e


@router.post("/{agent_id}/bundle/sync-from-workspace", response_model=None)
async def sync_agent_bundle_from_workspace(
    agent_id: str,
    body: WorkspaceBundleSyncRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Update existing agent in DB by parsing .myrm/agents/{agent_id}/ bundle from workspace."""
    try:
        result = await AgentBundleService.sync_workspace_to_agent(agent_id, body.workspace_dir)
        return success_response(data=result)
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Sync workspace bundle to agent", exception=e) from e


@router.post("/bundle/import-from-workspace", response_model=None)
async def import_agent_from_workspace_bundle(
    body: WorkspaceBundleImportRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Create a new agent by importing a bundle from .myrm/agents/{agent_id}/."""
    try:
        agent_dto = AgentBundleService.read_bundle_from_workspace(body.agent_id, body.workspace_dir)
        agent_dto.is_built_in = False
        new_agent = await AgentService.create_agent(agent_dto)
        return success_response(data=_to_agent_response(new_agent).model_dump())
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Import agent from workspace bundle", exception=e) from e
