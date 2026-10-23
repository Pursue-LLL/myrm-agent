"""Read-only catalog of subagent presets exposed to the Agent editor.

[INPUT]
- app.ai_agents.subagent_presets::load_user_selectable_subagent_configs, required_builtin_tools
- fastapi (APIRouter)
- app.core.utils.response_utils::success_response
- app.schemas.responses::StandardSuccessResponse

[OUTPUT]
- router: GET /agents/subagent-presets
- SubagentPresetItem: id, display_name, description, required_builtin_tools

[POS]
Server business-layer HTTP adapter for the user-selectable YAML subagent catalog. It exposes
metadata only (never system prompts), so the Agent editor can render and persist the same
``subagent_ids`` that the runtime resolves.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.ai_agents.subagent_presets import (
    load_user_selectable_subagent_configs,
    required_builtin_tools,
)
from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class SubagentPresetItem(BaseModel):
    """Public metadata for one built-in subagent preset."""

    id: str
    display_name: str
    description: str
    required_builtin_tools: list[str]


@router.get("/subagent-presets", response_model=StandardSuccessResponse)
async def list_subagent_presets() -> JSONResponse:
    """List the built-in specialists an Agent may bind as subagents."""
    try:
        configs = load_user_selectable_subagent_configs()
        presets = [
            SubagentPresetItem(
                id=type_id,
                display_name=config.display_name or type_id.replace("-", " ").title(),
                description=config.description,
                required_builtin_tools=list(required_builtin_tools(config)),
            ).model_dump()
            for type_id, config in configs.items()
        ]
        return success_response(data=presets)
    except Exception as exc:
        logger.exception("Failed to list subagent presets")
        raise internal_error(operation="List subagent presets", exception=exc) from exc
