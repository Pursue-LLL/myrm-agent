"""ChatLiteLLM asynchronous non-streaming generation mixin.

[INPUT]
- adapters.chat_model.exceptions (POS: EmptyChoicesError)
- adapters.chat_model.api_key_refresher (POS: host-registered renewal of an expiring api key)
- adapters.chat_model.memo_wiring (POS: model-call memo replay and recording)
- adapters.concurrency (POS: per-model semaphores)
- infra.tracing.gen_ai::ModelCall (POS: one `chat` span and its metrics per logical model call)
- utils.token_economics (POS: usage recording for non-streaming calls — lazy import)

[OUTPUT]
- ChatLiteLLMAsyncMixin: _agenerate (empty-response retry, api key renewal before each request; delegates streaming to the stream mixin)

[POS]
Asynchronous non-streaming LLM generation path for ChatLiteLLM with concurrency gate and unified
token-usage recording. One call is one `chat` span however many attempts it takes; retries appear
as events on that span.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from langchain_core.language_models.chat_models import agenerate_from_stream
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult

from myrm_agent_harness.infra.tracing.gen_ai import ModelCall
from myrm_agent_harness.toolkits.llms.adapters.chat_model.api_key_refresher import renew_api_key
from myrm_agent_harness.toolkits.llms.adapters.chat_model.exceptions import EmptyChoicesError
from myrm_agent_harness.toolkits.llms.adapters.chat_model.memo_wiring import memo_run
from myrm_agent_harness.toolkits.llms.adapters.chat_model.model_provider import model_provider_name
from myrm_agent_harness.toolkits.llms.adapters.concurrency import (
    bounded_model_call,
)
from myrm_agent_harness.toolkits.llms.adapters.gateway_normalizer import (
    is_gateway_param_rejection,
    sanitize_gateway_params_on_400,
)
from myrm_agent_harness.toolkits.llms.adapters.image_payload_evictor import (
    emergency_evict,
    emergency_evict_from_message_dicts,
)
from myrm_agent_harness.toolkits.llms.adapters.metrics import EmptyRetryMetrics
from myrm_agent_harness.toolkits.llms.adapters.wire.anthropic_params import (
    apply_anthropic_messages_params,
)
from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import (
    invoke_responses_async,
)
from myrm_agent_harness.toolkits.llms.errors.classifier import (
    is_context_overflow,
    is_payload_overflow,
)

logger = logging.getLogger(__name__)


class ChatLiteLLMAsyncMixin:
    if TYPE_CHECKING:
        # Attributes and sibling-mixin methods defined on the ChatLiteLLM aggregate
        # root; declared here so mypy understands the composition-mixin pattern.
        api_base: str | None
        api_key: str | None
        openai_api_key: str | None
        client: Any
        model: str
        model_name: str | None
        streaming: bool
        custom_llm_provider: str | None
        empty_retry_enabled: bool
        empty_retry_max_attempts: int
        empty_retry_delay: float
        _retry_metrics: EmptyRetryMetrics
        _create_chat_result: Callable[..., ChatResult]
        _convert_response_to_dict: Callable[..., dict[str, Any]]
        _extract_tool_context_from_kwargs: Callable[..., tuple[list[str] | None, dict[str, dict[str, Any]] | None]]
        _create_message_dicts: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]]
        _inject_allowed_params: Callable[..., None]
        _apply_output_budget: Callable[..., None]
        _recover_output_cap: Callable[..., bool]
        _inject_prompt_routing_key: Callable[..., None]
        _record_non_stream_usage: Callable[..., None]
        _astream: Callable[..., Any]

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        should_stream = kwargs.get("streaming", self.streaming)
        if should_stream:
            return await self._agenerate_inner(messages, stop, run_manager, **kwargs)

        async with bounded_model_call(self.model_name or self.model):
            return await self._agenerate_inner(messages, stop, run_manager, **kwargs)

    async def _agenerate_inner(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        should_stream = kwargs.pop("streaming", self.streaming)
        if should_stream:
            try:
                stream_iter = self._astream(messages=messages, stop=stop, run_manager=run_manager, **kwargs)
                return await agenerate_from_stream(stream_iter)
            except TypeError as e:
                if "'NoneType' object is not iterable" in str(e):
                    logger.warning(" LangChain agenerate_from_stream bug, falling back to non-streaming")
                    return await self._agenerate(messages, stop, run_manager, stream=False, **kwargs)
                raise
            except Exception:
                logger.error(f" LiteLLM streaming failed (Model: {self.model_name or self.model})")
                raise

        if (renewed := await renew_api_key(self.api_key or self.openai_api_key)) is not None:
            self.api_key = renewed
        available_tools, tool_schemas = self._extract_tool_context_from_kwargs(kwargs)
        message_dicts, params = self._create_message_dicts(messages, stop)

        # Filter out internal LangChain parameters that shouldn't be passed to LiteLLM
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in (
                "ls_structured_output_format",
                "_json_mode_fallback",
                "_in_fallback",
            )
        }

        params = {**params, **filtered_kwargs}
        self._inject_allowed_params(params)
        self._apply_output_budget(params)
        self._inject_prompt_routing_key(params)

        model_name = self.model_name or self.model
        call = ModelCall(
            model=model_name,
            provider=model_provider_name(model_name, str(self.api_base or "") or None, self.custom_llm_provider),
            stream=False,
            params=params,
            message_dicts=message_dicts,
        )
        try:
            return await self._agenerate_attempts(
                call, messages, message_dicts, params, available_tools, tool_schemas, model_name
            )
        except BaseException as exc:
            call.fail(exc)
            raise
        finally:
            call.close()

    async def _agenerate_attempts(
        self,
        call: ModelCall,
        messages: list[BaseMessage],
        message_dicts: list[dict[str, Any]],
        params: dict[str, Any],
        available_tools: list[str] | None,
        tool_schemas: dict[str, dict[str, Any]] | None,
        model_name: str,
    ) -> ChatResult:
        """Run the request, retrying empty responses and recoverable provider rejections."""
        from myrm_agent_harness.toolkits.llms.utils.logger import (
            log_llm_request,
            log_llm_response,
        )

        max_attempts = self.empty_retry_max_attempts if self.empty_retry_enabled else 1
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                started = time.perf_counter()
                log_llm_request(model_name, message_dicts, params)

                # Model-call memo: a repeated call with the same identity reads the recorded
                # answer back instead of paying for the model again. Inert without a scope.

                memo = memo_run(model_name, message_dicts, params)
                replayed = memo.replay
                memo_replayed = replayed is not None

                response: dict[str, Any]
                if replayed is not None:
                    response = replayed
                    logger.info(
                        " LLM memo hit: reusing the recorded answer for %s (no second charge).",
                        model_name,
                    )
                else:
                    memo.begin()
                    call.begin(attempt + 1)
                    wire_protocol = getattr(self, "wire_protocol", "chat_completions")
                    if wire_protocol == "responses":
                        response = await invoke_responses_async(self.client, message_dicts, params)
                    else:
                        call_params = (
                            apply_anthropic_messages_params(params) if wire_protocol == "anthropic_messages" else params
                        )
                        response = await self.client.acreate(messages=message_dicts, **call_params)
                        response = self._convert_response_to_dict(response)
                    memo.finish_payload(response)

                if not memo_replayed:
                    # A replayed answer was already logged and billed when it was first
                    # produced; counting it again would double-count the usage.
                    log_llm_response(response)

                result = self._create_chat_result(response, available_tools, tool_schemas)

                duration_ms = (time.perf_counter() - started) * 1000
                if not memo_replayed:
                    self._record_non_stream_usage(
                        response,
                        model_name=model_name,
                        duration_ms=duration_ms,
                    )
                    call.finish(response)

                # Update metrics: success after retry
                if attempt > 0:
                    self._retry_metrics.async_success_after_retry += 1

                return result

            except EmptyChoicesError as e:
                call.attempt_failed(e)
                last_error = e
                self._retry_metrics.async_retry_count += 1

                if attempt < max_attempts - 1:
                    logger.warning(f" Empty choices (attempt {attempt + 1}), retrying...")
                    delay_ms = self.empty_retry_delay * 1000
                    self._retry_metrics.total_retry_delay_ms += delay_ms
                    await asyncio.sleep(self.empty_retry_delay)
                else:
                    logger.error(f" Empty choices after {max_attempts} attempts.")
            except Exception as e:
                call.attempt_failed(e)
                memo.fail(e)

                if is_payload_overflow(e) and attempt < max_attempts - 1:
                    evicted = emergency_evict_from_message_dicts(
                        message_dicts, target_bytes=2 * 1024 * 1024, force_shrink=True
                    )
                    evicted_msgs = emergency_evict(messages, target_bytes=2 * 1024 * 1024, force_shrink=True)
                    if evicted > 0 or evicted_msgs > 0:
                        logger.warning(
                            f" Payload overflow 400/413 intercepted: evicted {max(evicted, evicted_msgs)} historical images, retrying (attempt {attempt + 1})"
                        )
                        continue

                if is_gateway_param_rejection(e) and attempt < max_attempts - 1:
                    stripped = sanitize_gateway_params_on_400(
                        params, e, model=self.model_name or self.model, base_url=str(self.api_base or "")
                    )
                    if stripped:
                        logger.warning(
                            f" Gateway rejected params {stripped}, retrying without them (attempt {attempt + 1})"
                        )
                        continue

                if attempt < max_attempts - 1 and self._recover_output_cap(e, params):
                    continue

                if is_context_overflow(e):
                    logger.warning(" Context overflow, fast-failing to trigger compression.")
                    raise e

                logger.error(f" LiteLLM acreate failed (Model: {self.model_name or self.model}): {e!s}")
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Unexpected error in _agenerate retry loop")
