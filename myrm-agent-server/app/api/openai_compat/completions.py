"""OpenAI-compatible /v1/chat/completions endpoint.

[INPUT]
- app.api.openai_compat.types::ChatCompletionRequest (POS: OpenAI request schema)
- app.api.openai_compat.auth::verify_api_key (POS: Bearer token auth)
- app.api.openai_compat.passthrough (POS: LLM passthrough for non-Agent models)
- app.services.agent.streaming::ai_agent_service_stream (POS: Agent stream engine)
- app.services.agent.params::convert_to_general_agent_params (POS: Param builder)

[OUTPUT]
- chat_completions: POST /v1/chat/completions (streaming + non-streaming)

[POS]
Core implementation. Routes requests to either Agent execution (when model matches
an agent ID) or LLM passthrough (when model matches a user-configured LLM). This
dual-mode design lets external tools (Aider, Cline, Codex) use MyrmAgent as an
OpenAI-compatible API proxy.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.openai_compat.auth import verify_api_key
from app.api.openai_compat.types import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    DeltaMessage,
    StreamChoice,
    UsageInfo,
)
from app.services.agent.streaming import ai_agent_service_stream

logger = logging.getLogger(__name__)

router = APIRouter()

if TYPE_CHECKING:
    from app.services.agent.params.models import GeneralAgentParams


def _build_chat_history(request: ChatCompletionRequest) -> list[list[str | dict[str, object]]]:
    """Convert OpenAI messages array to internal chat_history format.

    Internal format: list of [role_content_pairs] where each pair is
    [role, content] or a dict with role/content keys.
    Skips the last user message (used as query).
    """
    history: list[list[str | dict[str, object]]] = []
    messages = request.messages[:-1]
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        history.append([msg.role, content])
    return history


def _extract_query(request: ChatCompletionRequest) -> str:
    """Extract the query (last user message) from the request."""
    last_msg = request.messages[-1]
    if isinstance(last_msg.content, str):
        return last_msg.content
    # Multi-part content: concatenate text parts
    parts = []
    for part in last_msg.content:
        if isinstance(part, dict) and part.get("type") == "text":
            parts.append(part.get("text", ""))
    return "\n".join(parts) if parts else str(last_msg.content)


def _extract_system_instruction(request: ChatCompletionRequest) -> str | None:
    """Extract system instruction from messages if present."""
    for msg in request.messages:
        if msg.role == "system":
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return None


async def _build_agent_params(
    request: ChatCompletionRequest,
) -> "GeneralAgentParams":
    """Build GeneralAgentParams from an OpenAI-compatible request.

    Resolves agent_id from model field, loads user config, and
    assembles parameters for the Agent execution engine.
    """
    from app.services.agent.params import convert_to_general_agent_params
    from app.services.agent.params.models import AgentRequest

    agent_id = None if request.model in ("default", "gpt-4", "gpt-4o", "gpt-3.5-turbo") else request.model

    message_id = f"oai-{uuid.uuid4().hex[:16]}"
    chat_id = request.chat_id or f"oai-session-{uuid.uuid4().hex[:12]}"

    agent_request = AgentRequest(
        message_id=message_id,
        chat_id=chat_id,
        agent_id=agent_id,
        query=_extract_query(request),
        user_instructions=_extract_system_instruction(request),
        enable_memory=True,
        enable_memory_auto_extraction=True,
        timezone=None,
    )

    chat_history = _build_chat_history(request)
    params, _, _, _archive_restore_results = await convert_to_general_agent_params(agent_request, chat_history)

    # Apply temperature override if specified
    if request.temperature is not None and params.model_cfg:
        params.model_cfg = params.model_cfg.model_copy(update={"temperature": request.temperature})

    return params


async def _stream_response(
    request: ChatCompletionRequest,
) -> AsyncGenerator[str, None]:
    """Generate OpenAI-format SSE chunks from Agent stream."""
    params = await _build_agent_params(request)
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model_name = request.model

    # Send initial role chunk
    first_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model_name,
        choices=[StreamChoice(delta=DeltaMessage(role="assistant"), finish_reason=None)],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    total_content = ""
    async for event in ai_agent_service_stream(params):
        if isinstance(event, dict):
            event_type = event.get("type", "")

            if event_type == "message_chunk":
                content = event.get("content", "")
                if content:
                    total_content += content
                    chunk = ChatCompletionChunk(
                        id=completion_id,
                        created=created,
                        model=model_name,
                        choices=[StreamChoice(delta=DeltaMessage(content=content), finish_reason=None)],
                    )
                    yield f"data: {chunk.model_dump_json()}\n\n"

            elif event_type == "message_end":
                finish_chunk = ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=model_name,
                    choices=[StreamChoice(delta=DeltaMessage(), finish_reason="stop")],
                )
                yield f"data: {finish_chunk.model_dump_json()}\n\n"
                break

    yield "data: [DONE]\n\n"


@router.post("/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    _key_prefix: str = Depends(verify_api_key),
) -> ChatCompletionResponse | StreamingResponse:
    """OpenAI-compatible chat completions endpoint.

    Routes to either Agent execution or LLM passthrough based on model field:
    - Agent IDs (or "default") → Agent execution engine
    - LLM model names (e.g. "claude-3.5-sonnet") → direct litellm forwarding
    """
    from app.api.openai_compat.passthrough import (
        is_passthrough_model,
        passthrough_completion,
        passthrough_stream,
    )

    if await is_passthrough_model(request.model):
        if request.stream:
            return StreamingResponse(
                passthrough_stream(request),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        return await passthrough_completion(request)

    if request.stream:
        return StreamingResponse(
            _stream_response(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming Agent path: collect full response
    params = await _build_agent_params(request)

    full_content = ""
    usage_data: dict[str, object] = {}

    async for event in ai_agent_service_stream(params):
        if isinstance(event, dict):
            event_type = event.get("type", "")
            if event_type == "message_chunk":
                full_content += event.get("content", "")
            elif event_type == "message_end":
                usage_data = event.get("usage", {})
                break

    usage = UsageInfo(
        prompt_tokens=int(usage_data.get("prompt_tokens", 0)) if isinstance(usage_data, dict) else 0,
        completion_tokens=int(usage_data.get("completion_tokens", 0)) if isinstance(usage_data, dict) else 0,
        total_tokens=int(usage_data.get("total_tokens", 0)) if isinstance(usage_data, dict) else 0,
    )

    return ChatCompletionResponse(
        model=request.model,
        choices=[Choice(message=ChoiceMessage(content=full_content))],
        usage=usage,
    )
