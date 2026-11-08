"""LLM Core — model factory

Review agent/context_management/PROMPT_CACHE_PRACTICE.md §6.1-6.2 whenever this file changes.

[INPUT]
- adapters.chat_model::TransportChatModel, clean_model_kwargs (POS: LangChain adapter)
- catalog::supports_web_search (POS: model native search capability detection)
- transport::speaks_openai_body (POS: whether the provider takes an OpenAI-shaped request body)

[OUTPUT]
- create_chat_model(): factory function to create chat model instances
- TransportChatModel: LangChain-compatible chat model (re-exported from adapter)

[POS]
LLM core. Unified multi-model invocation interface (OpenAI, Anthropic, Gemini, etc.).
Provides a factory function to create chat model instances,
automatically merging model_kwargs into extra_body (only for providers that take an OpenAI-shaped body;
Anthropic, Gemini and Ollama build their own request body and reject unknown top-level fields). Integrates reasoning_timeout floor,
thinking model max_tokens headroom (auto-raise floor to prevent thinking-phase truncation),
local endpoint stall-detection relaxation (auto-detect localhost/RFC1918 → relax first_event/
inter_chunk/request timeouts), Ollama-scoped 64k context window (options.num_ctx injected only for
Ollama endpoints, since other OpenAI-compatible local gateways reject Ollama option objects),
OpenRouter reasoning_effort → reasoning.effort rewrite,
and native model capability passthrough (web_search_options) via tri-state native_tools config
(None=auto-detect / set=explicit / empty set=disabled).
Core layer used by LLMManager and business layer as the unified entry point for multi-model calls.
"""

import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

