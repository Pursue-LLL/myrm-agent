"""Stream Aggregation

[INPUT]
- adapters.streaming (POS: streaming response processing)
- adapters.tool_recovery (POS: Tool call recovery module)
- adapters.model_capability (POS: Model capability detection; xAI Grok tool-argument decoding gate)
- adapters.safety_termination_detector (POS: Safety termination detector for truncated tool call suppression)
- utils.token_economics.tracker::record_finish_reason (POS: Token tracking API)
- core.thinking_blocks (POS: the signed reasoning blocks an Anthropic-family answer carries)
- adapters.usage_estimate::estimate_stream_usage (POS: local token count for a stream the provider reported no usage for)
- utils.token_economics.usage_ledger::DROPPED_STREAM_FINISH_REASON (POS: finish_reason sentinel for streams closed without a final chunk)

[OUTPUT]
- StreamAggregator: Mutable accumulator for stream chunks (content, tool calls, reasoning, timing)
- finalize_stream(): Build aggregated response, record usage (counted locally when the provider sent none), yield final tool chunk
- attach_replay_state_to_final_chunk(): Export the reasoning state the next request replays (Responses blobs, signed thinking blocks) on the final stream chunk

[POS]
Stream data aggregation module. Eliminates duplication between sync _stream and async
_astream_inner by encapsulating shared chunk aggregation, timing, tool call recovery,
usage recording, and log construction into reusable components.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from langchain_core.messages import BaseMessage, BaseMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY, SignedThinkingBlock, coerce_thinking_blocks
from myrm_agent_harness.toolkits.llms.adapters.model_capability import ModelCapabilityDetector
from myrm_agent_harness.toolkits.llms.adapters.safety_termination_detector import (
    detect_safety_termination,
    suppress_tool_calls_for_safety,
)
from myrm_agent_harness.toolkits.llms.adapters.streaming import (
    aggregate_tool_call_chunk,
    build_tool_call_chunks,
    extract_chunk_metadata,
    normalize_usage,
    parse_tool_calls_from_reasoning,
    provider_reported_finish,
)
from myrm_agent_harness.toolkits.llms.adapters.tool_call_parsers import (
    clean_xml_tool_tags,
)
from myrm_agent_harness.toolkits.llms.adapters.tool_recovery import (
    build_final_tool_call_chunk,
    is_stream_complete,
)
from myrm_agent_harness.utils.token_economics.usage_ledger import (
    DROPPED_STREAM_FINISH_REASON,
)

logger = logging.getLogger(__name__)

_StreamT = TypeVar("_StreamT")

_capability_detector = ModelCapabilityDetector()


class StreamAggregator:
    """Mutable accumulator that collects stream chunks and produces an aggregated response."""

    __slots__ = (
        "_source",
        "chunk_count",
        "content",
        "default_chunk_class",
        "finish_reason",
        "first_token_time",
        "last_model",
        "last_usage",
        "prompt_messages",
        "reasoning",
        "responses_reasoning_items",
        "stream_start",
        "thinking_blocks",
        "tool_calls",
    )

    def __init__(
        self, default_chunk_class: type[BaseMessageChunk], prompt_messages: Sequence[BaseMessage] = ()
    ) -> None:
        self._source: object | None = None
        self.prompt_messages = prompt_messages
        self.content: list[str] = []
        self.tool_calls: list[dict[str, Any]] = []
        self.reasoning: list[str] = []
        self.responses_reasoning_items: list[dict[str, Any]] = []
        self.thinking_blocks: list[SignedThinkingBlock] = []
        self.last_model: str = ""
        self.finish_reason: str = ""
        self.last_usage: Any = None
        self.chunk_count: int = 0
        self.first_token_time: float | None = None
        self.stream_start: float = time.monotonic()
        self.default_chunk_class = default_chunk_class

    def track(self, stream: _StreamT) -> _StreamT:
        """Remember the provider stream being consumed (returned unchanged) so its end can be classified."""
        self._source = stream
        return stream

    @property
    def provider_finish(self) -> bool | None:
        """Whether the provider itself reported how the tracked stream ended (None when it cannot be told)."""
        return provider_reported_finish(self._source)

    def ingest_raw_chunk(self, chunk: Any) -> dict[str, Any] | None:
        """Extract metadata from a raw chunk and return its dict form (or None to skip)."""
        self.chunk_count += 1
        chunk_usage, chunk_model, chunk_fr = extract_chunk_metadata(chunk)
        if chunk_usage:
            self.last_usage = chunk_usage
        if chunk_model:
            self.last_model = chunk_model
        if chunk_fr:
            self.finish_reason = chunk_fr

        if isinstance(chunk, dict):
            return chunk
        try:
            return dict(chunk.model_dump())
        except Exception:
            return None

    def aggregate_tool_calls_from_dict(self, chunk_dict: dict[str, Any]) -> None:
        """Extract and aggregate tool call chunks from a chunk dict."""
        choices = chunk_dict.get("choices") or []
        if not choices:
            return
        raw_tool_calls = choices[0].get("delta", {}).get("tool_calls")
        for tc_chunk in build_tool_call_chunks(raw_tool_calls):
            aggregate_tool_call_chunk(tc_chunk, self.tool_calls)

    def on_generation_chunk(self, cg_chunk: ChatGenerationChunk, new_class: type[BaseMessageChunk]) -> None:
        """Update aggregator state after a ChatGenerationChunk is produced."""
        if self.first_token_time is None:
            self.first_token_time = time.monotonic()
        self.default_chunk_class = new_class

        if cg_chunk.message.content:
            self.content.append(str(cg_chunk.message.content))

        additional_kwargs = getattr(cg_chunk.message, "additional_kwargs", {})
        if additional_kwargs.get("reasoning_content"):
            self.reasoning.append(str(additional_kwargs["reasoning_content"]))
        replay_items = additional_kwargs.get("responses_reasoning_items")
        if isinstance(replay_items, list) and replay_items:
            self.responses_reasoning_items = list(replay_items)
        # The provider closes its reasoning blocks one by one, in the order the next request must replay them.
        self.thinking_blocks.extend(coerce_thinking_blocks(additional_kwargs.get(THINKING_BLOCKS_KEY)))

    @property
    def is_empty(self) -> bool:
        return self.chunk_count == 0 and self.last_usage is None and not self.finish_reason

    @property
    def duration_ms(self) -> float:
        return (time.monotonic() - self.stream_start) * 1000.0

    @property
    def ttft_ms(self) -> float | None:
        if self.first_token_time is None:
            return None
        return (self.first_token_time - self.stream_start) * 1000.0


class StreamFinalization:
    """Result of finalizing a stream: contains the final tool chunk and aggregated response."""

    __slots__ = ("aggregated_response", "final_tool_chunk")

    def __init__(
        self,
        final_tool_chunk: ChatGenerationChunk | None,
        aggregated_response: dict[str, Any],
    ) -> None:
        self.final_tool_chunk = final_tool_chunk
        self.aggregated_response = aggregated_response


def attach_replay_state_to_final_chunk(
    final_tool_chunk: ChatGenerationChunk | None,
    replay_state: Mapping[str, object],
) -> ChatGenerationChunk | None:
    """Ensure the reasoning state the next request must replay (Responses blobs, signed thinking blocks) reaches the
    merged AIMessage: it rides on the final chunk because the chunks that carried it are not yielded."""
    if not replay_state:
        return final_tool_chunk

    from langchain_core.messages import AIMessageChunk

    if final_tool_chunk is not None and isinstance(final_tool_chunk.message, AIMessageChunk):
        msg = final_tool_chunk.message
        additional_kwargs = {**(msg.additional_kwargs or {}), **replay_state}
        chunk_kwargs: dict[str, Any] = {
            "content": msg.content or "",
            "tool_call_chunks": list(msg.tool_call_chunks or []),
            "additional_kwargs": additional_kwargs,
        }
        if msg.chunk_position is not None:
            chunk_kwargs["chunk_position"] = msg.chunk_position
        return ChatGenerationChunk(message=AIMessageChunk(**chunk_kwargs))

    return ChatGenerationChunk(
        message=AIMessageChunk(
            content="",
            additional_kwargs=dict(replay_state),
        )
    )


def _reported_finish_reason(agg: StreamAggregator) -> str:
    """Finish reason as reported to usage, response and status telemetry.

    A stream that closed without ever delivering a final metadata chunk has an empty
    finish_reason; recorded verbatim it would be indistinguishable from a normal turn,
    so it is tagged with an explicit sentinel. Providers never emit this value.
    """
    return agg.finish_reason or DROPPED_STREAM_FINISH_REASON


def finalize_stream(
    agg: StreamAggregator,
    tool_schemas: Mapping[str, Mapping[str, Any]] | None,
    model_name: str,
    *,
    is_async: bool,
    record_usage_fn: Any,
    available_tools: list[str] | None = None,
) -> StreamFinalization:
    """Build aggregated response, record usage, and return finalization result.

    Args:
        agg: The stream aggregator with accumulated data
        tool_schemas: Tool schemas for recovery
        model_name: Resolved model name for attribution; also selects xAI Grok argument decoding
        is_async: Whether this is an async stream (affects reasoning parser)
        record_usage_fn: Callable to record token usage/cost/latency
        available_tools: Tool names for hallucination filtering in streaming mode
    """
    from myrm_agent_harness.toolkits.llms.utils.logger import log_llm_response

    aggregated_message: dict[str, Any] = {
        "content": "".join(agg.content),
        "role": "assistant",
    }
    valid_tool_calls = [tc for tc in agg.tool_calls if tc["function"]["name"]] if agg.tool_calls else []

    if available_tools and valid_tool_calls:
        before_count = len(valid_tool_calls)
        valid_tool_calls = [tc for tc in valid_tool_calls if tc.get("function", {}).get("name") in available_tools]
        dropped = before_count - len(valid_tool_calls)
        if dropped:
            logger.warning(
                " Stream: filtered %d hallucinated tool call(s) not in available_tools",
                dropped,
            )

    resolved_model = agg.last_model or model_name

    usage = agg.last_usage
    if not usage:
        # The provider ended the stream without a usage chunk: the call is still accounted, from a local count.
        from myrm_agent_harness.toolkits.llms.adapters.usage_estimate import estimate_stream_usage

        usage = estimate_stream_usage(
            agg.prompt_messages, text="".join([*agg.content, *agg.reasoning]), tool_calls=agg.tool_calls
        )
    record_usage_fn(
        usage,
        model_name=resolved_model,
        duration_ms=agg.duration_ms,
        ttft_ms=agg.ttft_ms,
        finish_reason=_reported_finish_reason(agg),
    )

    if agg.reasoning:
        aggregated_message["reasoning_content"] = "".join(agg.reasoning)

    if agg.responses_reasoning_items:
        aggregated_message["responses_reasoning_items"] = agg.responses_reasoning_items
    if agg.thinking_blocks:
        aggregated_message[THINKING_BLOCKS_KEY] = agg.thinking_blocks

    parsed_tool_calls, _ = parse_tool_calls_from_reasoning(agg.reasoning, valid_tool_calls, is_async=is_async)

    if not parsed_tool_calls and not valid_tool_calls:
        from myrm_agent_harness.toolkits.llms.adapters.tool_call_parsers import (
            parse_tool_calls,
        )

        parsed_tool_calls = parse_tool_calls(aggregated_message)
        if parsed_tool_calls:
            logger.warning(f" Stream: parsed {len(parsed_tool_calls)} tool calls from content/reasoning_content")

            if agg.finish_reason == "stop":
                agg.finish_reason = "tool_calls"
                logger.warning(
                    " Stream: overrode finish_reason from 'stop' to 'tool_calls' due to parsed DSML/Inline tags"
                )

    if aggregated_message.get("content"):
        aggregated_message["content"] = clean_xml_tool_tags(aggregated_message["content"])

    if aggregated_message.get("reasoning_content"):
        aggregated_message["reasoning_content"] = clean_xml_tool_tags(aggregated_message["reasoning_content"])

    tool_call_source = parsed_tool_calls if parsed_tool_calls else valid_tool_calls
    final_tool_chunk, corrected_tool_calls, recovery_metadata = build_final_tool_call_chunk(
        tool_call_source,
        tool_schemas,
        stream_complete=is_stream_complete(agg.finish_reason, agg.provider_finish),
        decode_html_entities=_capability_detector.is_xai_model(model_name),
    )
    if corrected_tool_calls:
        aggregated_message["tool_calls"] = corrected_tool_calls
    if recovery_metadata:
        aggregated_message["tool_call_recovery"] = [
            item
            for item in recovery_metadata
            if item["strategy"] != "standard_json" or item["degraded"] or not item["safe"]
        ]

    # Safety termination: suppress truncated tool_calls when provider stopped
    # generation for safety reasons, preventing corrupt half-formed arguments
    # from being dispatched. Withheld calls recorded by the truncation gate
    # (tool_call_recovery) are also covered, so the model is not asked to retry
    # a call that the provider deliberately cut off.
    safety_reason = agg.finish_reason if agg.finish_reason and detect_safety_termination(agg.finish_reason) else None
    if safety_reason and (aggregated_message.get("tool_calls") or aggregated_message.get("tool_call_recovery")):
        suppress_tool_calls_for_safety(aggregated_message, safety_reason)
        final_tool_chunk = None

    final_finish_reason = _reported_finish_reason(agg)
    aggregated_response: dict[str, Any] = {
        "model": resolved_model,
        "choices": [
            {
                "message": aggregated_message,
                "finish_reason": final_finish_reason,
            }
        ],
        "usage": normalize_usage(agg.last_usage) if agg.last_usage else {},
    }
    log_llm_response(aggregated_response)

    from myrm_agent_harness.utils.token_economics.tracker import (
        record_finish_reason,
    )

    record_finish_reason(final_finish_reason)

    replay_state: dict[str, object] = {
        key: aggregated_message[key]
        for key in ("responses_reasoning_items", THINKING_BLOCKS_KEY)
        if key in aggregated_message
    }
    final_tool_chunk = attach_replay_state_to_final_chunk(final_tool_chunk, replay_state)

    return StreamFinalization(
        final_tool_chunk=final_tool_chunk,
        aggregated_response=aggregated_response,
    )
