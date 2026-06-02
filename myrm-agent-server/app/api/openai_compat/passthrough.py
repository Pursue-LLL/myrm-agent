"""OpenAI-compatible LLM passthrough — transparent API forwarding.

[INPUT]
- app.api.openai_compat.types (POS: OpenAI request/response types)
- app.core.channel_bridge.model_resolver::_extract_all_active_keys, _to_litellm_model (POS: Provider key extraction & LiteLLM model formatting)
- app.services.config.service::config_service (POS: Config service for provider settings)

[OUTPUT]
- is_passthrough_model: check if model field matches a configured LLM (not an Agent)
- passthrough_completion: execute LLM call via litellm and return OpenAI-format response

[POS]
LLM passthrough for the /v1/chat/completions endpoint. When the `model` field
matches a user-configured LLM model (e.g. "claude-3.5-sonnet") rather than an
Agent ID, this module forwards the request directly to the upstream LLM via
litellm — bypassing the Agent execution engine entirely. This turns MyrmAgent
into an OpenAI-compatible API proxy that external tools (Aider, Cline, Codex,
Continue) can connect to with zero configuration.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator

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

logger = logging.getLogger(__name__)


async def _load_providers_dict() -> dict[str, object] | None:
    """Load user's provider configuration directly from config_service.

    Uses config_service.get() instead of load_user_configs() to avoid
    ConfigIncompleteError when no default model is configured — passthrough
    doesn't need a default model, only the provider list.
    """
    try:
        from app.services.config.service import config_service

        record = await config_service.get("providers")
        if record is None:
            return None
        value = record.value if hasattr(record, "value") else record
        if isinstance(value, dict):
            return value
    except Exception:
        logger.debug("Failed to load providers config for passthrough", exc_info=True)
    return None


_AGENT_ALIAS_MODELS = frozenset({"default", "gpt-4", "gpt-4o", "gpt-3.5-turbo"})
_AGENT_IDS_CACHE_TTL = 30.0  # seconds
_agent_ids_cache: tuple[float, frozenset[str]] = (0.0, frozenset())


async def _is_agent_id(model: str) -> bool:
    """Check if the model field matches a known Agent ID (cached 30s)."""
    import time as _time

    if model in _AGENT_ALIAS_MODELS:
        return True

    global _agent_ids_cache  # noqa: PLW0603
    cached_at, cached_ids = _agent_ids_cache
    now = _time.monotonic()

    if now - cached_at >= _AGENT_IDS_CACHE_TTL:
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models.agent import Agent

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Agent.id).where(Agent.is_active.is_(True))
                )
                cached_ids = frozenset(row[0] for row in result.all())
                _agent_ids_cache = (now, cached_ids)
        except Exception:
            logger.debug("Failed to refresh agent ID cache", exc_info=True)

    return model in cached_ids


async def _is_proxy_enabled() -> bool:
    """Check if the LLM passthrough proxy is enabled in user settings."""
    try:
        from app.services.config.service import config_service

        record = await config_service.get("proxySettings")
        if record is None:
            return False
        value = record.value if hasattr(record, "value") else record
        if isinstance(value, dict):
            return bool(value.get("enabled", False))
    except Exception:
        logger.debug("Failed to check proxy enabled status", exc_info=True)
    return False


async def is_passthrough_model(model: str) -> bool:
    """Check if a model name should be routed to LLM passthrough.

    Requires proxySettings.enabled=True. Agents get priority — if the model
    field matches a known Agent ID or alias, it routes to the Agent engine.
    """
    if not await _is_proxy_enabled():
        return False

    if await _is_agent_id(model):
        return False

    providers_dict = await _load_providers_dict()
    if not providers_dict:
        return False

    providers_raw = providers_dict.get("providers")
    if not isinstance(providers_raw, list):
        return False

    model_lower = model.lower()
    for provider in providers_raw:
        if not isinstance(provider, dict):
            continue
        is_enabled = provider.get("isEnabled") or provider.get("enabled")
        if not is_enabled:
            continue
        if not provider.get("apiKeys"):
            continue

        enabled_models = provider.get("enabledModels", [])
        if not isinstance(enabled_models, list):
            continue

        for m in enabled_models:
            if isinstance(m, str) and m.lower() == model_lower:
                return True

        pid = str(provider.get("id", ""))
        if pid and model_lower.startswith(f"{pid}/"):
            return True

    return False


def _resolve_passthrough_provider(
    model: str,
    providers_dict: dict[str, object],
) -> tuple[str, str, str | None]:
    """Find the provider that owns ``model`` and return litellm-ready credentials.

    Unlike ``resolve_model_config`` (designed for Agent engine, expects LiteLLM
    format ``provider/model``), this function matches bare model names (e.g.
    ``claude-sonnet-4-20250514``) against each provider's ``enabledModels``.

    Returns:
        (litellm_model, api_key, base_url | None)

    Raises:
        ValueError: if no matching provider is found.
    """
    from app.core.channel_bridge.model_resolver import (
        _extract_all_active_keys,
        _to_litellm_model,
    )

    providers_raw = providers_dict.get("providers")
    if not isinstance(providers_raw, list):
        raise ValueError(f"No providers configured for model '{model}'")

    model_lower = model.lower()

    for provider in providers_raw:
        if not isinstance(provider, dict):
            continue
        is_enabled = provider.get("isEnabled") or provider.get("enabled")
        if not is_enabled:
            continue

        pid = str(provider.get("id", ""))
        ptype = str(provider.get("providerType", "")) or None

        enabled_models = provider.get("enabledModels", [])
        matched_raw_model: str | None = None

        if isinstance(enabled_models, list):
            for m in enabled_models:
                if isinstance(m, str) and m.lower() == model_lower:
                    matched_raw_model = m
                    break

        if matched_raw_model is None and pid and model_lower.startswith(f"{pid}/"):
            matched_raw_model = model.split("/", 1)[1]

        if matched_raw_model is None:
            continue

        keys = _extract_all_active_keys(provider)
        if not keys:
            continue

        litellm_model = _to_litellm_model(pid, matched_raw_model, ptype)
        api_url = str(provider.get("apiUrl") or provider.get("baseURL") or "")

        return litellm_model, keys[0], api_url or None

    raise ValueError(f"Model '{model}' not found in any enabled provider")


async def _build_litellm_kwargs(
    request: ChatCompletionRequest,
    *,
    stream: bool,
) -> dict[str, object]:
    """Build litellm.acompletion kwargs from request + user provider config."""
    providers_dict = await _load_providers_dict()
    if not providers_dict:
        raise ValueError("No providers configuration available")

    litellm_model, api_key, base_url = _resolve_passthrough_provider(
        request.model, providers_dict,
    )

    messages = [
        {"role": m.role, "content": m.content if isinstance(m.content, str) else m.content}
        for m in request.messages
    ]

    kwargs: dict[str, object] = {
        "model": litellm_model,
        "messages": messages,
        "api_key": api_key,
        "stream": stream,
    }
    if base_url:
        kwargs["api_base"] = base_url

    optional_params: list[str] = [
        "temperature", "max_tokens", "top_p", "stop",
        "presence_penalty", "frequency_penalty",
    ]
    for param in optional_params:
        value = getattr(request, param, None)
        if value is not None:
            kwargs[param] = value

    return kwargs


async def passthrough_stream(
    request: ChatCompletionRequest,
) -> AsyncGenerator[str, None]:
    """Stream LLM response in OpenAI SSE format via litellm."""
    import litellm

    try:
        litellm_kwargs = await _build_litellm_kwargs(request, stream=True)
    except (ValueError, Exception) as exc:
        error_body = json.dumps({
            "error": {
                "message": str(exc),
                "type": "configuration_error",
                "code": "passthrough_config_error",
            }
        })
        yield f"data: {error_body}\n\n"
        yield "data: [DONE]\n\n"
        return

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    first_chunk = ChatCompletionChunk(
        id=completion_id,
        created=created,
        model=request.model,
        choices=[StreamChoice(delta=DeltaMessage(role="assistant"), finish_reason=None)],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    try:
        response = await litellm.acompletion(**litellm_kwargs)
        async for part in response:
            delta_content = None
            finish = None

            if hasattr(part, "choices") and part.choices:
                choice = part.choices[0]
                if hasattr(choice, "delta") and choice.delta:
                    delta_content = getattr(choice.delta, "content", None)
                finish = getattr(choice, "finish_reason", None)

            if delta_content:
                chunk = ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=request.model,
                    choices=[StreamChoice(
                        delta=DeltaMessage(content=delta_content),
                        finish_reason=None,
                    )],
                )
                yield f"data: {chunk.model_dump_json()}\n\n"

            if finish:
                finish_chunk = ChatCompletionChunk(
                    id=completion_id,
                    created=created,
                    model=request.model,
                    choices=[StreamChoice(
                        delta=DeltaMessage(),
                        finish_reason=finish,
                    )],
                )
                yield f"data: {finish_chunk.model_dump_json()}\n\n"

    except Exception as exc:
        error_body = json.dumps({
            "error": {
                "message": str(exc),
                "type": "upstream_error",
                "code": "passthrough_error",
            }
        })
        yield f"data: {error_body}\n\n"

    yield "data: [DONE]\n\n"


async def passthrough_completion(
    request: ChatCompletionRequest,
) -> ChatCompletionResponse:
    """Non-streaming LLM completion via litellm."""
    import litellm
    from fastapi import HTTPException

    try:
        litellm_kwargs = await _build_litellm_kwargs(request, stream=False)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "message": str(exc),
                    "type": "configuration_error",
                    "code": "passthrough_config_error",
                }
            },
        ) from exc

    try:
        response = await litellm.acompletion(**litellm_kwargs)
    except Exception as exc:
        logger.warning("Passthrough completion failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={
                "error": {
                    "message": f"Upstream LLM error: {exc}",
                    "type": "upstream_error",
                    "code": "passthrough_error",
                }
            },
        ) from exc

    content = ""
    usage_info = UsageInfo()

    if hasattr(response, "choices") and response.choices:
        msg = response.choices[0].message
        content = getattr(msg, "content", "") or ""

    if hasattr(response, "usage") and response.usage:
        usage_info = UsageInfo(
            prompt_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(response.usage, "total_tokens", 0) or 0,
        )

    return ChatCompletionResponse(
        model=request.model,
        choices=[Choice(message=ChoiceMessage(content=content))],
        usage=usage_info,
    )