from myrm_agent_harness.core.config.wire import DEFAULT_WIRE_PROTOCOL, WireProtocol
from myrm_agent_harness.toolkits.llms.adapters.chat_model import (
    TransportChatModel as TransportChatModel,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model import (
    clean_model_kwargs as clean_model_kwargs,
)
from myrm_agent_harness.toolkits.llms.catalog import supports_web_search
from myrm_agent_harness.toolkits.llms.core.deepseek_reasoning import apply_deepseek_reasoning_effort
from myrm_agent_harness.toolkits.llms.core.openai_reasoning import apply_openai_reasoning_effort
from myrm_agent_harness.toolkits.llms.core.openrouter_verbosity import apply_openrouter_reasoning_effort
from myrm_agent_harness.toolkits.llms.core.reasoning_timeout import get_reasoning_timeout_floor
from myrm_agent_harness.toolkits.llms.core.thinking_headroom import ensure_thinking_headroom
from myrm_agent_harness.toolkits.llms.transport import speaks_openai_body

logger = logging.getLogger(__name__)

# Explicit cache (Claude/Qwen): controlled by Pipeline ExplicitCacheProcessor
# via dynamic cache_control injection in message additional_kwargs.
# OpenAI/DeepSeek/Gemini: rely on API auto-prefix cache, no explicit processing needed.

_LOCAL_FIRST_EVENT_TIMEOUT = 300.0
_LOCAL_INTER_CHUNK_TIMEOUT = 600.0
_LOCAL_REQUEST_TIMEOUT = 1800.0
_OLLAMA_DEFAULT_PORT = 11434


def _is_local_endpoint(url: str | None) -> bool:
    """Detect whether a URL points to a local/private-network LLM service.

    Local models (Ollama, LM Studio, vLLM) have zero network latency but
    potentially long compute latency (prefill). Stall detection thresholds
    designed for cloud APIs will cause false kills on local endpoints.
    """
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", "0.0.0.0"):  # noqa: S104  # hostname compare, not a bind
        return True
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def _is_ollama_endpoint(url: str | None, model: str | None) -> bool:
    """Detect Ollama specifically.

    Ollama accepts ``options.num_ctx``; other local OpenAI-compatible gateways
    (LiteLLM proxy, OmniRoute, vLLM) reject Ollama-specific option objects.
    """
    if model:
        parts = model.lower().split("/")
        if parts[0] == "ollama" or (len(parts) > 1 and "ollama" in parts[1]):
            return True
    if not url:
        return False
    if "ollama" in url.lower():
        return True
    try:
        return urlparse(url).port == _OLLAMA_DEFAULT_PORT
    except ValueError:
        return False


# Kwargs the extra_body mirror must never copy:
# - max_tokens: extra_body is laid over the typed fields on the wire, so a mirrored cap would overwrite the
#   headroom-adjusted (and truncation-boosted) value.
# - extra_body: copying a dict into itself makes a self-reference that cannot be serialized.
# - supports_reasoning: factory-only switch that no provider understands.
# - the rest are TransportChatModel's own configuration (timeouts, retry policy, routing); they configure the call and
#   are never request-body fields.
_NEVER_MIRRORED = frozenset(
    {
        "max_tokens",
        "extra_body",
        "supports_reasoning",
        "model_kwargs",
        "custom_llm_provider",
        "wire_protocol",
        "egress_proxy",
        "streaming",
        "request_timeout",
        "first_event_timeout",
        "inter_chunk_timeout",
        "empty_retry_enabled",
        "empty_retry_max_attempts",
        "empty_retry_delay",
    }
)


def _merge_model_kwargs_to_extra_body(llm_kwargs: dict[str, Any], model_kwargs: dict[str, Any] | None) -> None:
    """Mirror model_kwargs into extra_body for cross-provider compatibility.

    Factory keyword arguments that are not adapter fields (``frequency_penalty``, ``thinking``, ...) reach the provider
    only through ``extra_body``. The caller's own ``extra_body`` is copied rather than mutated, and its keys win.

    Args:
        llm_kwargs: LLM parameter dict (mutated in place).
        model_kwargs: Model-specific custom parameters.
    """
    if not model_kwargs:
        return

    current = llm_kwargs.get("extra_body")
    extra_body = dict(current) if isinstance(current, dict) else {}
    for key, value in model_kwargs.items():
        if key not in _NEVER_MIRRORED:
            extra_body.setdefault(key, value)
    if extra_body:
        llm_kwargs["extra_body"] = extra_body


def _resolve_web_search_options(
    model: str,
    native_tools: set[str] | None,
    web_search_options: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve web_search_options based on native_tools configuration.

    Three-state logic:
    - native_tools is None (default): auto-detect via the model catalog
    - native_tools contains "web_search": explicitly enable
    - native_tools is empty set: explicitly disable all native tools

    Args:
        model: Model identifier for auto-detection
        native_tools: User-configured native tools (None = auto-detect)
        web_search_options: Explicit web_search_options override

    Returns:
        web_search_options dict if native search should be enabled, None otherwise
    """
    if web_search_options is not None:
        return web_search_options

    if native_tools is not None:
        if "web_search" in native_tools:
            return {}
        return None

    if supports_web_search(model):
        logger.info("Model '%s' supports native web search (auto-detected)", model)
        return {}
    return None


def create_chat_model(
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    streaming: bool = False,
    native_tools: set[str] | None = None,
    web_search_options: dict[str, Any] | None = None,
    wire_protocol: WireProtocol = DEFAULT_WIRE_PROTOCOL,
    reasoning_effort: str | None = None,
    egress_proxy: str | None = None,
    **kwargs: Any,
) -> "TransportChatModel":
    """Unified factory for creating TransportChatModel instances across all providers.

    Explicit cache (Claude/Qwen) is controlled by ExplicitCacheProcessor.
    Implicit cache (OpenAI/DeepSeek/Gemini) relies on API auto-prefix cache.

    Args:
        model: Model identifier (e.g. "gpt-4o", "claude-3-opus").
        base_url: Custom API base URL.
        api_key: API key for authentication.
        temperature: Sampling temperature.
        streaming: Enable streaming output.
        native_tools: Model native tools config (None=auto-detect, set=explicit, empty set=disable).
        web_search_options: Explicit web_search_options override.
        egress_proxy: Optional outbound proxy URL for LLM API calls.
        **kwargs: Additional model-specific parameters (e.g. model_kwargs, max_tokens).

    Returns:
        Configured TransportChatModel instance.
    """
    llm_kwargs: dict[str, Any] = {"model": model, "wire_protocol": wire_protocol, **kwargs}
    custom_provider = llm_kwargs.get("custom_llm_provider")
    openai_body = wire_protocol != "anthropic_messages" and speaks_openai_body(
        model, api_base=base_url, custom_llm_provider=custom_provider if isinstance(custom_provider, str) else None
    )
    if egress_proxy is not None:
        llm_kwargs["egress_proxy"] = egress_proxy
    if reasoning_effort is not None:
        llm_kwargs["reasoning_effort"] = reasoning_effort
        if openai_body:
            caller_extra_body = llm_kwargs.get("extra_body")
            llm_kwargs["extra_body"] = {
                "reasoning_effort": reasoning_effort,
                **(caller_extra_body if isinstance(caller_extra_body, dict) else {}),
            }
    if temperature is not None:
        llm_kwargs["temperature"] = temperature

    if base_url:
        llm_kwargs["api_base"] = base_url

    if api_key:
        llm_kwargs["api_key"] = api_key

    if streaming:
        llm_kwargs["streaming"] = streaming

    # Merge kwargs into extra_body so non-field kwargs reach the provider. Providers with their own protocol build
    # the body from typed parameters and reject unknown top-level fields, so only OpenAI-shaped bodies take them.
    if openai_body:
        _merge_model_kwargs_to_extra_body(llm_kwargs, kwargs)

    # DeepSeek: normalize reasoning_effort ('off'|'low'|'high'|'max') & thinking ('enabled'|'disabled')
    apply_deepseek_reasoning_effort(model, llm_kwargs)

    # OpenRouter: rewrite reasoning_effort → extra_body.reasoning.effort
    apply_openrouter_reasoning_effort(model, llm_kwargs)

    # OpenAI: remap non-standard reasoning levels ('minimal'→'low', 'xhigh'→'high') & strip for non-reasoning
    apply_openai_reasoning_effort(model, llm_kwargs)

    # Thinking models: raise max_tokens floor to prevent thinking-phase truncation
    ensure_thinking_headroom(model, llm_kwargs)

    resolved_wso = _resolve_web_search_options(model, native_tools, web_search_options)
    if resolved_wso is not None:
        llm_kwargs["web_search_options"] = resolved_wso

    # Capture user-explicit timeout keys before internal processing
    user_explicit_timeouts = frozenset(
        k for k in ("request_timeout", "first_event_timeout", "inter_chunk_timeout") if k in llm_kwargs
    )

    # Apply reasoning model timeout floor (e.g. o3 needs 600s for thinking phase)
    reasoning_floor = get_reasoning_timeout_floor(model, llm_kwargs)

    if "request_timeout" not in llm_kwargs and reasoning_floor is not None:
        llm_kwargs["request_timeout"] = reasoning_floor

    if "first_event_timeout" not in llm_kwargs and reasoning_floor is not None:
        llm_kwargs["first_event_timeout"] = min(reasoning_floor / 2, 300.0)

    # Local endpoints: relax stall detection to avoid killing long prefills.
    # Use max() for non-user-explicit keys so reasoning models on local hardware
    # get at least the local relaxation threshold (not clamped to cloud-speed floors).
    if _is_local_endpoint(base_url):
        logger.info("Local endpoint detected (%s), relaxing stall timeouts", base_url)
        for key, local_val in (
            ("first_event_timeout", _LOCAL_FIRST_EVENT_TIMEOUT),
            ("inter_chunk_timeout", _LOCAL_INTER_CHUNK_TIMEOUT),
            ("request_timeout", _LOCAL_REQUEST_TIMEOUT),
        ):
            if key in user_explicit_timeouts:
                continue
            current = llm_kwargs.get(key)
            if not isinstance(current, (int, float)) or current < local_val:
                llm_kwargs[key] = local_val

    # Ollama only: share the 64k agentic context window through options.num_ctx
    if _is_ollama_endpoint(base_url, model):
        extra_body = llm_kwargs.setdefault("extra_body", {})
        if isinstance(extra_body, dict):
            options = extra_body.setdefault("options", {})
            if isinstance(options, dict) and "num_ctx" not in options:
                options["num_ctx"] = 64000

    # Vercel AI Gateway: auto-inject attribution headers for spend observability
    if base_url and "ai-gateway.vercel.sh" in base_url.lower():
        extra_headers = llm_kwargs.setdefault("extra_headers", {})
        if isinstance(extra_headers, dict):
            extra_headers.setdefault("HTTP-Referer", "https://myrm.ai")
            extra_headers.setdefault("X-Title", "Myrm Agent")
            extra_headers.setdefault("User-Agent", "Myrm/1.0 (Vercel-AI-Gateway-Client)")
        model_kwargs_dict = llm_kwargs.setdefault("model_kwargs", {})
        if isinstance(model_kwargs_dict, dict):
            extra_headers_m = model_kwargs_dict.setdefault("extra_headers", {})
            if isinstance(extra_headers_m, dict):
                extra_headers_m.setdefault("HTTP-Referer", "https://myrm.ai")
                extra_headers_m.setdefault("X-Title", "Myrm Agent")
                extra_headers_m.setdefault("User-Agent", "Myrm/1.0 (Vercel-AI-Gateway-Client)")

    # OpenRouter: auto-inject attribution headers for ranking & free tier compliance
    if (base_url and "openrouter.ai" in base_url.lower()) or model.lower().startswith("openrouter/"):
        extra_headers = llm_kwargs.setdefault("extra_headers", {})
        if isinstance(extra_headers, dict):
            extra_headers.setdefault("HTTP-Referer", "https://myrm.ai")
            extra_headers.setdefault("X-Title", "Myrm Agent")
        model_kwargs_dict = llm_kwargs.setdefault("model_kwargs", {})
        if isinstance(model_kwargs_dict, dict):
            extra_headers_m = model_kwargs_dict.setdefault("extra_headers", {})
            if isinstance(extra_headers_m, dict):
                extra_headers_m.setdefault("HTTP-Referer", "https://myrm.ai")
                extra_headers_m.setdefault("X-Title", "Myrm Agent")

    llm_kwargs = clean_model_kwargs(llm_kwargs, model)

    return TransportChatModel(**llm_kwargs)
