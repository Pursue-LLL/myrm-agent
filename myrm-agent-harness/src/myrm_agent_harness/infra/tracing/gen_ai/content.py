"""Opt-in capture of prompt, reply and tool content on GenAI spans.

[INPUT]
- os.environ: ``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` (standard switch, off by default)

[OUTPUT]
- capture_content_enabled: whether content may be written onto spans at all
- CONTENT_VALUE_LIMIT: character budget the exporter keeps per content attribute
- input_messages_json / output_messages_json / query_messages_json: structured message attributes
- tool_arguments_json / tool_result_text: tool call content

[POS]
Producer side of content capture. Nothing here runs unless the switch is on, so the default path
costs one environment lookup. Output follows the GenAI message shape (role + typed parts); the
system prompt and model reasoning are never included, every text is clipped before it is
serialized, and the exporter's privacy guard redacts credentials and caps the final value.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence

CAPTURE_CONTENT_ENV = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
CONTENT_VALUE_LIMIT = 32768

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_SYSTEM_ROLES = frozenset({"system", "developer"})
_MAX_INPUT_MESSAGES = 8
_TEXT_LIMIT = 1500
_OUTPUT_TEXT_LIMIT = 4000
_ARGUMENTS_LIMIT = 500
_OMITTED = "[non-text content omitted]"

type Part = dict[str, object]


def capture_content_enabled() -> bool:
    """True when the operator opted in to exporting message and tool content."""
    return os.environ.get(CAPTURE_CONTENT_ENV, "").strip().lower() in _TRUTHY


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...[{len(text) - limit} more chars]"


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _text_parts(content: object, limit: int) -> list[Part]:
    if isinstance(content, str):
        return [{"type": "text", "content": _clip(content, limit)}] if content else []
    if not isinstance(content, Sequence):
        return []
    parts: list[Part] = []
    for block in content:
        if isinstance(block, str):
            parts.append({"type": "text", "content": _clip(block, limit)})
        elif isinstance(block, Mapping) and isinstance(block.get("text"), str):
            parts.append({"type": "text", "content": _clip(str(block["text"]), limit)})
        else:
            parts.append({"type": "text", "content": _OMITTED})
    return parts


def _content_text(content: object) -> str:
    return "".join(str(part["content"]) for part in _text_parts(content, _TEXT_LIMIT))


def _tool_call_parts(tool_calls: object) -> list[Part]:
    if not isinstance(tool_calls, Sequence) or isinstance(tool_calls, str):
        return []
    parts: list[Part] = []
    for call in tool_calls:
        if not isinstance(call, Mapping):
            continue
        function = call.get("function")
        function = function if isinstance(function, Mapping) else {}
        parts.append(
            {
                "type": "tool_call",
                "id": call.get("id"),
                "name": function.get("name"),
                "arguments": _clip(str(function.get("arguments") or ""), _ARGUMENTS_LIMIT),
            }
        )
    return parts


def _message(message: Mapping[str, object]) -> Part:
    role = str(message.get("role") or "user")
    if role == "tool":
        parts: list[Part] = [
            {
                "type": "tool_call_response",
                "id": message.get("tool_call_id"),
                "response": _content_text(message.get("content")),
            }
        ]
    else:
        parts = _text_parts(message.get("content"), _TEXT_LIMIT) + _tool_call_parts(message.get("tool_calls"))
    return {"role": role, "parts": parts}


def input_messages_json(message_dicts: Sequence[Mapping[str, object]]) -> str:
    """The most recent non-system messages of a model request."""
    recent = [message for message in message_dicts if message.get("role") not in _SYSTEM_ROLES]
    return _dumps([_message(message) for message in recent[-_MAX_INPUT_MESSAGES:]])


def output_messages_json(response: Mapping[str, object]) -> str:
    """The assistant message of a model response (text and tool calls, never reasoning)."""
    choices = response.get("choices")
    choice = choices[0] if isinstance(choices, Sequence) and choices and isinstance(choices[0], Mapping) else {}
    message = choice.get("message")
    message = message if isinstance(message, Mapping) else {}
    parts = _text_parts(message.get("content"), _OUTPUT_TEXT_LIMIT) + _tool_call_parts(message.get("tool_calls"))
    return _dumps([{"role": "assistant", "parts": parts, "finish_reason": choice.get("finish_reason")}])


def query_messages_json(query: object) -> str:
    """The user's turn as one input message; a resume command carries no text."""
    if isinstance(query, str) or (isinstance(query, Sequence) and not isinstance(query, bytes)):
        parts = _text_parts(query, _TEXT_LIMIT)
    else:
        parts = [{"type": "text", "content": "[resume command]"}]
    return _dumps([{"role": "user", "parts": parts}])


def tool_arguments_json(arguments: object) -> str:
    return _clip(_dumps(arguments), _TEXT_LIMIT)


def tool_result_text(content: object) -> str:
    if isinstance(content, (str, Sequence)) and not isinstance(content, bytes):
        return _content_text(content)
    return _clip(_dumps(content), _TEXT_LIMIT)
