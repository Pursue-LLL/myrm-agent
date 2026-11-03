"""The chat.completion shape every chat wire hands the adapter.

[INPUT]
- transport.errors (POS: LLMResponseError for a choice without a message)
- transport.http (POS: Chunk and StreamDecoder)
- utils.coercion (POS: parse_int for token counts a provider sends as text or null)

[OUTPUT]
- FINISH_REASONS: the finish words providers use, mapped onto OpenAI's
- shape_usage: ``usage`` with every token count an int
- shape_completion: a non-streaming answer in the shape the adapter reads
- shape_chunk / ShapedDecoder: the same for the chunks of a stream

[POS]
The adapter reads provider answers as plain dicts and assumes OpenAI's shapes: token counts that are ints, a role, a
finish reason from OpenAI's five. Gateways routinely break those assumptions (``usage: null``, counts as text, no role,
``end_turn`` or ``SAFETY`` as the finish reason, ``choices: null`` on a usage-only chunk) and the OpenAI wire passes
provider JSON through. One pass at the facade gives the adapter the shape it assumes whatever the wire or the gateway
sent, so no consumer needs a defence of its own.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.errors import LLMResponseError
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, StreamDecoder
from myrm_agent_harness.utils.coercion import parse_int

_EXCERPT_LIMIT: Final = 300
_COUNTS: Final = ("prompt_tokens", "completion_tokens", "total_tokens")
_DETAILS: Final = ("prompt_tokens_details", "completion_tokens_details")
_NOT_A_COUNT: Final = -1

# A word that is not listed is a normal end of the answer, which is what every provider that invents one means.
_STOP: Final = "stop"
FINISH_REASONS: Final[Mapping[str, str]] = {
    **dict.fromkeys(("stop", "STOP", "end_turn", "stop_sequence", "eos", "eos_token", "COMPLETE"), _STOP),
    **dict.fromkeys(("length", "max_tokens", "MAX_TOKENS", "compaction", "model_context_window_exceeded"), "length"),
    **dict.fromkeys(("tool_calls", "tool_use"), "tool_calls"),
    **dict.fromkeys(
        (
            "content_filter",
            "content_filtered",
            "SAFETY",
            "RECITATION",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
            "IMAGE_SAFETY",
            "IMAGE_PROHIBITED_CONTENT",
            "LANGUAGE",
            "OTHER",
            "ERROR_TOXIC",
            "guardrail_intervened",
            "refusal",
            "sensitive",
        ),
        "content_filter",
    ),
    "function_call": "function_call",
}


def _count(value: object) -> int | None:
    count = parse_int(value, _NOT_A_COUNT, min_val=0)
    return None if count == _NOT_A_COUNT else count


def shape_usage(raw: object) -> dict[str, object]:
    """``usage`` with every token count an int; a value that is not a count (null, text) is left out."""
    if not isinstance(raw, Mapping):
        return {}
    usage = {key: value for key, value in raw.items() if key not in _COUNTS and key not in _DETAILS}
    counts = {key: count for key in _COUNTS if (count := _count(raw.get(key))) is not None}
    usage.update(counts)
    for key in _DETAILS:
        details = raw.get(key)
        if isinstance(details, Mapping):
            usage[key] = {name: count for name, value in details.items() if (count := _count(value)) is not None}
    if counts and "total_tokens" not in counts:
        usage["total_tokens"] = counts.get("prompt_tokens", 0) + counts.get("completion_tokens", 0)
    return usage


def _finish(reason: object) -> str:
    return FINISH_REASONS.get(reason, _STOP) if isinstance(reason, str) else _STOP


def _index(choice: Mapping[str, object], position: int) -> int:
    index = choice.get("index")
    return index if isinstance(index, int) else position


def _text_of(parts: list[object]) -> str:
    """The text of a content given as typed parts, which some gateways answer with."""
    return "".join(
        str(part["text"]) for part in parts if isinstance(part, Mapping) and isinstance(part.get("text"), str)
    )


def _shape_choice(provider: str, choice: Mapping[str, object], position: int) -> dict[str, object]:
    message = choice.get("message")
    if not isinstance(message, Mapping):
        raise LLMResponseError(provider, f"{provider} answered with a choice that has no message")
    shaped = {key: value for key, value in message.items() if key != "tool_calls" or value is not None}
    if not shaped.get("role"):
        shaped["role"] = "assistant"
    content = shaped.get("content")
    if isinstance(content, list):
        shaped["content"] = _text_of(content)
    finish = _finish(choice.get("finish_reason"))
    if finish == _STOP and shaped.get("tool_calls"):
        finish = "tool_calls"
    return {**choice, "index": _index(choice, position), "message": shaped, "finish_reason": finish}


def shape_completion(provider: str, payload: dict[str, object]) -> dict[str, object]:
    """A non-streaming answer in the shape the adapter reads.

    An answer without a choice, or with a choice that has no message, has nothing to read: the provider's reply is not
    a completion, and the failure is the provider's (``LLMResponseError`` carries the status of a gateway relaying a
    broken upstream answer, so the agent repeats the request).
    """
    choices = payload.get("choices")
    shaped = [
        _shape_choice(provider, choice, position)
        for position, choice in enumerate(choices if isinstance(choices, list) else [])
        if isinstance(choice, Mapping)
    ]
    if not shaped:
        excerpt = json.dumps(payload, ensure_ascii=False, default=str)[:_EXCERPT_LIMIT]
        raise LLMResponseError(provider, f"{provider} answered without a choice: {excerpt}")
    payload["choices"] = shaped
    payload["usage"] = shape_usage(payload.get("usage"))
    return payload


def _shape_stream_choice(choice: Mapping[str, object], position: int) -> dict[str, object]:
    delta = choice.get("delta")
    reason = choice.get("finish_reason")
    return {
        **choice,
        "index": _index(choice, position),
        "delta": dict(delta) if isinstance(delta, Mapping) else {},
        "finish_reason": _finish(reason) if reason else None,
    }


def shape_chunk(chunk: Chunk) -> Chunk:
    """One stream chunk in the shape the adapter reads (edited in place: the decoder hands it over)."""
    choices = chunk.get("choices")
    chunk["choices"] = [
        _shape_stream_choice(choice, position)
        for position, choice in enumerate(choices if isinstance(choices, list) else [])
        if isinstance(choice, Mapping)
    ]
    if "usage" in chunk:
        if usage := shape_usage(chunk["usage"]):
            chunk["usage"] = usage
        else:
            del chunk["usage"]
    return chunk


class ShapedDecoder:
    """A wire's stream decoder whose every chunk is shaped like a ``chat.completion.chunk`` the adapter reads."""

    __slots__ = ("_inner",)

    def __init__(self, inner: StreamDecoder) -> None:
        self._inner = inner

    @property
    def done(self) -> bool:
        return self._inner.done

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        return [shape_chunk(chunk) for chunk in self._inner.feed(event, data)]

    def finish(self) -> list[Chunk]:
        return [shape_chunk(chunk) for chunk in self._inner.finish()]
