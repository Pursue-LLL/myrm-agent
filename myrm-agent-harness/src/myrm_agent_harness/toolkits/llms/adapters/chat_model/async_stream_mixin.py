"""ChatLiteLLM streaming mixin: one stream call with retry, stall detection and usage recording.

[INPUT]
- adapters.chat_model.exceptions (POS: EmptyStreamError / StreamStallTimeoutError)
- adapters.chat_model.api_key_refresher (POS: host-registered renewal of an expiring api key)
- adapters.chat_model.payload_debug (POS: opt-in failed-request payload diagnostics)
- adapters.chat_model.memo_wiring (POS: model-call memo replay and recording)
- adapters.concurrency (POS: per-model semaphores)
- adapters.stream_aggregator (POS: stream aggregation and finalization)
- infra.tracing.gen_ai::ModelCall (POS: one `chat` span and its metrics per logical model call)

[OUTPUT]
- ChatLiteLLMAsyncStreamMixin: _astream, _astream_inner (empty-stream retry, stall detection, api key renewal)

[POS]
Streaming half of the asynchronous LiteLLM adapter. One stream call is one `chat` span however many
attempts it takes; the span closes the moment the response is complete (not when the consumer has
drained the last chunk) and also when the consumer abandons the stream.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import aclosing
from typing import TYPE_CHECKING, Any

from langchain_core.messages import (
    AIMessageChunk,
    BaseMessage,
    BaseMessageChunk,
)
from langchain_core.outputs import ChatGenerationChunk

from myrm_agent_harness.infra.tracing.gen_ai import ModelCall
from myrm_agent_harness.toolkits.llms.adapters.chat_model.api_key_refresher import renew_api_key
from myrm_agent_harness.toolkits.llms.adapters.chat_model.exceptions import (
    EmptyStreamError,
    StreamStallTimeoutError,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model.memo_wiring import (
    memo_run,
    replay_memo_chunk,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model.model_provider import model_provider_name
from myrm_agent_harness.toolkits.llms.adapters.chat_model.payload_debug import dump_payload_pairing
from myrm_agent_harness.toolkits.llms.adapters.concurrency import (
    bounded_model_call,
)
from myrm_agent_harness.toolkits.llms.adapters.metrics import EmptyRetryMetrics
from myrm_agent_harness.toolkits.llms.adapters.stream_aggregator import (
    StreamAggregator,
    XmlStreamBuffer,
    finalize_stream,
)
from myrm_agent_harness.toolkits.llms.adapters.wire.anthropic_params import (
    apply_anthropic_messages_params,
)
from myrm_agent_harness.toolkits.llms.adapters.wire.invocation import (
    stream_responses_async,
)

logger = logging.getLogger(__name__)


class ChatLiteLLMAsyncStreamMixin:
    if TYPE_CHECKING:
        # Attributes and sibling-mixin methods defined on the ChatLiteLLM aggregate
        # root; declared here so mypy understands the composition-mixin pattern.
        api_base: str | None
        api_key: str | None
        openai_api_key: str | None
        client: Any
        model: str
        model_name: str | None
        custom_llm_provider: str | None
        empty_retry_enabled: bool
        empty_retry_max_attempts: int
        empty_retry_delay: float
        first_event_timeout: float
        inter_chunk_timeout: float
        _retry_metrics: EmptyRetryMetrics
        _extract_tool_context_from_kwargs: Callable[..., tuple[list[str] | None, dict[str, dict[str, Any]] | None]]
        _create_message_dicts: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]]
        _inject_allowed_params: Callable[..., None]
        _apply_output_budget: Callable[..., None]
        _recover_output_cap: Callable[..., bool]
        _inject_prompt_routing_key: Callable[..., None]
        _process_chunk: Callable[..., tuple[ChatGenerationChunk | None, type[BaseMessageChunk]]]
        _record_usage: Callable[..., None]

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        # aclosing: a consumer that stops early closes the attempt (span, semaphore) now,
        # not whenever the abandoned inner generator is garbage collected.
        async with (
            bounded_model_call(self.model_name or self.model),
            aclosing(self._astream_inner(messages, stop, run_manager, **kwargs)) as chunks,
        ):
            async for chunk in chunks:
                yield chunk

    async def _astream_inner(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ChatGenerationChunk]:
        model_name = self.model_name or self.model

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

        params = {
            **params,
            **filtered_kwargs,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        self._inject_allowed_params(params)
        self._apply_output_budget(params)
        self._inject_prompt_routing_key(params)

        call = ModelCall(
            model=model_name,
            provider=model_provider_name(model_name, str(self.api_base or "") or None, self.custom_llm_provider),
            stream=True,
            params=params,
            message_dicts=message_dicts,
        )
        try:
            max_attempts = self.empty_retry_max_attempts if self.empty_retry_enabled else 1
            last_error: Exception | None = None

            for attempt in range(max_attempts):
                agg: StreamAggregator | None = None
                try:
                    # Model-call memo: a repeated call with the same identity replays the
                    # recorded answer instead of paying for the model again. Inert without a scope.

                    memo = memo_run(model_name, message_dicts, params)
                    if memo.replay is not None:
                        replayed = replay_memo_chunk(memo.replay)
                        if replayed is not None:
                            logger.info(
                                " LLM memo hit: replaying the recorded answer for %s (no second charge).",
                                model_name,
                            )
                            yield replayed
                            # The sentinel keeps LangGraph's messages stream dispatching, exactly
                            # as the normal path does when the stream carries no final tool chunk.
                            yield ChatGenerationChunk(message=AIMessageChunk(content=""))
                            return
                    memo.begin()
                    call.begin(attempt + 1)
                    wire_protocol = getattr(self, "wire_protocol", "chat_completions")
                    if wire_protocol == "responses":
                        stream = stream_responses_async(self.client, message_dicts, params)
                    else:
                        call_params = (
                            apply_anthropic_messages_params(params) if wire_protocol == "anthropic_messages" else params
                        )
                        stream = await self.client.acreate(messages=message_dicts, **call_params)

                    agg = StreamAggregator(AIMessageChunk)
                    xml_content_buffer = XmlStreamBuffer()
                    xml_reasoning_buffer = XmlStreamBuffer()

                    stall_phase = "first_event"
                    try:
                        loop = asyncio.get_running_loop()
                        async with asyncio.timeout(self.first_event_timeout) as stall_tm:
                            async for chunk in agg.track(stream):
                                stall_tm.reschedule(loop.time() + self.inter_chunk_timeout)
                                if stall_phase == "first_event":
                                    stall_phase = "inter_chunk"

                                chunk_dict = agg.ingest_raw_chunk(chunk)
                                if chunk_dict is None:
                                    continue
                                agg.aggregate_tool_calls_from_dict(chunk_dict)

                                cg_chunk, new_class = self._process_chunk(
                                    chunk_dict,
                                    agg.default_chunk_class,
                                    emit_tool_call_chunks=False,
                                )
                                if cg_chunk:
                                    agg.on_generation_chunk(cg_chunk, new_class)

                                    # Filter content and reasoning_content through DSML buffer before yielding
                                    raw_content = str(cg_chunk.message.content) if cg_chunk.message.content else ""
                                    safe_content = xml_content_buffer.process(raw_content)

                                    additional_kwargs = dict(getattr(cg_chunk.message, "additional_kwargs", {}))
                                    raw_reasoning = additional_kwargs.get("reasoning_content", "")
                                    safe_reasoning = (
                                        xml_reasoning_buffer.process(str(raw_reasoning)) if raw_reasoning else ""
                                    )

                                    if (
                                        safe_content
                                        or safe_reasoning
                                        or getattr(cg_chunk.message, "tool_call_chunks", [])
                                    ):
                                        msg_dict = dict(cg_chunk.message)
                                        msg_dict.pop("type", None)
                                        msg_dict["content"] = safe_content
                                        if "additional_kwargs" in msg_dict:
                                            ak = dict(msg_dict["additional_kwargs"])
                                            if safe_reasoning:
                                                ak["reasoning_content"] = safe_reasoning
                                            elif "reasoning_content" in ak:
                                                del ak["reasoning_content"]
                                            msg_dict["additional_kwargs"] = ak

                                        safe_chunk = cg_chunk.message.__class__(**msg_dict)
                                        safe_cg_chunk = ChatGenerationChunk(message=safe_chunk)
                                        if run_manager:
                                            await run_manager.on_llm_new_token(safe_content, chunk=safe_cg_chunk)
                                        yield safe_cg_chunk
                    except TimeoutError as exc:
                        timeout_val = (
                            self.first_event_timeout if stall_phase == "first_event" else self.inter_chunk_timeout
                        )
                        logger.warning(
                            " Stream stall detected (phase=%s, model=%s, timeout=%.0fs)",
                            stall_phase,
                            model_name,
                            timeout_val,
                        )
                        raise StreamStallTimeoutError(
                            provider=self.custom_llm_provider or "unknown",
                            model=model_name,
                            phase=stall_phase,
                            elapsed_s=timeout_val,
                        ) from exc

                    logger.debug(f" Stream completed: total {agg.chunk_count} chunks")

                    if agg.is_empty:
                        raise EmptyStreamError(f"Stream produced no chunks. Model: {model_name}")

                    # Flush buffers at the end of the stream
                    flushed_content = xml_content_buffer.flush()
                    flushed_reasoning = xml_reasoning_buffer.flush()
                    if flushed_content or flushed_reasoning:
                        msg_dict = {"content": flushed_content}
                        if flushed_reasoning:
                            msg_dict["additional_kwargs"] = {"reasoning_content": flushed_reasoning}
                        safe_chunk = agg.default_chunk_class(**msg_dict)
                        safe_cg_chunk = ChatGenerationChunk(message=safe_chunk)
                        if run_manager:
                            await run_manager.on_llm_new_token(flushed_content, chunk=safe_cg_chunk)
                        yield safe_cg_chunk

                    result = finalize_stream(
                        agg,
                        tool_schemas,
                        model_name,
                        is_async=True,
                        record_usage_fn=self._record_usage,
                        available_tools=available_tools,
                    )
                    memo.finish(result)
                    call.finish(
                        result.aggregated_response,
                        time_to_first_chunk_s=agg.ttft_ms / 1000.0 if agg.ttft_ms is not None else None,
                    )
                    call.close()
                    if result.final_tool_chunk:
                        if run_manager:
                            await run_manager.on_llm_new_token("", chunk=result.final_tool_chunk)
                        yield result.final_tool_chunk
                    else:
                        # Yield an empty chunk so LangGraph's messages stream triggers
                        # one more dispatch cycle, allowing get_pending_token_events()
                        # to capture the usage recorded by finalize_stream above.
                        sentinel = ChatGenerationChunk(message=AIMessageChunk(content=""))
                        yield sentinel

                    if attempt > 0:
                        self._retry_metrics.stream_success_after_retry += 1
                    # Success path: clear a stale retry error so the loop-exit raise
                    # below only fires when every attempt failed.
                    last_error = None
                    break

                except EmptyStreamError as e:
                    call.attempt_failed(e)
                    last_error = e
                    self._retry_metrics.stream_retry_count += 1
                    if attempt < max_attempts - 1:
                        logger.warning(f" Empty stream (attempt {attempt + 1}), retrying...")
                        self._retry_metrics.total_retry_delay_ms += self.empty_retry_delay * 1000
                        await asyncio.sleep(self.empty_retry_delay)
                    else:
                        logger.error(f" Empty stream after {max_attempts} attempts.")
                except StreamStallTimeoutError:
                    raise
                except Exception as e:
                    call.attempt_failed(e)
                    from myrm_agent_harness.toolkits.llms.adapters.gateway_normalizer import (
                        is_gateway_param_rejection,
                        sanitize_gateway_params_on_400,
                    )
                    from myrm_agent_harness.toolkits.llms.errors.classifier import (
                        is_context_overflow,
                        is_payload_overflow,
                    )

                    # A retry restarts the stream, so it is only safe while the consumer has received nothing yet.
                    can_retry = attempt < max_attempts - 1 and (agg is None or agg.chunk_count == 0)

                    if can_retry and is_gateway_param_rejection(e):
                        stripped = sanitize_gateway_params_on_400(
                            params, e, model=self.model_name or self.model, base_url=str(self.api_base or "")
                        )
                        if stripped:
                            logger.warning(
                                f" Gateway streaming rejected params {stripped}, retrying without them (attempt {attempt + 1})"
                            )
                            continue

                    from myrm_agent_harness.toolkits.llms.adapters.image_payload_evictor import (
                        emergency_evict,
                        emergency_evict_from_message_dicts,
                    )

                    if can_retry and is_payload_overflow(e):
                        evicted = emergency_evict_from_message_dicts(
                            message_dicts, target_bytes=4 * 1024 * 1024, force_shrink=True
                        )
                        evicted_msgs = emergency_evict(messages, target_bytes=4 * 1024 * 1024, force_shrink=True)
                        if evicted > 0 or evicted_msgs > 0:
                            logger.warning(
                                f" Streaming payload overflow 400/413 intercepted: evicted {evicted} historical images, retrying (attempt {attempt + 1})"
                            )
                            continue

                    if can_retry and self._recover_output_cap(e, params):
                        continue

                    if is_context_overflow(e):
                        logger.warning(" Context overflow, fast-failing to trigger compression.")
                        raise e

                    logger.error(f" LiteLLM streaming failed (Model: {model_name}): {e!s}")
                    if os.environ.get("MYRM_DEBUG_DUMP_LLM_PAYLOAD", "") == "1":
                        dump_payload_pairing(message_dicts)
                    raise

            if last_error:
                raise last_error
        except BaseException as exc:
            call.fail(exc)
            raise
        finally:
            call.close()
