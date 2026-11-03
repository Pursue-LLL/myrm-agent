"""Gemini ``contents``: an OpenAI-shaped history as alternating user/model turns.

[INPUT]
- (none) Pure translation over stdlib.

[OUTPUT]
- to_contents: (system parts, turns) for a ``generateContent`` request
- split_signature / SIGNATURE_SEPARATOR: the ``<id>__thought__<signature>`` call-id convention, shared with the answer side
- Part: one JSON object of the Gemini wire

[POS]
Request-side half of the Gemini wire. Content parts become text, inline data or file data; assistant tool calls
become ``functionCall`` parts and tool results ``functionResponse`` parts. Gemini 3 and later demand the
``thoughtSignature`` of a function call on the next turn and take the call id on calls and responses: both come from the
tool-call id (``<id>__thought__<signature>``), the one field every layer above preserves verbatim, and a call this model
did not sign (history from another model, a rewritten id) gets Google's placeholder signature. Inline media a tool
returned (a screenshot) goes inside the function response on Gemini 3 and later; earlier models, and media given by
address, take it as parts beside the function response in the same turn, the shape Google's own CLI sends.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from collections.abc import Mapping, Sequence
from typing import Final
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

Part = dict[str, object]
SIGNATURE_SEPARATOR: Final = "__thought__"
INTERRUPTED_REPLY: Final = "[The previous response was interrupted before it completed.]"
_DATA_URL: Final = re.compile(r"^data:(?P<media>[^;,]+);base64,(?P<data>.+)$", re.DOTALL)
# Google's documented bypass for a function call the model did not produce itself.
_UNSIGNED_CALL: Final = base64.b64encode(b"skip_thought_signature_validator").decode("ascii")


def split_signature(call_id: str) -> tuple[str, str | None]:
    base, sep, signature = call_id.partition(SIGNATURE_SEPARATOR)
    return base, (signature if sep and signature else None)


def _media_part(url: str, fallback_media: str) -> Part:
    match = _DATA_URL.match(url)
    if match:
        return {"inlineData": {"mimeType": match["media"], "data": match["data"]}}
    media = mimetypes.guess_type(urlsplit(url).path)[0] or fallback_media
    return {"fileData": {"fileUri": url, "mimeType": media}}


def _parts(content: object) -> list[Part]:
    if isinstance(content, str):
        return [{"text": content}] if content else []
    parts: list[Part] = []
    for item in content if isinstance(content, list) else []:
        if isinstance(item, str):
            if item:
                parts.append({"text": item})
        elif isinstance(item, Mapping):
            kind = item.get("type")
            if kind == "text":
                text = item.get("text")
                if isinstance(text, str) and text:
                    parts.append({"text": text})
            elif kind == "image_url":
                image = item.get("image_url")
                url = image.get("url") if isinstance(image, Mapping) else image
                if isinstance(url, str) and url:
                    parts.append(_media_part(url, "image/jpeg"))
            elif kind == "file":
                file = item.get("file")
                data = file.get("file_data") if isinstance(file, Mapping) else None
                if isinstance(data, str) and _DATA_URL.match(data):
                    parts.append(_media_part(data, "application/octet-stream"))
            else:
                logger.warning("Dropping content part of unsupported type %r for the Gemini API", kind)
    return parts


def _function_calls(tool_calls: object, names: dict[str, str], *, gemini_3: bool) -> list[Part]:
    parts: list[Part] = []
    for call in tool_calls if isinstance(tool_calls, list) else []:
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        raw = function.get("arguments")
        try:
            args = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        except ValueError:
            args = {}
        name = str(function.get("name") or "")
        call_id = str(call.get("id") or "")
        names[call_id] = name
        base_id, signature = split_signature(call_id)
        call_body: Part = {"name": name, "args": args if isinstance(args, dict) else {}}
        if gemini_3 and base_id:
            call_body["id"] = base_id
        part: Part = {"functionCall": call_body}
        signature = signature or (_UNSIGNED_CALL if gemini_3 else None)
        if signature:
            part["thoughtSignature"] = signature
        parts.append(part)
    return parts


def _function_response(message: Mapping[str, object], names: Mapping[str, str], *, gemini_3: bool) -> list[Part]:
    """The function response part, followed by the media a tool returned that does not fit inside it."""
    content = message.get("content")
    parts = [] if isinstance(content, str) else _parts(content)
    text = content if isinstance(content, str) else "".join(str(p["text"]) for p in parts if "text" in p)
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    call_id = str(message.get("tool_call_id") or "")
    name = message.get("name") or names.get(call_id) or "tool"
    response: Part = {"name": name, "response": parsed if isinstance(parsed, dict) else {"content": text}}
    if gemini_3 and call_id:
        response["id"] = split_signature(call_id)[0]
    nested: list[Part] = []
    beside: list[Part] = []
    for part in parts:
        if "text" not in part:
            (nested if gemini_3 and "inlineData" in part else beside).append(part)
    if nested:
        response["parts"] = nested
    return [{"functionResponse": response}, *beside]


def _carries_response(parts: Sequence[Part]) -> bool:
    return any("functionResponse" in part for part in parts)


def to_contents(messages: Sequence[Mapping[str, object]], *, gemini_3: bool) -> tuple[list[Part], list[Part]]:
    """(system parts, alternating user/model turns) for an OpenAI-shaped history."""
    system: list[Part] = []
    turns: list[tuple[str, list[Part]]] = []
    names: dict[str, str] = {}

    def push(role: str, parts: list[Part]) -> None:
        if not parts:
            return
        if not turns or turns[-1][0] != role:
            turns.append((role, list(parts)))
        elif role == "user" and _carries_response(turns[-1][1]) != _carries_response(parts):
            # Gemini 3 reads a user message folded into a tool result as the result's continuation and answers
            # nothing, while two adjacent user turns are refused: a model turn keeps them apart and the roles alternating.
            turns.append(("model", [{"text": INTERRUPTED_REPLY}]))
            turns.append((role, list(parts)))
        else:
            turns[-1][1].extend(parts)

    for message in messages:
        role = message.get("role")
        if role in ("system", "developer"):
            system.extend(_parts(message.get("content")))
        elif role == "assistant":
            push(
                "model",
                _parts(message.get("content")) + _function_calls(message.get("tool_calls"), names, gemini_3=gemini_3),
            )
        elif role == "tool":
            push("user", _function_response(message, names, gemini_3=gemini_3))
        elif role == "user":
            push("user", _parts(message.get("content")))
    return system, [{"role": role, "parts": parts} for role, parts in turns]
