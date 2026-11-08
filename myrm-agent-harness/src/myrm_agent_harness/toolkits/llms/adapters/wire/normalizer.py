"""Normalize OpenAI Responses API payloads into chat-completions-shaped dicts.

[INPUT]
- typing::Any (POS: Python 类型标注标准库)
- utils.coercion::parse_int (POS: token counts a provider sends as text, null or negative)
- toolkits.llms.transport.errors::error_status (POS: the HTTP status a failure reported inside a 2xx answer stands for)
- .responses_stream::ResponsesStreamState (POS: per-stream function-call and reasoning bookkeeping)

[OUTPUT]
- responses_dict_to_chat_completion: completed payload → chat.completion dict
- responses_event_to_completion_chunk: SSE event (+ the stream's state) → chat.completion.chunk or None
- responses_stream_failure / assert_responses_payload_not_failed: failure surfacing as ResponsesStreamError, which
  carries the HTTP status the failure stands for
- extract_responses_reasoning_items: encrypted reasoning items for later replay

[POS]
Inbound leg of the LLM adapter wire layer. Converts vendor Responses shapes into the
chat-completions contract TransportChatModel already consumes, so upstream code stays vendor
agnostic. Streaming tool-call arguments are emitted as deltas, once per call; assembled by the caller.
Usage keeps the cache-hit, cache-write and reasoning token counters in the ``*_details`` objects.
"""

from __future__ import annotations

from typing import Any

from myrm_agent_harness.toolkits.llms.transport.errors import error_status
from myrm_agent_harness.utils.coercion import parse_int

from .responses_stream import ResponsesStreamState, ToolCallDelta

_REQUEST_FAILED = "Responses API request failed"


class ResponsesStreamError(Exception):
    """OpenAI Responses API returned a failed or error stream/completion payload.

    ``status_code`` is the HTTP status the failure stands for (``None`` when it names none and nothing else implies
    one), which is what lets the failure classifier repeat a ``server_error`` or a rate limit and leave a rejected
    prompt alone.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _error_message_from_payload(error: object) -> str | None:
    if isinstance(error, str) and error.strip():
        return error.strip()
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            code = error.get("code")
            if isinstance(code, str) and code.strip():
                return f"{code}: {message.strip()}"
            return message.strip()
    return None


def _failure(error: object, *, in_stream: bool) -> ResponsesStreamError | None:
    message = _error_message_from_payload(error)
    if message is None:
        return None
    return ResponsesStreamError(message, error_status(error if isinstance(error, dict) else {}, in_stream=in_stream))


def responses_stream_failure(event: dict[str, Any]) -> ResponsesStreamError | None:
    """The failure a Responses SSE event reports, if it reports one.

    An ``error`` event or a ``response.failed`` event is a failure even when it says nothing more: reading it as an
    ordinary event would end the answer where the provider broke it, and call that a success.
    """
    event_type = str(event.get("type") or "").lower()
    response = event.get("response")
    nested = response if isinstance(response, dict) else {}
    is_error = event_type == "error" or event_type.endswith(".error")
    reports_failure = "failed" in event_type or nested.get("status") == "failed"
    if not (is_error or reports_failure):
        return None
    # OpenAI's own error event carries ``code`` and ``message`` on the event itself; gateways nest them in ``error``.
    for error in (event.get("error"), nested.get("error"), event if is_error else None):
        if failure := _failure(error, in_stream=True):
            return failure
    if is_error or event_type == "response.failed" or nested.get("status") == "failed":
        return ResponsesStreamError(_REQUEST_FAILED, error_status(event, in_stream=True))
    return None


def assert_responses_payload_not_failed(response: dict[str, Any]) -> None:
    """Raise when a non-stream Responses payload reports failed status."""
    if response.get("status") != "failed":
        return
    raise _failure(response.get("error"), in_stream=False) or ResponsesStreamError(_REQUEST_FAILED)


def _extract_output_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str):
        return output_text
    parts: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
    return "".join(parts)


def _extract_reasoning_summary(response: dict[str, Any]) -> str:
    """Extract plain text summary from reasoning output items, if available."""
    parts: list[str] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        summary = item.get("summary")
        if isinstance(summary, list):
            for part in summary:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
    return "".join(parts)


def _tool_call_from_function_item(item: dict[str, Any]) -> dict[str, Any] | None:
    call_id = item.get("call_id") or item.get("id")
    name = item.get("name")
    arguments = item.get("arguments") or "{}"
    if not call_id or not name:
        return None
    return {
        "id": str(call_id),
        "type": "function",
        "function": {"name": str(name), "arguments": str(arguments)},
    }


def extract_responses_reasoning_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve reasoning output items (with encrypted_content) for multi-turn replay."""
    preserved: list[dict[str, Any]] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        entry: dict[str, Any] = {"type": "reasoning"}
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id.strip():
            entry["id"] = item_id
        encrypted = item.get("encrypted_content")
        if isinstance(encrypted, str) and encrypted.strip():
            entry["encrypted_content"] = encrypted
        summary = item.get("summary")
        if isinstance(summary, list):
            entry["summary"] = summary
        else:
            entry["summary"] = []
        if len(entry) > 1:
            preserved.append(entry)
    return preserved


def _extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for item in response.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "function_call":
            continue
        mapped = _tool_call_from_function_item(item)
        if mapped is not None:
            tool_calls.append(mapped)
    return tool_calls


def _usage_details(raw: object, keys: tuple[str, ...]) -> dict[str, int]:
    """The non-zero token counters among ``keys`` of a usage ``*_details`` object."""
    if not isinstance(raw, dict):
        return {}
    return {key: count for key in keys if isinstance(count := raw.get(key), int) and count > 0}


