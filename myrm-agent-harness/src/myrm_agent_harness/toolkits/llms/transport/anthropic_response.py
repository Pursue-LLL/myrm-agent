"""Anthropic Messages wire: ``/v1/messages`` answers and event streams as chat.completion objects.

[INPUT]
- core.thinking_blocks (POS: ThinkingBlockAssembler — builds the signed reasoning blocks of a stream)
- transport.profile (POS: Route — provider id and bare model)
- transport.http (POS: Chunk, StreamDecoder)
- transport.errors (POS: LLMAnswerError for an error inside a 200 answer or stream)
- transport.chat_shape (POS: answered_without, the failure of a 200 answer that holds no message)
- transport.frames (POS: the JSON payload of a stream frame)

[OUTPUT]
- parse: a Messages answer as a chat.completion dict (content, reasoning, signed thinking_blocks, tool_calls, usage with
  cache accounting)
- decoder: the SSE decoder yielding chat.completion.chunk dicts; each signed reasoning block is delivered whole, as one
  ``thinking_blocks`` delta, when the provider closes it

[POS]
Response half of the Anthropic wire (the request half is ``anthropic_messages``). The answer is returned in the
chat.completion shape the adapter already consumes, with Anthropic's cache counters folded into the prompt-token
total the way every other provider reports it. A finish chunk is emitted only when the provider reported a stop
reason, so an interrupted stream is never mistaken for a complete one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY, ThinkingBlockAssembler
from myrm_agent_harness.toolkits.llms.transport.chat_shape import answered_without
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.frames import json_frame
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.profile import Route

_STOP_REASON: Final = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "pause_turn": "stop",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "tool_use": "tool_calls",
    "refusal": "content_filter",
}
Block = dict[str, object]


def _usage(raw: Mapping[str, object]) -> dict[str, object]:
    """Anthropic counts cache reads/writes beside ``input_tokens``; providers elsewhere fold them into the prompt."""

    def count(key: str) -> int:
        value = raw.get(key)
        return value if isinstance(value, int) else 0

    fresh, written, read, output = (
        count("input_tokens"),
        count("cache_creation_input_tokens"),
        count("cache_read_input_tokens"),
        count("output_tokens"),
    )
    prompt = fresh + written + read
    return {
        "prompt_tokens": prompt,
        "completion_tokens": output,
        "total_tokens": prompt + output,
        "prompt_tokens_details": {"cached_tokens": read},
        "cache_creation_input_tokens": written,
        "cache_read_input_tokens": read,
    }


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    if payload.get("type") == "error":
        raise LLMAnswerError(route.profile.id, payload)
    content = payload.get("content")
    if not isinstance(content, list):
        raise answered_without(route.profile.id, "a message", payload)
    texts: list[str] = []
    reasoning: list[str] = []
    thinking_blocks: list[Block] = []
    tool_calls: list[Block] = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        kind = block.get("type")
        if kind == "text":
            texts.append(str(block.get("text") or ""))
        elif kind == "thinking":
            reasoning.append(str(block.get("thinking") or ""))
            thinking_blocks.append(dict(block))
        elif kind == "redacted_thinking":
            thinking_blocks.append(dict(block))
        elif kind == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    },
                }
            )
    message: dict[str, object] = {"role": "assistant", "content": "".join(texts) or None}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    if thinking_blocks:
        message["thinking_blocks"] = thinking_blocks
    if tool_calls:
        message["tool_calls"] = tool_calls
    reason = payload.get("stop_reason")
    usage = payload.get("usage")
    return {
        "id": payload.get("id"),
        "object": "chat.completion",
        "model": payload.get("model") or route.model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": _STOP_REASON.get(str(reason), "stop") if reason else None,
            }
        ],
        "usage": _usage(usage) if isinstance(usage, Mapping) else {},
    }


# --- stream ----------------------------------------------------------------------------------------------------


class AnthropicStreamDecoder:
    """Maps Messages stream events onto chat.completion.chunk dicts; the caller's tool blocks get running 0-based indexes.

    A server tool (the native web search) runs on the provider's side, so its blocks produce no tool call: the
    answer text that follows is all the caller sees.
    """

    __slots__ = ("_id", "_model", "_provider", "_stop", "_thinking", "_tool_index", "_tool_of_block", "_usage", "done")

    def __init__(self, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._id: object = None
        self._tool_of_block: dict[int, int] = {}
        self._tool_index = -1
        self._thinking = ThinkingBlockAssembler()
        self._stop: str | None = None
        self._usage: dict[str, int] = {}
        self.done = False

    def _chunk(
        self, delta: dict[str, object], finish: str | None = None, usage: dict[str, object] | None = None
    ) -> Chunk:
        chunk: Chunk = {
            "id": self._id,
            "object": "chat.completion.chunk",
            "model": self._model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        if usage is not None:
            chunk["usage"] = usage
        return chunk

    def _merge_usage(self, raw: object) -> None:
        if isinstance(raw, Mapping):
            self._usage.update({k: v for k, v in raw.items() if isinstance(v, int)})

    def _block_start(self, index: int, block: Mapping[str, object]) -> list[Chunk]:
        kind = block.get("type")
        if kind == "tool_use":
            self._tool_index += 1
            self._tool_of_block[index] = self._tool_index
            call = {
                "index": self._tool_index,
                "id": block.get("id"),
                "type": "function",
                "function": {"name": block.get("name"), "arguments": ""},
            }
            return [self._chunk({"tool_calls": [call]})]
        if kind == "thinking":
            self._thinking.add_text(index, str(block.get("thinking") or ""))
        elif kind == "redacted_thinking":
            self._thinking.set_redacted(index, str(block.get("data") or ""))
        return []

    def _block_delta(self, index: int, delta: Mapping[str, object]) -> list[Chunk]:
        delta_type = delta.get("type")
        if delta_type == "text_delta":
            return [self._chunk({"content": delta.get("text") or ""})]
        if delta_type == "thinking_delta":
            text = str(delta.get("thinking") or "")
            self._thinking.add_text(index, text)
            return [self._chunk({"reasoning_content": text})]
        if delta_type == "signature_delta":
            self._thinking.add_signature(index, str(delta.get("signature") or ""))
        elif delta_type == "input_json_delta" and index in self._tool_of_block:
            call = {"index": self._tool_of_block[index], "function": {"arguments": delta.get("partial_json") or ""}}
            return [self._chunk({"tool_calls": [call]})]
        return []

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        payload = json_frame(self._provider, data)
        if payload is None:
            return []
        kind = payload.get("type") or event
        if kind == "error":
            raise LLMAnswerError(self._provider, payload, stream=True)
        if kind == "message_start":
            message = payload.get("message")
            if isinstance(message, Mapping):
                self._id = message.get("id")
                self._model = str(message.get("model") or self._model)
                self._merge_usage(message.get("usage"))
            return [self._chunk({"role": "assistant", "content": ""})]
        raw_index = payload.get("index")
        index = raw_index if isinstance(raw_index, int) else 0
        if kind == "content_block_start":
            block = payload.get("content_block")
            return self._block_start(index, block) if isinstance(block, Mapping) else []
        if kind == "content_block_delta":
            delta = payload.get("delta")
            return self._block_delta(index, delta) if isinstance(delta, Mapping) else []
        if kind == "content_block_stop":
            # A reasoning block is whole only now: its signature arrives last, so a cut stream never yields half a block.
            finished = self._thinking.close(index)
            return [self._chunk({THINKING_BLOCKS_KEY: [finished]})] if finished else []
        if kind == "message_delta":
            delta = payload.get("delta")
            if isinstance(delta, Mapping) and delta.get("stop_reason"):
                self._stop = str(delta["stop_reason"])
            self._merge_usage(payload.get("usage"))
            return []
        if kind == "message_stop":
            self.done = True
        return []

    def finish(self) -> list[Chunk]:
        if self._stop is None:
            return []  # the provider never said how the answer ended: no finish chunk is invented
        return [self._chunk({}, _STOP_REASON.get(self._stop, "stop"), _usage(self._usage))]


def decoder(route: Route) -> StreamDecoder:
    return AnthropicStreamDecoder(route.profile.id, route.model)
