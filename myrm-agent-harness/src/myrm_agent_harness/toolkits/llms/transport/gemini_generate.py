"""Gemini generateContent wire: OpenAI-shaped input to ``models/{model}:generateContent`` and back.

[INPUT]
- transport.gemini_schema (POS: tool-parameter schema reduction to the Gemini subset)
- transport.profile (POS: Route — endpoint root and credential)
- transport.params (POS: CallOptions split of the call's keyword arguments)
- transport.http (POS: PreparedRequest, StreamDecoder)

[OUTPUT]
- prepare: a PreparedRequest for ``generateContent`` / ``streamGenerateContent?alt=sse``
- parse: a GenerateContentResponse as a chat.completion dict (content, reasoning, tool_calls, usage)
- decoder: the SSE decoder yielding chat.completion.chunk dicts

[POS]
Translation boundary for the Gemini API (first-party and Gemini-compatible gateways, which speak this native
wire rather than the OpenAI one). Messages become ``contents`` with role alternation, tools become function
declarations, the system prompt becomes ``system_instruction``. Gemini 3 demands that a function call's
``thoughtSignature`` comes back on the next turn: it travels inside the tool-call id (``<id>__thought__<signature>``),
the one field every layer above preserves verbatim, so no other layer needs to know about it.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Final
from urllib.parse import urlsplit

from myrm_agent_harness.toolkits.llms.transport.errors import LLMStreamError
from myrm_agent_harness.toolkits.llms.transport.gemini_schema import to_gemini_schema
from myrm_agent_harness.toolkits.llms.transport.http import Chunk, PreparedRequest, StreamDecoder
from myrm_agent_harness.toolkits.llms.transport.params import CallOptions, merge_headers, split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route, UnsupportedProviderError

logger = logging.getLogger(__name__)

_SIGNATURE_SEPARATOR: Final = "__thought__"
_DATA_URL: Final = re.compile(r"^data:(?P<media>[^;,]+);base64,(?P<data>.+)$", re.DOTALL)
_THINKING_BUDGET: Final = {"minimal": 1024, "low": 1024, "medium": 2048, "high": 4096, "xhigh": 8192, "max": 8192}
_DISABLED_EFFORT: Final = frozenset({"none", "off", "disable", "disabled"})
_GEMINI_3: Final = re.compile(r"^gemini-3", re.IGNORECASE)
_FILTERED: Final = frozenset(
    {
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
        "IMAGE_SAFETY",
        "LANGUAGE",
        "IMAGE_PROHIBITED_CONTENT",
    }
)
_OFFICIAL_HOST: Final = "generativelanguage.googleapis.com"
Part = dict[str, object]


# --- request ---------------------------------------------------------------------------------------------------


def _split_signature(call_id: str) -> tuple[str, str | None]:
    base, sep, signature = call_id.partition(_SIGNATURE_SEPARATOR)
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
            if kind == "text" and isinstance(item.get("text"), str) and item["text"]:
                parts.append({"text": item["text"]})
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


def _function_calls(tool_calls: object, names: dict[str, str]) -> list[Part]:
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
        part: Part = {"functionCall": {"name": name, "args": args if isinstance(args, dict) else {}}}
        signature = _split_signature(call_id)[1]
        if signature:
            part["thoughtSignature"] = signature
        parts.append(part)
    return parts


def _function_response(message: Mapping[str, object], names: Mapping[str, str]) -> Part:
    content = message.get("content")
    text = content if isinstance(content, str) else "".join(str(p["text"]) for p in _parts(content) if "text" in p)
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    name = message.get("name") or names.get(str(message.get("tool_call_id") or "")) or "tool"
    return {"functionResponse": {"name": name, "response": parsed if isinstance(parsed, dict) else {"content": text}}}


def _to_contents(messages: Sequence[Mapping[str, object]]) -> tuple[list[Part], list[Part]]:
    system: list[Part] = []
    turns: list[tuple[str, list[Part]]] = []
    names: dict[str, str] = {}

    def push(role: str, parts: list[Part]) -> None:
        if not parts:
            return
        if turns and turns[-1][0] == role:
            turns[-1][1].extend(parts)
        else:
            turns.append((role, list(parts)))

    for message in messages:
        role = message.get("role")
        if role in ("system", "developer"):
            system.extend(_parts(message.get("content")))
        elif role == "assistant":
            push("model", _parts(message.get("content")) + _function_calls(message.get("tool_calls"), names))
        elif role == "tool":
            push("user", [_function_response(message, names)])
        elif role == "user":
            push("user", _parts(message.get("content")))
    return system, [{"role": role, "parts": parts} for role, parts in turns]


def _thinking_config(model: str, effort: object) -> Part | None:
    if not isinstance(effort, str) or effort.lower() in _DISABLED_EFFORT:
        return None
    level = effort.lower()
    if _GEMINI_3.match(model):
        return {"includeThoughts": True, "thinkingLevel": "low" if level in ("minimal", "low") else "high"}
    budget = _THINKING_BUDGET.get(level)
    return {"includeThoughts": True, "thinkingBudget": budget} if budget else None


def _generation_config(route: Route, params: Mapping[str, object]) -> Part:
    config: Part = {}
    limit = params.get("max_completion_tokens") or params.get("max_tokens")
    if isinstance(limit, int) and limit > 0:
        config["maxOutputTokens"] = limit
    for source, target in (
        ("temperature", "temperature"),
        ("top_p", "topP"),
        ("top_k", "topK"),
        ("seed", "seed"),
        ("presence_penalty", "presencePenalty"),
        ("frequency_penalty", "frequencyPenalty"),
    ):
        if params.get(source) is not None:
            config[target] = params[source]
    stop = params.get("stop")
    if isinstance(stop, str):
        config["stopSequences"] = [stop]
    elif isinstance(stop, list) and stop:
        config["stopSequences"] = [s for s in stop if isinstance(s, str)]
    response_format = params.get("response_format")
    if isinstance(response_format, Mapping) and response_format.get("type") in ("json_schema", "json_object"):
        config["responseMimeType"] = "application/json"
        holder = response_format.get("json_schema")
        schema = holder.get("schema") if isinstance(holder, Mapping) else None
        if isinstance(schema, Mapping):
            config["responseJsonSchema"] = dict(schema)
    thinking = _thinking_config(route.model, params.get("reasoning_effort"))
    if thinking is not None:
        config["thinkingConfig"] = thinking
    return config


def _tool_config(choice: object) -> Part | None:
    if choice in (None, "auto"):
        return {"functionCallingConfig": {"mode": "AUTO"}}
    if choice == "required":
        return {"functionCallingConfig": {"mode": "ANY"}}
    if choice == "none":
        return {"functionCallingConfig": {"mode": "NONE"}}
    if isinstance(choice, Mapping):
        function = choice.get("function")
        name = function.get("name") if isinstance(function, Mapping) else None
        if name:
            return {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [name]}}
    return None


def _declarations(raw: object) -> list[Part]:
    declarations: list[Part] = []
    for tool in raw if isinstance(raw, list) else []:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if not isinstance(function, Mapping) or not function.get("name"):
            continue
        entry: Part = {"name": function["name"]}
        if function.get("description"):
            entry["description"] = function["description"]
        parameters = function.get("parameters")
        if isinstance(parameters, Mapping) and parameters.get("properties"):
            entry["parameters"] = to_gemini_schema(parameters)
        declarations.append(entry)
    return declarations


def _body(route: Route, messages: Sequence[Mapping[str, object]], opts: CallOptions) -> dict[str, object]:
    params = opts.body
    system, contents = _to_contents(messages)
    body: dict[str, object] = {"contents": contents}
    if system:
        body["system_instruction"] = {"parts": system}
    config = _generation_config(route, params)
    if config:
        body["generationConfig"] = config
    declarations = _declarations(params.get("tools"))
    tools: list[Part] = []
    if declarations:
        tools.append({"functionDeclarations": declarations})
        tool_config = _tool_config(params.get("tool_choice"))
        if tool_config is not None:
            body["toolConfig"] = tool_config
    if isinstance(params.get("web_search_options"), Mapping):
        if declarations:
            logger.debug("Gemini cannot combine Google Search with function tools; search is skipped for this call")
        else:
            tools.append({"googleSearch": {}})
    if tools:
        body["tools"] = tools
    body.update(opts.extra_body)
    return body


def prepare(route: Route, messages: Sequence[Mapping[str, object]], params: Mapping[str, object]) -> PreparedRequest:
    opts = split_params(params)
    if not route.base_url:
        raise UnsupportedProviderError("The Gemini wire needs an api_base")
    action = "streamGenerateContent" if opts.stream else "generateContent"
    model = route.model.removeprefix("models/")
    headers: dict[str, str] = {}
    if route.api_key:
        headers["x-goog-api-key"] = route.api_key
        if urlsplit(route.base_url).hostname != _OFFICIAL_HOST:
            headers["Authorization"] = f"Bearer {route.api_key}"  # gateways that emulate the API read either header
    return PreparedRequest(
        provider=route.profile.id,
        url=f"{route.base_url}/models/{model}:{action}",
        headers=merge_headers(headers, opts.headers),
        body=_body(route, messages, opts),
        timeout=opts.timeout,
        proxy=opts.proxy,
        stream=opts.stream,
        query={"alt": "sse"} if opts.stream else {},
    )


# --- response --------------------------------------------------------------------------------------------------


def _finish_reason(reason: object, has_tool_calls: bool) -> str:
    if has_tool_calls:
        return "tool_calls"
    if reason == "MAX_TOKENS":
        return "length"
    if reason in _FILTERED:
        return "content_filter"
    return "stop"


def _usage(raw: Mapping[str, object]) -> dict[str, object]:
    """Thought tokens are billed as output; ``promptTokenCount`` already contains the cached tokens."""

    def count(key: str) -> int:
        value = raw.get(key)
        return value if isinstance(value, int) else 0

    prompt, candidates, thoughts, cached = (
        count("promptTokenCount"),
        count("candidatesTokenCount"),
        count("thoughtsTokenCount"),
        count("cachedContentTokenCount"),
    )
    usage: dict[str, object] = {
        "prompt_tokens": prompt,
        "completion_tokens": candidates + thoughts,
        "total_tokens": count("totalTokenCount") or prompt + candidates + thoughts,
        "prompt_tokens_details": {"cached_tokens": cached},
    }
    if thoughts:
        usage["completion_tokens_details"] = {"reasoning_tokens": thoughts}
    return usage


def _tool_call(part: Mapping[str, object], index: int) -> Part | None:
    call = part.get("functionCall")
    if not isinstance(call, Mapping):
        return None
    call_id = f"call_{uuid.uuid4().hex[:24]}"
    signature = part.get("thoughtSignature")
    if isinstance(signature, str) and signature:
        call_id += _SIGNATURE_SEPARATOR + signature
    return {
        "index": index,
        "id": call_id,
        "type": "function",
        "function": {"name": call.get("name"), "arguments": json.dumps(call.get("args") or {}, ensure_ascii=False)},
    }


def _candidate(payload: Mapping[str, object]) -> Mapping[str, object]:
    candidates = payload.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else None
    return first if isinstance(first, Mapping) else {}


def _candidate_parts(candidate: Mapping[str, object]) -> list[Mapping[str, object]]:
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, Mapping) else None
    return [p for p in parts if isinstance(p, Mapping)] if isinstance(parts, list) else []


def _blocked(payload: Mapping[str, object]) -> bool:
    feedback = payload.get("promptFeedback")
    return isinstance(feedback, Mapping) and bool(feedback.get("blockReason"))


def parse(route: Route, payload: dict[str, object]) -> dict[str, object]:
    candidate = _candidate(payload)
    texts: list[str] = []
    reasoning: list[str] = []
    tool_calls: list[Part] = []
    for part in _candidate_parts(candidate):
        call = _tool_call(part, len(tool_calls))
        if call is not None:
            tool_calls.append(call)
        elif isinstance(part.get("text"), str):
            (reasoning if part.get("thought") is True else texts).append(str(part["text"]))
    message: Part = {"role": "assistant", "content": "".join(texts) or None}
    if reasoning:
        message["reasoning_content"] = "".join(reasoning)
    if tool_calls:
        message["tool_calls"] = [{k: v for k, v in c.items() if k != "index"} for c in tool_calls]
    usage = payload.get("usageMetadata")
    reason = (
        "content_filter"
        if _blocked(payload) and not candidate
        else _finish_reason(candidate.get("finishReason"), bool(tool_calls))
    )
    return {
        "id": payload.get("responseId") or f"gemini-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": payload.get("modelVersion") or route.model,
        "choices": [{"index": 0, "message": message, "finish_reason": reason}],
        "usage": _usage(usage) if isinstance(usage, Mapping) else {},
    }


# --- stream ----------------------------------------------------------------------------------------------------


class GeminiStreamDecoder:
    """One SSE event is a partial GenerateContentResponse; the event carrying ``finishReason`` closes the answer."""

    __slots__ = ("_id", "_model", "_provider", "_tool_index", "done")

    def __init__(self, provider: str, model: str) -> None:
        self._provider = provider
        self._model = model
        self._id = f"gemini-{uuid.uuid4().hex[:12]}"
        self._tool_index = -1
        self.done = False

    def feed(self, event: str | None, data: str) -> list[Chunk]:
        try:
            payload = json.loads(data)
        except ValueError:
            return []
        if not isinstance(payload, dict):
            return []
        if "error" in payload and "candidates" not in payload:
            raise LLMStreamError(self._provider, payload)
        self._model = str(payload.get("modelVersion") or self._model)
        candidate = _candidate(payload)
        delta: Part = {}
        calls: list[Part] = []
        for part in _candidate_parts(candidate):
            call = _tool_call(part, self._tool_index + 1)
            if call is not None:
                self._tool_index += 1
                calls.append(call)
            elif isinstance(part.get("text"), str) and part["text"]:
                key = "reasoning_content" if part.get("thought") is True else "content"
                delta[key] = str(delta.get(key, "")) + str(part["text"])
        if calls:
            delta["tool_calls"] = calls
        reason = candidate.get("finishReason")
        finish = None
        if reason or (_blocked(payload) and not candidate):
            finish = "content_filter" if not reason else _finish_reason(reason, self._tool_index >= 0)
        if not delta and finish is None:
            return []
        chunk: Chunk = {
            "id": self._id,
            "object": "chat.completion.chunk",
            "model": self._model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        usage = payload.get("usageMetadata")
        if finish is not None and isinstance(usage, Mapping):
            chunk["usage"] = _usage(usage)
        return [chunk]

    def finish(self) -> list[Chunk]:
        return []


def decoder(route: Route) -> StreamDecoder:
    return GeminiStreamDecoder(route.profile.id, route.model)