def _map_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    """Chat-completions usage of a Responses ``usage`` object; empty when the provider reported none.

    A count that is text, null or negative is read the way every chat wire reads it (``chat_shape.shape_usage``):
    as the number it spells, else zero.
    """
    if not usage:
        return {}
    input_tokens = parse_int(usage.get("input_tokens") or usage.get("prompt_tokens"), 0, min_val=0)
    output_tokens = parse_int(usage.get("output_tokens") or usage.get("completion_tokens"), 0, min_val=0)
    total = parse_int(usage.get("total_tokens"), 0, min_val=0) or input_tokens + output_tokens
    mapped: dict[str, Any] = {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": total,
    }
    # Cache hits and reasoning tokens ride in the details objects; cost and cache accounting read them there.
    prompt_details = _usage_details(
        usage.get("input_tokens_details") or usage.get("prompt_tokens_details"), ("cached_tokens", "cache_write_tokens")
    )
    if prompt_details:
        mapped["prompt_tokens_details"] = prompt_details
    completion_details = _usage_details(
        usage.get("output_tokens_details") or usage.get("completion_tokens_details"), ("reasoning_tokens",)
    )
    if completion_details:
        mapped["completion_tokens_details"] = completion_details
    return mapped


def responses_dict_to_chat_completion(response: dict[str, Any]) -> dict[str, Any]:
    """Convert a completed Responses API payload to chat-completions shape for TransportChatModel."""
    text = _extract_output_text(response)
    tool_calls = _extract_tool_calls(response)
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    reasoning_summary = _extract_reasoning_summary(response)
    if reasoning_summary:
        message["reasoning_content"] = reasoning_summary
    reasoning_items = extract_responses_reasoning_items(response)
    if reasoning_items:
        message["responses_reasoning_items"] = reasoning_items
    if tool_calls:
        message["tool_calls"] = tool_calls
        message["content"] = text or ""
    finish_reason = "tool_calls" if tool_calls else "stop"
    if response.get("status") == "incomplete":
        finish_reason = "length"
    return {
        "id": response.get("id"),
        "object": "chat.completion",
        "model": response.get("model"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": _map_usage(response.get("usage") if isinstance(response.get("usage"), dict) else None),
    }


_REASONING_DELTA_EVENTS = (
    "reasoning.delta",
    "reasoning_summary.delta",
    "reasoning_summary_text.delta",
    "reasoning_text.delta",
)


def _is_terminal_event(normalized_type: str) -> bool:
    return (
        "response.completed" in normalized_type
        or "response.incomplete" in normalized_type
        or normalized_type.endswith(("response_completed", "response_incomplete"))
    )


def _tool_calls_chunk(tool_calls: list[ToolCallDelta]) -> dict[str, Any] | None:
    if not tool_calls:
        return None
    return {"choices": [{"index": 0, "delta": {"tool_calls": tool_calls}, "finish_reason": None}]}


def _completed_chunk(response: dict[str, Any], state: ResponsesStreamState) -> dict[str, Any]:
    """Closing chunk: finish reason, usage and the parts of the final output that were not streamed."""
    output = response.get("output")
    tool_calls = state.on_completed(output if isinstance(output, list) else [])
    finish_reason = "tool_calls" if tool_calls or state.has_calls else "stop"
    if response.get("status") == "incomplete":
        finish_reason = "length"
    delta: dict[str, Any] = {}
    if tool_calls:
        delta["tool_calls"] = tool_calls
    reasoning_summary = _extract_reasoning_summary(response)
    if reasoning_summary and not state.reasoning_streamed:
        delta["reasoning_content"] = reasoning_summary
    reasoning_items = extract_responses_reasoning_items(response)
    if reasoning_items:
        delta["responses_reasoning_items"] = reasoning_items
    chunk: dict[str, Any] = {"choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]}
    usage = _map_usage(response.get("usage") if isinstance(response.get("usage"), dict) else None)
    if usage:
        chunk["usage"] = usage
    return chunk


def responses_event_to_completion_chunk(
    event: dict[str, Any], state: ResponsesStreamState | None = None
) -> dict[str, Any] | None:
    """Map a Responses stream event to a chat completion stream chunk dict.

    ``state`` must be shared by every event of one stream: a function call spans several events and the
    closing event repeats what was streamed. Without it the event is mapped as if it were the whole stream.
    """
    if state is None:
        state = ResponsesStreamState()
    normalized_type = str(event.get("type") or "").lower()
    delta = event.get("delta")

    if (
        ("output_text.delta" in normalized_type or normalized_type.endswith("output_text_delta"))
        and isinstance(delta, str)
        and delta
    ):
        return {
            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        }

    if any(name in normalized_type for name in _REASONING_DELTA_EVENTS):
        text_delta = delta if isinstance(delta, str) else ""
        if not text_delta and isinstance(delta, dict):
            text_delta = str(delta.get("text") or "")
        if text_delta:
            state.reasoning_streamed = True
            return {
                "choices": [{"index": 0, "delta": {"reasoning_content": text_delta}, "finish_reason": None}],
            }

    item = event.get("item")
    if isinstance(item, dict) and item.get("type") == "function_call":
        return _tool_calls_chunk(state.on_item(event, item))

    if "function_call_arguments" in normalized_type:
        final = normalized_type.endswith(("arguments.done", "arguments_done"))
        return _tool_calls_chunk(state.on_arguments(event, final=final))

    if _is_terminal_event(normalized_type):
        response = event.get("response")
        if isinstance(response, dict):
            return _completed_chunk(response, state)
    return None
