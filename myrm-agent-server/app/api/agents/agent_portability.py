"""Agent portability — clone endpoint.

[INPUT]
services.agent.agent_service::AgentService (POS: 业务层 Agent CRUD 服务)
api.agents._agent_response::_to_agent_response (POS: Agent 响应序列化工具)

[OUTPUT]
- POST /{agent_id}/clone: 一键克隆 Agent

[POS]
Agent 克隆端点。用户之间交换专家一律走 Agent Plugins ZIP（`/plugins/export`、`/plugins/import`）。
"""

from __future__ import annotations

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

router = APIRouter()


class AgentCloneRequest(BaseModel):
    name: str | None = None


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
