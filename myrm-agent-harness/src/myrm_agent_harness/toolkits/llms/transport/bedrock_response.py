"""Bedrock Converse wire: ``converse`` answers and ``converse-stream`` event streams as chat.completion objects.

[INPUT]
- core.thinking_blocks (POS: ThinkingBlockAssembler — builds the signed reasoning blocks of a stream)
- transport.profile (POS: Route — provider id and bare model)
- transport.http (POS: Chunk, StreamDecoder)
- transport.errors (POS: LLMAnswerError for an exception of an open stream)
- transport.frames (POS: the JSON payload of a stream event)
- transport.chat_shape (POS: FINISH_REASONS, the finish words providers use; answered_without, the failure of an answer with no message)
- transport.bedrock_content (POS: decode_tool_name)
- transport.bedrock_structured (POS: JSON_TOOL, the synthetic tool of a structured answer)

[OUTPUT]
- parse: a Converse answer as a chat.completion dict (content, reasoning, signed thinking_blocks, tool_calls, usage with
  cache accounting)
- decoder: the event-stream decoder yielding chat.completion.chunk dicts; each signed reasoning block is delivered
  whole, as one ``thinking_blocks`` delta, when the provider closes it

[POS]
Response half of the Bedrock wire (the request half is ``bedrock_converse``). The answer is returned in the
chat.completion shape the adapter already consumes, with Bedrock's cache counters folded into the prompt-token total the
way every other provider reports it. The call of the synthetic JSON tool is the structured answer: it becomes the text
of the message. A finish chunk is emitted only when the provider reported a stop reason, so an interrupted stream is
never mistaken for a complete one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY, ThinkingBlockAssembler
from myrm_agent_harness.toolkits.llms.transport.bedrock_content import Block, decode_tool_name
from myrm_agent_harness.toolkits.llms.transport.bedrock_structured import JSON_TOOL
from myrm_agent_harness.toolkits.llms.transport.chat_shape import FINISH_REASONS, answered_without
from myrm_agent_harness.toolkits.llms.transport.errors import LLMAnswerError
from myrm_agent_harness.toolkits.llms.transport.frames import json_frame
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.profile import Route

# The HTTP status an exception of an open stream stands for (the stream itself already answered 200).
_EXCEPTION_STATUS: Final = {
    "validationException": 400,
    "accessDeniedException": 403,
    "resourceNotFoundException": 404,
    "modelTimeoutException": 408,
    "modelStreamErrorException": 424,
    "modelErrorException": 424,
    "throttlingException": 429,
    "modelNotReadyException": 429,
    "internalServerException": 500,
    "serviceUnavailableException": 503,
}


def _count(raw: Mapping[str, object], key: str) -> int:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _usage(raw: Mapping[str, object]) -> dict[str, object]:
    """Bedrock counts cache reads and writes beside ``inputTokens``; providers elsewhere fold them into the prompt."""
    read, written = _count(raw, "cacheReadInputTokens"), _count(raw, "cacheWriteInputTokens")
    prompt = _count(raw, "inputTokens") + read + written
    output = _count(raw, "outputTokens")
    return {
        "prompt_tokens": prompt,
        "completion_tokens": output,
        "total_tokens": _count(raw, "totalTokens") or prompt + output,
        "prompt_tokens_details": {"cached_tokens": read},
        "cache_creation_input_tokens": written,
        "cache_read_input_tokens": read,
    }


def _structured_text(arguments: str) -> str:
    """The arguments of the JSON tool as text; a lone ``properties`` wrapper, which models sometimes add, is removed."""
    try:
        data = json.loads(arguments)
    except ValueError:
        return arguments
    if isinstance(data, dict) and len(data) == 1 and "properties" in data:
        return json.dumps(data["properties"], ensure_ascii=False)
    return arguments


def _finish(reason: object, *, tools_called: bool) -> str:
    finish = FINISH_REASONS.get(reason, "stop") if isinstance(reason, str) else "stop"
    # The call of the JSON tool ended the turn but is no tool call to the caller.
    return "stop" if finish == "tool_calls" and not tools_called else finish


def _answer_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex}"


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    output = payload.get("output")
    message = output.get("message") if isinstance(output, Mapping) else None
    blocks = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(blocks, list):
        raise answered_without(route.profile.id, "a message", payload)
    texts: list[str] = []
    structured: list[str] = []
    reasoning: list[str] = []
    thinking_blocks: list[Block] = []
    tool_calls: list[Block] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        if isinstance(block.get("text"), str):
            texts.append(block["text"])
        elif isinstance(use := block.get("toolUse"), Mapping):
            name = decode_tool_name(str(use.get("name") or ""))
            arguments = json.dumps(use.get("input") or {}, ensure_ascii=False)
            if name == JSON_TOOL:
                structured.append(_structured_text(arguments))
                continue
            tool_calls.append(
                {"id": use.get("toolUseId"), "type": "function", "function": {"name": name, "arguments": arguments}}
            )
        elif isinstance(thought := block.get("reasoningContent"), Mapping):
            if isinstance(text := thought.get("reasoningText"), Mapping):
                reasoning.append(str(text.get("text") or ""))
                signature = {"signature": text["signature"]} if text.get("signature") else {}
                thinking_blocks.append({"type": "thinking", "thinking": text.get("text") or "", **signature})
            elif thought.get("redactedContent"):
                thinking_blocks.append({"type": "redacted_thinking", "data": thought["redactedContent"]})
    # Structured output is the whole answer: text the model wrote around the tool call stays in front of it.
    content = "".join(texts + structured) or None
    reply: dict[str, object] = {"role": "assistant", "content": content}
    if reasoning:
        reply["reasoning_content"] = "".join(reasoning)
    if thinking_blocks:
        reply["thinking_blocks"] = thinking_blocks
    if tool_calls:
        reply["tool_calls"] = tool_calls
    stop, usage = payload.get("stopReason"), payload.get("usage")
    return {
        "id": _answer_id(),
        "object": "chat.completion",
        "model": route.model,
        "choices": [
            {
                "index": 0,
                "message": reply,
                "finish_reason": _finish(stop, tools_called=bool(tool_calls)) if stop else None,
            }
        ],
        "usage": _usage(usage) if isinstance(usage, Mapping) else {},
    }


# --- stream ----------------------------------------------------------------------------------------------------


class BedrockStreamDecoder:
    """Maps ConverseStream events onto chat.completion.chunk dicts; the caller's tool blocks get running 0-based indexes.

    The synthetic JSON tool is buffered until its block ends and then emitted as text, because the one wrapper that
    has to be removed from a structured answer cannot be recognised before the answer is whole.
    """

    __slots__ = (
        "_args_seen",
        "_id",
        "_json",
        "_model",
        "_provider",
        "_stop",
        "_thinking",
        "_tool_index",
        "_tool_of_block",
        "_usage",
        "done",
    )

    def __init__(self, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._id = _answer_id()
        self._thinking = ThinkingBlockAssembler()
        self._json: dict[int, list[str]] = {}
        self._tool_of_block: dict[int, int] = {}
        self._args_seen: set[int] = set()
        self._tool_index = -1
        self._stop: object = None
        self._usage: Mapping[str, object] = {}
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

    def _failure(self, kind: str, name: str, data: str) -> LLMAnswerError:
        """The failure an exception or error message of the stream reports; its payload is JSON or plain text."""
        try:
            payload = json.loads(data)
        except ValueError:
            payload = None
        message = payload.get("message") if isinstance(payload, dict) else None
        error: dict[str, object] = {"type": name or kind, "message": message or data}
        if status := _EXCEPTION_STATUS.get(name):
            error["code"] = status
        return LLMAnswerError(self._provider, {"error": error}, stream=True)

    def _start(self, index: int, start: object) -> list[Chunk]:
        use = start.get("toolUse") if isinstance(start, Mapping) else None
        if not isinstance(use, Mapping):
            return []
        name = decode_tool_name(str(use.get("name") or ""))
        if name == JSON_TOOL:
            self._json[index] = []
            return []
        self._tool_index += 1
        self._tool_of_block[index] = self._tool_index
        call = {
            "index": self._tool_index,
            "id": use.get("toolUseId"),
            "type": "function",
            "function": {"name": name, "arguments": ""},
        }
        return [self._chunk({"tool_calls": [call]})]

    def _delta(self, index: int, delta: object) -> list[Chunk]:
        if not isinstance(delta, Mapping):
            return []
        if isinstance(text := delta.get("text"), str):
            return [self._chunk({"content": text})]
        use = delta.get("toolUse")
        if isinstance(use, Mapping):
            part = use.get("input")
            part = part if isinstance(part, str) else ""
            if index in self._json:
                self._json[index].append(part)
            elif index in self._tool_of_block and part:
                self._args_seen.add(index)
                call = {"index": self._tool_of_block[index], "function": {"arguments": part}}
                return [self._chunk({"tool_calls": [call]})]
            return []
        thought = delta.get("reasoningContent")
        return self._thought(index, thought) if isinstance(thought, Mapping) else []

    def _thought(self, index: int, thought: Mapping[str, object]) -> list[Chunk]:
        """Reasoning has no block-start event: its text, signature or redacted data arrives as deltas of its index."""
        if isinstance(redacted := thought.get("redactedContent"), str):
            self._thinking.set_redacted(index, redacted)
        if isinstance(signature := thought.get("signature"), str):
            self._thinking.add_signature(index, signature)
        if isinstance(text := thought.get("text"), str):
            self._thinking.add_text(index, text)
            return [self._chunk({"reasoning_content": text})]
        return []

    def _stop_block(self, index: int) -> list[Chunk]:
        if (finished := self._thinking.close(index)) is not None:
            return [self._chunk({THINKING_BLOCKS_KEY: [finished]})]
        if index in self._json:
            text = "".join(self._json.pop(index))
            return [self._chunk({"content": _structured_text(text)})] if text else []
        if index in self._tool_of_block and index not in self._args_seen:
            # A tool that takes no arguments streams none; the caller still needs an object to parse.
            call = {"index": self._tool_of_block[index], "function": {"arguments": "{}"}}
            return [self._chunk({"tool_calls": [call]})]
        return []

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        kind, _, name = (event or "").partition(":")
        if kind in ("exception", "error"):
            raise self._failure(kind, name, data)
        payload = json_frame(self._provider, data)
        if payload is None:
            return []
        raw_index = payload.get("contentBlockIndex")
        index = raw_index if isinstance(raw_index, int) else 0
        if event == "messageStart":
            return [self._chunk({"role": "assistant", "content": ""})]
        if event == "contentBlockStart":
            return self._start(index, payload.get("start"))
        if event == "contentBlockDelta":
            return self._delta(index, payload.get("delta"))
        if event == "contentBlockStop":
            return self._stop_block(index)
        if event == "messageStop":
            self._stop = payload.get("stopReason")
        elif event == "metadata":
            usage = payload.get("usage")
            self._usage = usage if isinstance(usage, Mapping) else {}
            self.done = True
        return []

    def finish(self) -> list[Chunk]:
        if self._stop is None:
            return []  # the provider never said how the answer ended: no finish chunk is invented
        finish = _finish(self._stop, tools_called=self._tool_index >= 0)
        return [self._chunk({}, finish, _usage(self._usage))]


def decoder(route: Route) -> StreamDecoder:
    return BedrockStreamDecoder(route.profile.id, route.model)
