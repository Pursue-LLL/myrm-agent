"""A2A Agent integration management API.

CRUD for third-party A2A Agent connections: add/remove/list remote agents
discovered via their ``/.well-known/agent-card.json``.

[INPUT]
- myrm_agent_harness.toolkits.a2a::A2ACardResolver (POS: AgentCard resolver)
- myrm_agent_harness.toolkits.a2a::AgentCard (POS: A2A data model)

[OUTPUT]
- router: FastAPI router for /integrations/a2a endpoints

[POS]
Integration management for A2A agents, similar to MCP server management.
Allows users to add/remove/list third-party A2A agents via URL discovery.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from myrm_agent_harness.toolkits.a2a.resolver import (
    A2ACardResolver,
    A2AResolveError,
    SSRFBlockedError,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 模块级 resolver 实例（带缓存）
_resolver = A2ACardResolver(timeout_seconds=15.0, cache_ttl_seconds=300.0)

# 内存存储（后续可替换为 SQLite 持久化）
_a2a_agents: dict[str, "A2AAgentRecord"] = {}


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class A2AAgentRecord(BaseModel):
    """Persisted A2A agent connection record."""

    id: str
    base_url: str
    name: str
    description: str
    version: str = ""
    skills: list[dict[str, str]] = Field(default_factory=list)
    added_at: str = ""
    last_checked_at: str = ""
    healthy: bool = True


class AddA2AAgentRequest(BaseModel):
    """Request to add a third-party A2A agent by URL."""

    base_url: str = Field(
        description="Base URL of the A2A agent (e.g. https://agent.example.com)"
    )


class AddA2AAgentResponse(BaseModel):
    """Response after successfully adding an A2A agent."""

    id: str
    name: str
    description: str
    version: str
    skills_count: int
    base_url: str


class A2AAgentListItem(BaseModel):
    """List item for connected A2A agents."""

    id: str
    base_url: str
    name: str
    description: str
    version: str
    skills_count: int
    healthy: bool
    added_at: str


class RefreshA2AAgentResponse(BaseModel):
    """Response after refreshing an A2A agent's card."""

    id: str
    name: str
    description: str
    version: str
    skills_count: int
    updated: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/add")
async def add_a2a_agent(body: AddA2AAgentRequest) -> AddA2AAgentResponse:
    """Add a third-party A2A agent by discovering its AgentCard.

    Fetches ``/.well-known/agent-card.json`` from the given URL,
    validates the response, and stores the connection.
    """
    base_url = body.base_url.rstrip("/")

    # 检查是否已添加
    for record in _a2a_agents.values():
        if record.base_url == base_url:
            raise HTTPException(
                status_code=409,
                detail=f"A2A agent at {base_url} already added",
            )

    # 通过 Resolver 发现 AgentCard
    try:
        card = await _resolver.resolve(base_url)
    except SSRFBlockedError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"URL blocked by security policy: {exc}",
        ) from exc
    except A2AResolveError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to discover AgentCard: {exc}",
        ) from exc

    # 创建记录
    agent_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    skills_data = [
        {"id": s.id, "name": s.name, "description": s.description}
        for s in card.skills
    ]

    record = A2AAgentRecord(
        id=agent_id,
        base_url=base_url,
        name=card.name,
        description=card.description,
        version=card.version,
        skills=skills_data,
        added_at=now,
        last_checked_at=now,
        healthy=True,
    )
    _a2a_agents[agent_id] = record

    logger.info("Added A2A agent: %s (%s) with %d skills", card.name, base_url, len(card.skills))

    return AddA2AAgentResponse(
        id=agent_id,
        name=card.name,
        description=card.description,
        version=card.version,
        skills_count=len(card.skills),
        base_url=base_url,
    )


@router.get("/list")
async def list_a2a_agents() -> list[A2AAgentListItem]:
    """List all connected A2A agents."""
    return [
        A2AAgentListItem(
            id=r.id,
            base_url=r.base_url,
            name=r.name,
            description=r.description,
            version=r.version,
            skills_count=len(r.skills),
            healthy=r.healthy,
            added_at=r.added_at,
        )
        for r in _a2a_agents.values()
    ]


@router.delete("/{agent_id}")
async def remove_a2a_agent(agent_id: str) -> dict[str, bool]:
    """Remove a connected A2A agent."""
    if agent_id not in _a2a_agents:
        raise HTTPException(status_code=404, detail="A2A agent not found")

    record = _a2a_agents.pop(agent_id)
    _resolver.invalidate_cache(record.base_url)

    logger.info("Removed A2A agent: %s (%s)", record.name, record.base_url)
    return {"removed": True}


@router.post("/{agent_id}/refresh")
async def refresh_a2a_agent(agent_id: str) -> RefreshA2AAgentResponse:
    """Refresh an A2A agent's card by re-fetching from its URL."""
    if agent_id not in _a2a_agents:
        raise HTTPException(status_code=404, detail="A2A agent not found")

    record = _a2a_agents[agent_id]
    _resolver.invalidate_cache(record.base_url)

    try:
        card = await _resolver.resolve(record.base_url)
    except A2AResolveError as exc:
        # 标记为不健康但不删除
        record.healthy = False
        _a2a_agents[agent_id] = record
        raise HTTPException(
            status_code=502,
            detail=f"Failed to refresh AgentCard: {exc}",
        ) from exc

    # 更新记录
    now = datetime.now(tz=timezone.utc).isoformat()
    skills_data = [
        {"id": s.id, "name": s.name, "description": s.description}
        for s in card.skills
    ]
    updated = (
        record.name != card.name
        or record.description != card.description
        or record.version != card.version
        or len(record.skills) != len(skills_data)
    )

    record = A2AAgentRecord(
        id=agent_id,
        base_url=record.base_url,
        name=card.name,
        description=card.description,
        version=card.version,
        skills=skills_data,
        added_at=record.added_at,
        last_checked_at=now,
        healthy=True,
    )
    _a2a_agents[agent_id] = record

    return RefreshA2AAgentResponse(
        id=agent_id,
        name=card.name,
        description=card.description,
        version=card.version,
        skills_count=len(card.skills),
        updated=updated,
    )
