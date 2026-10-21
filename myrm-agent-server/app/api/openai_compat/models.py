"""OpenAI-compatible /v1/models endpoint.

[INPUT]
- app.database.models.agent::Agent (POS: Agent configuration model)
- app.api.openai_compat.auth::verify_api_key (POS: Bearer token auth)

[OUTPUT]
- list_models: GET /v1/models (returns configured agents)

[POS]
Lists Myrm agents as OpenAI-compatible model objects for the Agent API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.openai_compat.auth import verify_api_key
from app.api.openai_compat.types import ModelListResponse, ModelObject
from app.database.connection import get_session
from app.database.models.agent import Agent

router = APIRouter()


@router.get("/models")
async def list_models(
    _key_prefix: str = Depends(verify_api_key),
) -> ModelListResponse:
    """List available agents in OpenAI-compatible format."""
    models: list[ModelObject] = [
        ModelObject(id="default", owned_by="myrm"),
    ]

    async with get_session() as session:
        result = await session.execute(select(Agent.id, Agent.name).where(Agent.is_active.is_(True)))
        agents = result.all()

        for agent_id, agent_name in agents:
            models.append(
                ModelObject(
                    id=agent_id,
                    owned_by=f"myrm/{agent_name}" if agent_name else "myrm",
                )
            )

    return ModelListResponse(data=models)
