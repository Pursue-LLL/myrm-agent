"""OpenAI-compatible /v1/models endpoint.

[INPUT]
- app.database.models.agent::Agent (POS: Agent configuration model)
- app.api.openai_compat.auth::verify_api_key (POS: Bearer token auth)
- app.services.config.service::config_service (POS: Config service for provider settings)

[OUTPUT]
- list_models: GET /v1/models (returns agents + passthrough LLM models)

[POS]
Returns both configured agents and user-configured LLM models as
OpenAI-compatible model objects. Agents can be used with the Agent execution
engine; LLM models use the passthrough path for direct forwarding.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.openai_compat.auth import verify_api_key
from app.api.openai_compat.types import ModelListResponse, ModelObject
from app.database.connection import get_session
from app.database.models.agent import Agent

logger = logging.getLogger(__name__)

router = APIRouter()


def _collect_provider_models(providers_dict: dict[str, object]) -> list[ModelObject]:
    """Extract enabled LLM models from user's provider config for passthrough."""
    models: list[ModelObject] = []
    providers_raw = providers_dict.get("providers")
    if not isinstance(providers_raw, list):
        return models

    for provider in providers_raw:
        if not isinstance(provider, dict):
            continue
        is_enabled = provider.get("isEnabled") or provider.get("enabled")
        if not is_enabled:
            continue

        pid = str(provider.get("id", ""))
        enabled_models: list[str] = provider.get("enabledModels", [])  # type: ignore[assignment]
        if not isinstance(enabled_models, list):
            continue

        has_keys = bool(provider.get("apiKeys"))
        if not has_keys:
            continue

        for model_name in enabled_models:
            if not isinstance(model_name, str) or not model_name.strip():
                continue
            models.append(
                ModelObject(
                    id=model_name,
                    owned_by=f"provider/{pid}" if pid else "provider",
                )
            )

    return models


@router.get("/models")
async def list_models(
    _key_prefix: str = Depends(verify_api_key),
) -> ModelListResponse:
    """List available models in OpenAI-compatible format.

    Returns:
    - "default" agent (always present)
    - User-configured agents
    - User-configured LLM models (for passthrough)
    """
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

    try:
        from app.services.config.service import config_service

        record = await config_service.get("providers")
        if record is not None:
            value = record.value if hasattr(record, "value") else record
            if isinstance(value, dict):
                existing_ids = {m.id for m in models}
                for pm in _collect_provider_models(value):
                    if pm.id not in existing_ids:
                        models.append(pm)
                        existing_ids.add(pm.id)
    except Exception:
        logger.warning("Failed to load provider models for /v1/models passthrough list")

    return ModelListResponse(data=models)
