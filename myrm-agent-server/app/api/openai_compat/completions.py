"""OpenAI-compatible /v1/chat/completions endpoint.

[INPUT]
- app.api.openai_compat.types::ChatCompletionRequest (POS: OpenAI request schema)
- app.api.openai_compat.auth::verify_api_key (POS: Bearer token auth)
- app.core.utils.session_id::is_safe_session_id (POS: safe chat_id whitelist guard)
- app.core.utils.errors::validation_error (POS: HTTP 400 factory)
- app.services.agent.streaming::ai_agent_service_stream (POS: Agent stream engine)
- app.services.agent.params::convert_to_general_agent_params (POS: Param builder)

[OUTPUT]
- chat_completions: POST /v1/chat/completions (streaming + non-streaming)

[POS]
Agent-only OpenAI-compatible API. External tools call this endpoint to run Myrm
agents (memory, tools, skills) — not raw LLM passthrough.
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
from app.core.utils.errors import validation_error
from app.core.utils.session_id import is_safe_session_id
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
    """Build GeneralAgentParams from an OpenAI-compatible request."""
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
    params, _, _, _, _archive_restore_results = await convert_to_general_agent_params(agent_request, chat_history)

    if request.temperature is not None and params.model_cfg:
        # Dual-channel write: temperature 同时写入顶层字段与 model_kwargs，
        # 经 get_llm_from_config（顶层优先合并 model_kwargs）统一消费，
        # 保证 OpenAI-compat 请求的温度参数对主 agent 与 subagent 全链路生效。
        model_cfg = params.model_cfg
        merged_kwargs = dict(model_cfg.model_kwargs or {})
        merged_kwargs["temperature"] = request.temperature
        params.model_cfg = model_cfg.model_copy(
            update={
                "temperature": request.temperature,
                "model_kwargs": merged_kwargs,
            }
        )

    return params


def _normalize_agent_event(event: object) -> dict[str, object] | None:
    """Normalize harness/gateway stream events to a plain dict."""
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        dumped = event.model_dump()
        return dumped if isinstance(dumped, dict) else None
    if hasattr(event, "to_dict"):
        dumped = event.to_dict()
        return dumped if isinstance(dumped, dict) else None
    return None


def _extract_assistant_text(event: dict[str, object]) -> str:
    """Extract assistant-visible text from Agent SSE events."""
    event_type = event.get("type", "")
    if event_type == "message_chunk":
        content = event.get("content", "")
        return content if isinstance(content, str) else str(content) if content else ""
    if event_type != "message":
        return ""
    data = event.get("data", "")
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("content", "text"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return ""


async def _stream_response(
    request: ChatCompletionRequest,
) -> AsyncGenerator[str, None]:
    """Generate OpenAI-format SSE chunks from Agent stream."""
    from app.services.agent.runtime_context import (
        build_agent_runtime_context,
        resolve_stream_execution_mode,
    )

    params = await _build_agent_params(request)
    extra_context = await build_agent_runtime_context(execution_mode=resolve_stream_execution_mode())
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model_name = request.model

    first_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=model_name,
        choices=[StreamChoice(delta=DeltaMessage(role="assistant"), finish_reason=None)],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    async for event in ai_agent_service_stream(params, extra_context=extra_context):
        normalized = _normalize_agent_event(event)
        if normalized is None:
            continue

        event_type = normalized.get("type", "")
        if event_type in ("message", "message_chunk"):
            content = _extract_assistant_text(normalized)
            if content:
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
    """OpenAI-compatible chat completions endpoint (Agent execution only)."""
    if request.chat_id and not is_safe_session_id(request.chat_id):
        raise validation_error(f"Invalid chat_id: {request.chat_id!r}")

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

    from app.services.agent.runtime_context import (
        build_agent_runtime_context,
        resolve_stream_execution_mode,
    )

    params = await _build_agent_params(request)
    extra_context = await build_agent_runtime_context(execution_mode=resolve_stream_execution_mode())

    full_content = ""
    usage_data: dict[str, object] = {}

    async for event in ai_agent_service_stream(params, extra_context=extra_context):
        normalized = _normalize_agent_event(event)
        if normalized is None:
            continue

        event_type = normalized.get("type", "")
        if event_type in ("message", "message_chunk"):
            full_content += _extract_assistant_text(normalized)
        elif event_type == "message_end":
            usage_data = normalized.get("usage", {})
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
