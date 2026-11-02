"""LangChain chat model over the model transport

[INPUT]
- langchain_core (POS: BaseChatModel base class, message, runnable, tool and env-lookup helpers)
- transport::LLMTransport, get_transport (POS: provider transport the adapter calls; injectable for tests)
- adapters.chat_model.message_mixin / output_cap_recovery / session_affinity / sync_mixin / async_mixin / async_stream_mixin (POS: request assembly, output-limit recovery and generation behavior composed into the aggregate root)
- adapters.chat_model.binding (POS: bind_tools and with_structured_output assembly)
- adapters.chat_model.exceptions (POS: adapter exceptions and constants)
- adapters.metrics::EmptyRetryMetrics (POS: empty-response retry counters)
- core.config.wire::WireProtocol (POS: wire protocol selection)
- core.context_vars::prompt_routing_key_var, chat_id_var (POS: Session-scoped routing key for OpenCode gateway session affinity)
- toolkits.llms.utils.proxy::normalize_proxy_url (POS: Egress proxy URL normalization)
- toolkits.llms.utils.model_kwargs::clean_model_kwargs, should_skip_response_format (POS: Model-parameter compatibility helpers)
- toolkits.llms.utils.json_document::is_json_document (POS: whether reasoning text is a JSON document the output parser accepts)

[OUTPUT]
- TransportChatModel: LangChain-compatible chat model aggregate root (config, bind_tools, structured_output)
- chat_model.message_mixin / chat_model.session_affinity / chat_model.sync_mixin / chat_model.async_mixin / chat_model.async_stream_mixin : message assembly, session-affinity and generation mixins
- chat_model.binding: tool_bind_kwargs / structured_output_bind_kwargs / structured_output_chain (bind_tools and with_structured_output assembly)
- chat_model.exceptions: EmptyChoicesError, EmptyStreamError, adapter constants
- clean_model_kwargs(): utility function to clean model parameters

[POS]
LangChain chat-model adapter. Provides a LangChain-compatible chat model for unified multi-model
invocation. Supports sync/async calls, streaming responses (with TTFT and duration latency tracking),
tool calling, structured output, and model native search (web_search_options).
Records token usage + cost calculation + audit log appending for every call (streaming and non-streaming),
with TTFT/duration stats collected on the streaming path.
**Empty response retry**: covers Sync/Async/Stream, configurable retry count (1-10) and delay (0.1-10.0s);
Stream only supports fully empty stream retry (mid-stream interruptions cannot be retried).
**Metrics observability**: instance-level EmptyRetryMetrics tracks retry count, success rate, total delay;
business layer exports via retry_metrics.to_dict() for monitoring integration.
**Structured output**: an empty answer retries once without ``response_format``; the model's reasoning
replaces it only when the reasoning is itself a JSON document the output parser accepts.
**Parameter fidelity**: every parameter the framework or the caller sets reaches the provider request; the transport
never filters by a provider capability table. Each protocol wire translates the OpenAI-shaped parameters into the
provider's own request body, so protocol-specific rejections are handled in one place per wire.
Cross-provider compatible via the model transport. As the adapter layer, used by core.llm and business layer,
bridging LangChain and the transport.
Provider-aware message normalization keeps providers that reject ``system`` turns
(for example MiniMax) on the compatibility path without leaking that concern to callers.
For OpenAI GPT-5+/Codex/o-series models, promotes ``system`` role to ``developer``
following OpenAI's recommended priority hierarchy (system > developer > user).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import (
    Any,
    TypeVar,
)

from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import (
    Runnable,
    RunnableConfig,
)
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr, model_validator

from myrm_agent_harness.core.config.wire import DEFAULT_WIRE_PROTOCOL, WireProtocol
from myrm_agent_harness.toolkits.llms.adapters.chat_model.async_mixin import TransportChatModelAsyncMixin
from myrm_agent_harness.toolkits.llms.adapters.chat_model.async_stream_mixin import TransportChatModelAsyncStreamMixin
from myrm_agent_harness.toolkits.llms.adapters.chat_model.binding import (
    structured_output_bind_kwargs,
    structured_output_chain,
    tool_bind_kwargs,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model.exceptions import (
    DEVELOPER_ROLE_PATTERN,
    EmptyChoicesError,
    EmptyStreamError,
    StreamStallTimeoutError,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model.message_mixin import TransportChatModelMessageMixin
from myrm_agent_harness.toolkits.llms.adapters.chat_model.output_cap_recovery import TransportChatModelOutputCapMixin
from myrm_agent_harness.toolkits.llms.adapters.chat_model.session_affinity import TransportChatModelSessionAffinityMixin
from myrm_agent_harness.toolkits.llms.adapters.chat_model.sync_mixin import TransportChatModelSyncMixin
from myrm_agent_harness.toolkits.llms.adapters.metrics import EmptyRetryMetrics
from myrm_agent_harness.toolkits.llms.transport import LLMTransport, get_transport
from myrm_agent_harness.toolkits.llms.utils.json_document import is_json_document
from myrm_agent_harness.toolkits.llms.utils.model_kwargs import (
    clean_model_kwargs as utils_clean_model_kwargs,
)
from myrm_agent_harness.toolkits.llms.utils.model_kwargs import (
    should_skip_response_format,
)
from myrm_agent_harness.toolkits.llms.utils.proxy import normalize_proxy_url

_BM = TypeVar("_BM", bound=BaseModel)

logger = logging.getLogger(__name__)

__all__ = [
    "DEVELOPER_ROLE_PATTERN",
    "TransportChatModel",
    "EmptyChoicesError",
    "EmptyStreamError",
    "StreamStallTimeoutError",
    "clean_model_kwargs",
]


class TransportChatModel(
    TransportChatModelMessageMixin,
    TransportChatModelOutputCapMixin,
    TransportChatModelSessionAffinityMixin,
    TransportChatModelSyncMixin,
    TransportChatModelAsyncMixin,
    TransportChatModelAsyncStreamMixin,
    BaseChatModel,
):
    """Minimal LangChain ChatModel adapter over the model transport.

    Implements the subset of features this project uses: non-streaming/streaming
    chat completions and compatibility with LangChain Runnable API.
    """

    client: LLMTransport | None = None
    model: str = "gpt-3.5-turbo"
    model_name: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    organization: str | None = None
    custom_llm_provider: str | None = None
    # Seconds to wait for the provider's next bytes, handed to the transport as ``timeout``: a stream that keeps producing
    # is not cut, a silent provider is. ``first_event_timeout`` and ``inter_chunk_timeout`` guard a started stream.
    request_timeout: float | None = 300.0
    temperature: float | None = None
    model_kwargs: dict[str, Any] = Field(default_factory=dict)
    extra_body: dict[str, Any] | None = Field(default=None)
    web_search_options: dict[str, Any] | None = Field(
        default=None,
        description="web_search_options for native search (auto-detected or explicit)",
    )
    top_p: float | None = None
    top_k: int | None = None
    n: int | None = None
    max_tokens: int | None = None
    reasoning_effort: str | None = Field(
        default=None,
        description="Reasoning effort level (e.g. low, medium, high, max)",
    )
    streaming: bool = False
    egress_proxy: str | None = Field(
        default=None,
        description="Egress HTTP/SOCKS5 proxy URL for outbound API requests",
    )
    empty_retry_enabled: bool = Field(
        default=True,
        description="Enable retry on empty response (EmptyChoicesError/EmptyStreamError)",
    )
    empty_retry_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum retry attempts for empty response (1-10)",
    )
    empty_retry_delay: float = Field(
        default=0.5,
        ge=0.1,
        le=10.0,
        description="Delay between retries in seconds (0.1-10.0)",
    )
    first_event_timeout: float = Field(
        default=60.0,
        ge=5.0,
        description="Max seconds to wait for the first stream event after HTTP 200. "
        "Reasoning models may need higher values (e.g. 120-180s).",
    )
    inter_chunk_timeout: float = Field(
        default=180.0,
        ge=10.0,
        description="Max seconds between consecutive stream chunks. "
        "Detects mid-stream stalls caused by proxy buffering or provider GC.",
    )
    wire_protocol: WireProtocol = Field(
        default=DEFAULT_WIRE_PROTOCOL,
        description="HTTP wire transport: chat_completions, responses, or anthropic_messages",
    )

    # Private attribute for metrics (Pydantic v2 PrivateAttr)
    _retry_metrics: EmptyRetryMetrics = PrivateAttr(default_factory=EmptyRetryMetrics)

    @property
    def retry_metrics(self) -> EmptyRetryMetrics:
        """Get retry metrics for observability."""
        return self._retry_metrics

    def uses_responses_wire(self) -> bool:
        return self.wire_protocol == "responses"

    @property
    def base_url(self) -> str | None:
        """Compatibility alias for ``api_base``.

        Downstream consumers (error diagnostics, capability learning) read the
        API base URL via ``getattr(llm, "base_url")``; the canonical field on
        this class is ``api_base``.
        """
        return self.api_base

    @model_validator(mode="before")
    @classmethod
    def validate_environment(cls, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("client") is None:
            values["client"] = get_transport()
        return values

    @property
    def _default_params(self) -> dict[str, Any]:
        set_model_value = self.model_name or self.model
        params = {
            "model": set_model_value,
            "timeout": self.request_timeout,
            "max_tokens": self.max_tokens,
            "stream": self.streaming,
            "n": self.n,
            "temperature": self.temperature,
            "custom_llm_provider": self.custom_llm_provider,
            **self.model_kwargs,
        }
        # Sampling options a user sets in the model configuration: OpenAI-shaped bodies also get them through the
        # factory's extra_body mirror, the wires with their own protocol (Gemini, Ollama, Responses, Anthropic) only here.
        for name, value in (("top_p", self.top_p), ("top_k", self.top_k)):
            if value is not None:
                params[name] = value
        if self.extra_body:
            params["extra_body"] = self.extra_body
        if self.reasoning_effort is not None:
            params["reasoning_effort"] = self.reasoning_effort
        if self.web_search_options is not None:
            params["web_search_options"] = self.web_search_options
        return params

    @property
    def _client_params(self) -> dict[str, Any]:
        set_model_value = self.model_name or self.model
        creds: dict[str, Any] = {
            "model": set_model_value,
            "api_base": self.api_base,
            "api_key": self.api_key,
            "organization": self.organization,
        }
        if self.egress_proxy:
            normalized_proxy = normalize_proxy_url(self.egress_proxy)
            if normalized_proxy:
                creds["proxy"] = normalized_proxy

        # Caller headers plus gateway affinity; each wire adds its own credential header.
        raw_extra_headers = self.model_kwargs.get("extra_headers")
        extra_headers: dict[str, str] = dict(raw_extra_headers) if isinstance(raw_extra_headers, dict) else {}

        if self._is_opencode_endpoint() and not any(k.lower() == "x-opencode-session" for k in extra_headers):
            from myrm_agent_harness.core.context_vars import (
                chat_id_var,
                prompt_routing_key_var,
            )

            session_val = prompt_routing_key_var.get() or chat_id_var.get() or "sess-default-open-affinity"
            extra_headers["x-opencode-session"] = session_val

        if extra_headers:
            creds["extra_headers"] = extra_headers

        return {**self._default_params, **creds}

    @property
    def _identifying_params(self) -> dict[str, Any]:
        set_model_value = self.model_name or self.model
        return {
            "model": set_model_value,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "n": self.n,
        }

    @property
    def _llm_type(self) -> str:
        return "transport-chat"

    @staticmethod
    def should_skip_response_format(model: str) -> bool:
        return should_skip_response_format(model)

    @staticmethod
    def clean_model_kwargs(
        kwargs: dict[str, Any],
        model: str,
        additional_remove_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        return dict(utils_clean_model_kwargs(kwargs, model, additional_remove_keys))

    def _get_model_name(self) -> str:
        return getattr(self, "model", "") or getattr(self, "model_name", "") or ""

    async def ainvoke(
        self,
        input: LanguageModelInput,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AIMessage:
        logger.debug(f"ainvoke kwargs keys: {list(kwargs.keys())}")
        if "tools" in kwargs:
            logger.debug(f"ainvoke tools count: {len(kwargs.get('tools', []))}")
        if kwargs.get("_in_fallback", False):
            return await super().ainvoke(input, config, **self.clean_model_kwargs(kwargs, self._get_model_name()))

        result = await super().ainvoke(input, config, **kwargs)
        if not kwargs.get("_json_mode_fallback", False):
            return result

        if result.content and (isinstance(result.content, str) and result.content.strip()):
            return result

        reasoning_content = getattr(result, "additional_kwargs", {}).get("reasoning_content")
        if isinstance(reasoning_content, str) and is_json_document(reasoning_content):
            return AIMessage(
                content=reasoning_content.strip(),
                additional_kwargs=getattr(result, "additional_kwargs", {}),
            )

        fallback_kwargs = self.clean_model_kwargs(kwargs, self._get_model_name())
        fallback_kwargs["_in_fallback"] = True
        return await super().ainvoke(input, config, **fallback_kwargs)

    def with_structured_output(
        self,
        schema: dict[str, Any] | type[_BM] | type | None = None,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | _BM]:
        if kwargs:
            raise ValueError(f"Received unsupported arguments {kwargs}")
        bind_kwargs = structured_output_bind_kwargs(
            schema, skip_response_format=self.should_skip_response_format(self._get_model_name())
        )
        return structured_output_chain(self.bind(**bind_kwargs), schema, include_raw=include_raw)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool | Any],
        *,
        tool_choice: str | dict[str, Any] | None = None,
        parallel_tool_calls: bool | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        bind_kwargs = tool_bind_kwargs(
            tools,
            model_id=self.model_name or self.model,
            api_base=str(self.api_base or ""),
            custom_llm_provider=str(self.custom_llm_provider or ""),
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
            extra=kwargs,
        )
        return self.bind(**bind_kwargs)


def clean_model_kwargs(
    kwargs: dict[str, Any],
    model: str,
    additional_remove_keys: list[str] | None = None,
) -> dict[str, Any]:
    return TransportChatModel.clean_model_kwargs(kwargs, model, additional_remove_keys)
