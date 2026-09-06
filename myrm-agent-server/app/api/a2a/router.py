"""A2A (Agent-to-Agent) Provider Server API endpoints.

Implements standard Google A2A v1.0 discovery endpoints and JSON-RPC 2.0
task lifecycle dispatch (tasks/send, tasks/get, tasks/cancel).

[INPUT]
- GET /.well-known/agent-card.json (or /api/v1/a2a/.well-known/agent-card.json)
- GET /api/v1/a2a/agents/{agent_id}/.well-known/agent-card.json
- POST /api/v1/a2a/rpc
- POST /api/v1/a2a/agents/{agent_id}/rpc

[OUTPUT]
- AgentCard manifest JSON
- JSON-RPC 2.0 response envelopes

[POS]
HTTP & JSON-RPC entry point for external agent interoperability.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, Request
from myrm_agent_harness.toolkits.a2a.security import sanitize_bearer_token
from myrm_agent_harness.toolkits.a2a.types import (
    JsonRpcError,
    JsonRpcErrorCode,
    JsonRpcRequest,
    JsonRpcResponse,
)

from app.services.a2a.card_generator import AgentCardGenerator
from app.services.a2a.service import get_a2a_server_service

logger = logging.getLogger(__name__)

router = APIRouter()
_card_generator = AgentCardGenerator()


@router.get("/.well-known/agent-card.json")
async def get_well_known_agent_card(request: Request) -> dict[str, object]:
    """Standard root discovery endpoint for default AgentCard."""
    base_url = str(request.base_url).rstrip("/")
    card = await _card_generator.generate_card(base_url=base_url)
    return card.model_dump(by_alias=True)


@router.get("/agents/{agent_id}/.well-known/agent-card.json")
async def get_agent_specific_card(agent_id: str, request: Request) -> dict[str, object]:
    """Per-agent discovery endpoint for specific Agent Profile."""
    base_url = str(request.base_url).rstrip("/")
    card = await _card_generator.generate_card(agent_id=agent_id, base_url=base_url)
    return card.model_dump(by_alias=True)


@router.post("/rpc")
async def handle_root_rpc(
    request: Request,
    body: JsonRpcRequest,
    authorization: str | None = Header(default=None),
) -> JsonRpcResponse:
    """JSON-RPC 2.0 dispatch for default agent."""
    return await _dispatch_rpc(request, body, agent_id=None, authorization=authorization)


@router.post("/agents/{agent_id}/rpc")
async def handle_agent_rpc(
    agent_id: str,
    request: Request,
    body: JsonRpcRequest,
    authorization: str | None = Header(default=None),
) -> JsonRpcResponse:
    """JSON-RPC 2.0 dispatch for specific agent profile."""
    return await _dispatch_rpc(request, body, agent_id=agent_id, authorization=authorization)


async def _dispatch_rpc(
    request: Request,
    req: JsonRpcRequest,
    *,
    agent_id: str | None,
    authorization: str | None,
) -> JsonRpcResponse:
    """Handle standard A2A JSON-RPC 2.0 methods."""
    _ = sanitize_bearer_token(authorization)
    service = get_a2a_server_service()
    req_id = req.id
    method = (req.method or "").strip()
    params = req.params or {}

    try:
        if method in ("tasks/send", "SendMessage"):
            prompt_obj = params.get("prompt") or params.get("message")
            if not isinstance(prompt_obj, str) or not prompt_obj.strip():
                return JsonRpcResponse(
                    id=req_id,
                    error=JsonRpcError(
                        code=int(JsonRpcErrorCode.INVALID_PARAMS),
                        message="Missing or invalid required parameter 'prompt' (or 'message').",
                    ),
                )

            task_id_param = str(params["taskId"]) if "taskId" in params else None
            push_url_param = str(params["pushUrl"]) if "pushUrl" in params else None
            push_secret_param = str(params["pushSecret"]) if "pushSecret" in params else None
            target_agent = str(params.get("agentId")) if params.get("agentId") else agent_id

            task = await service.send_task(
                prompt_obj,
                task_id=task_id_param,
                agent_id=target_agent,
                push_url=push_url_param,
                push_secret=push_secret_param,
            )
            return JsonRpcResponse(
                id=req_id,
                result=task.model_dump(by_alias=True),
            )

        elif method in ("tasks/get", "GetTask"):
            task_id = params.get("taskId") or params.get("id")
            if not isinstance(task_id, str) or not task_id.strip():
                return JsonRpcResponse(
                    id=req_id,
                    error=JsonRpcError(
                        code=int(JsonRpcErrorCode.INVALID_PARAMS),
                        message="Missing required parameter 'taskId'.",
                    ),
                )

            task = await service.get_task(task_id.strip())
            if task is None:
                return JsonRpcResponse(
                    id=req_id,
                    error=JsonRpcError(
                        code=int(JsonRpcErrorCode.TASK_NOT_FOUND),
                        message=f"Task with id '{task_id}' not found.",
                    ),
                )

            return JsonRpcResponse(
                id=req_id,
                result=task.model_dump(by_alias=True),
            )

        elif method in ("tasks/cancel", "CancelTask"):
            task_id = params.get("taskId") or params.get("id")
            if not isinstance(task_id, str) or not task_id.strip():
                return JsonRpcResponse(
                    id=req_id,
                    error=JsonRpcError(
                        code=int(JsonRpcErrorCode.INVALID_PARAMS),
                        message="Missing required parameter 'taskId'.",
                    ),
                )

            cancelled = await service.cancel_task(task_id.strip())
            return JsonRpcResponse(
                id=req_id,
                result={"cancelled": cancelled, "taskId": task_id.strip()},
            )

        elif method in ("agent/card", "GetAgentCard"):
            base_url = str(request.base_url).rstrip("/")
            card = await _card_generator.generate_card(agent_id=agent_id, base_url=base_url)
            return JsonRpcResponse(
                id=req_id,
                result=card.model_dump(by_alias=True),
            )

        else:
            return JsonRpcResponse(
                id=req_id,
                error=JsonRpcError(
                    code=int(JsonRpcErrorCode.METHOD_NOT_FOUND),
                    message=f"Method '{method}' is not recognized.",
                ),
            )

    except Exception as e:
        logger.error("Error executing A2A RPC method '%s': %s", method, e, exc_info=True)
        return JsonRpcResponse(
            id=req_id,
            error=JsonRpcError(
                code=int(JsonRpcErrorCode.INTERNAL_ERROR),
                message=f"Internal error processing request: {e}",
            ),
        )
