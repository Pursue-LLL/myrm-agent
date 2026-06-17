"""A2A well-known AgentCard endpoint.

Serves ``/.well-known/agent-card.json`` per A2A spec.

[INPUT]
- app.config.settings::settings (POS: app name/version)
- app.config.deploy_mode::is_sandbox (POS: deploy mode)
- app.services.agent.agent_service::AgentService (POS: agent data)

[OUTPUT]
- router: FastAPI router for /.well-known/agent-card.json

[POS]
Exposes the server's A2A AgentCard for external discovery.
Controlled by A2A_DISCOVERY_ENABLED env var.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from myrm_agent_harness.toolkits.a2a.types import (
    AgentCard,
    AgentCapabilities,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    TransportProtocol,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["a2a"])


def _is_a2a_discovery_enabled() -> bool:
    """Check if A2A AgentCard exposure is enabled.

    Defaults: sandbox=True (cloud), local/tauri=False.
    Override via A2A_DISCOVERY_ENABLED env var.
    """
    env_val = os.getenv("A2A_DISCOVERY_ENABLED")
    if env_val is not None:
        return env_val.lower() in ("true", "1", "yes")

    from app.config.deploy_mode import is_sandbox

    return is_sandbox()


async def _build_agent_card() -> AgentCard:
    """Build AgentCard from default agent and installed skills."""
    from app.config.settings import settings
    from app.services.agent.agent_service import AgentService

    # 获取所有智能体，使用第一个（默认）智能体的信息
    agents, _ = await AgentService.get_agent_list(page=1, page_size=1)
    agent = agents[0] if agents else None

    name = settings.app_name
    description = "AI Agent service with multi-modal capabilities"
    if agent:
        name = agent.display_name or name
        description = agent.description or description

    # 从智能体的已安装 skills 构建 AgentSkill 列表
    a2a_skills: list[AgentSkill] = []
    if agent and agent.skills:
        for skill_id in agent.skills:
            a2a_skills.append(
                AgentSkill(
                    id=skill_id,
                    name=skill_id.replace("_", " ").replace("-", " ").title(),
                    description=f"Skill: {skill_id}",
                    tags=[skill_id],
                )
            )

    return AgentCard(
        name=name,
        description=description,
        version=settings.app_version,
        supported_interfaces=[
            AgentInterface(
                url="/",
                protocol_binding=TransportProtocol.HTTP_JSON,
            ),
        ],
        capabilities=AgentCapabilities(
            streaming=True,
        ),
        skills=a2a_skills,
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["text/plain", "application/json"],
        provider=AgentProvider(
            organization="Myrm",
            url="https://myrm.dev",
        ),
    )


@router.get("/.well-known/agent-card.json")
async def get_agent_card() -> JSONResponse:
    """Serve AgentCard per A2A spec.

    Returns 404 if A2A discovery is disabled.
    """
    if not _is_a2a_discovery_enabled():
        return JSONResponse(
            status_code=404,
            content={"error": "A2A discovery is not enabled"},
        )

    card = await _build_agent_card()
    return JSONResponse(
        content=card.model_dump(mode="json", by_alias=True, exclude_none=True),
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "public, max-age=300",
        },
    )


@router.options("/.well-known/agent-card.json")
async def agent_card_cors_preflight() -> JSONResponse:
    """CORS preflight for AgentCard endpoint."""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
        },
    )
