"""Chat turn prewarm API — proactive EmptyChat / focus warm.

[INPUT]
- app.services.agent.execution_cache.prewarm.params::resolve_prewarm_agent_params (POS: prewarm params SSOT)
- app.services.agent.execution_cache.prewarm.coordinator::get_turn_prewarm_coordinator (POS: turn prewarm coordinator)

[OUTPUT]
- POST /agents/chats/{chat_id}/prewarm: start background warm
- DELETE /agents/chats/{chat_id}/prewarm: cancel scope warm tasks

[POS]
General Agent HTTP 层。EmptyChat / MessageInput focus 触发的 turn1 冷启动预热入口。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.services.agent.execution_cache.prewarm.coordinator import get_turn_prewarm_coordinator
from app.services.agent.execution_cache.prewarm.params import resolve_prewarm_agent_params

logger = logging.getLogger(__name__)

router = APIRouter()


class TurnPrewarmRequest(BaseModel):
    agent_id: str | None = None
    action_mode: str = "agent"
    incognito_mode: bool = False

    class Config:
        alias_generator = to_camel
        populate_by_name = True


@router.post("/chats/{chat_id}/prewarm")
@limiter.limit(settings.rate_limit.chat)
async def prewarm_chat_turn(
    chat_id: str,
    body: TurnPrewarmRequest,
    http_request: Request,
) -> JSONResponse:
    from app.core.utils.response_utils import success_response
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access

    require_mobile_pair_chat_access(http_request, chat_id)
    if body.incognito_mode or body.action_mode == "fast":
        return success_response(
            data={"started": False, "chat_id": chat_id, "reason": "skipped_mode"},
        )

    params = await resolve_prewarm_agent_params(
        chat_id=chat_id,
        agent_id=body.agent_id,
        action_mode=body.action_mode,
        incognito_mode=body.incognito_mode,
    )
    await get_turn_prewarm_coordinator().ensure_warming(
        params,
        action_mode=body.action_mode,
    )
    logger.warning("Turn prewarm requested: chat_id=%s agent_id=%s", chat_id, body.agent_id)
    return success_response(data={"started": True, "chat_id": chat_id})


@router.delete("/chats/{chat_id}/prewarm")
@limiter.limit(settings.rate_limit.chat)
async def cancel_prewarm_chat_turn(
    chat_id: str,
    http_request: Request,
    agent_id: str | None = Query(default=None),
) -> JSONResponse:
    from app.core.utils.response_utils import success_response
    from app.remote_access.mobile_gate import require_mobile_pair_chat_access

    require_mobile_pair_chat_access(http_request, chat_id)
    await get_turn_prewarm_coordinator().cancel_scope(chat_id, agent_id)
    return success_response(data={"cancelled": True, "chat_id": chat_id})
