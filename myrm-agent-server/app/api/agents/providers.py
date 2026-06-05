"""
[INPUT] app.database.models.agent::Agent (POS: Agent Database Model)
[OUTPUT] Provider APIs (usage, clear-usage, batch-migrate)
[POS] Agent provider configuration endpoints for deletion impact analysis and batch operations.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models.agent import Agent
from app.database.standard_responses import StandardSuccessResponse

router = APIRouter()


class AgentSummary(BaseModel):
    id: str
    name: str
    model: str | None = None


class ProviderUsageResponse(BaseModel):
    has_usage: bool
    count: int
    agents: list[AgentSummary]


@router.get("/{provider_id}/usage", response_model=ProviderUsageResponse)
async def get_provider_usage(provider_id: str, db: AsyncSession = Depends(get_db)):
    """Check how many agents are currently using this provider."""
    stmt = select(Agent.id, Agent.name, Agent.model_selection).where(
        Agent.model_selection["providerId"].as_string() == provider_id
    )
    result = await db.execute(stmt)
    agents = result.all()

    agent_summaries = []
    for agent in agents:
        ms = agent.model_selection
        model_name = ms.get("model") if ms else None
        agent_summaries.append(AgentSummary(id=agent.id, name=agent.name, model=str(model_name) if model_name else None))

    return ProviderUsageResponse(has_usage=len(agent_summaries) > 0, count=len(agent_summaries), agents=agent_summaries)


class ClearUsageRequest(BaseModel):
    provider_id: str


@router.post("/{provider_id}/clear-usage", response_model=StandardSuccessResponse)
async def clear_provider_usage(provider_id: str, db: AsyncSession = Depends(get_db)):
    """Clear provider references from all agents using it. Used when force deleting a provider."""
    stmt = select(Agent).where(Agent.model_selection["providerId"].as_string() == provider_id)
    result = await db.execute(stmt)
    agents = result.scalars().all()

    updated_count = 0
    for agent in agents:
        agent.model_selection = None
        updated_count += 1

    if updated_count > 0:
        await db.commit()

    return success_response(message=f"Cleared provider references from {updated_count} agents")


class BatchMigrateRequest(BaseModel):
    from_provider_id: str
    to_provider_id: str
    to_model: str
    preview: bool = False


class BatchMigratePreviewResponse(BaseModel):
    affected_count: int
    affected_agents: list[dict[str, str]]


class BatchMigrateResponse(BaseModel):
    updated_count: int


@router.post("/batch-migrate")
async def batch_migrate_provider(req: BatchMigrateRequest, db: AsyncSession = Depends(get_db)):
    """Batch migrate agents from one provider to another."""
    stmt = select(Agent).where(Agent.model_selection["providerId"].as_string() == req.from_provider_id)
    result = await db.execute(stmt)
    agents = result.scalars().all()

    affected = []

    for agent in agents:
        ms = agent.model_selection
        if isinstance(ms, dict):
            current_model = str(ms.get("model", ""))
            affected.append({"id": agent.id, "name": agent.name, "current_model": current_model, "new_model": req.to_model})

            if not req.preview:
                new_ms = dict(ms)
                new_ms["providerId"] = req.to_provider_id
                new_ms["model"] = req.to_model
                agent.model_selection = new_ms
                # Update model_config as well
                agent.model_config = {"model": req.to_model}

    if not req.preview and affected:
        await db.commit()

    if req.preview:
        return BatchMigratePreviewResponse(affected_count=len(affected), affected_agents=affected)
    return BatchMigrateResponse(updated_count=len(affected))
